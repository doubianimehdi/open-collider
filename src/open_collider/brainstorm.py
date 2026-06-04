"""Python orchestrator for API mode. Reuses all prepare/parse from skill_interface."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from open_collider.config import load_project_config
from open_collider.llm.client import LLMClient, validate_provider_model_config
from open_collider.phases.idea_scorer import apply_threshold
from open_collider.skill_interface import (
    init_iteration,
    prepare_domain_prompt,
    parse_domain_response_text,
    prepare_idea_prompts,
    parse_idea_response,
    prepare_scoring_prompts,
    parse_scoring_response,
    finalize_iteration,
    apply_flags as _apply_flags,
    generate_brainstorm_report,
)

logger = logging.getLogger(__name__)

BACKOFF_DELAYS = [30, 60, 120]


class BrainstormOrchestrator:
    """Run a full brainstorm iteration via direct API calls."""

    def __init__(self, project_dir: Path, brainstorm_id: str | None = None) -> None:
        self.project_dir = project_dir
        self.brainstorm_id = brainstorm_id
        self.config = load_project_config(str(project_dir))
        validate_provider_model_config(self.config)
        self.llm = LLMClient(
            provider=self.config.get("llm_provider", "anthropic"),
            timeout=self._optional_int_config("llm_timeout"),
        )

    def run_iteration(self) -> dict:
        """Run one brainstorm iteration: domains → ideas → scoring → finalize."""
        state = init_iteration(str(self.project_dir), brainstorm_id=self.brainstorm_id)
        config = state["config"]
        iteration = state["iteration"]

        logger.info("=== Brainstorm iteration %d ===", iteration)

        # ---- Phase 1: Domain generation (sequential) ----
        strategies_cfg = config.get("strategies", {})
        strategy_domain_yamls = {}
        strategy_to_ideas = {}

        for strat_name, strat_cfg in strategies_cfg.items():
            if not strat_cfg.get("enabled", True):
                continue
            condition = strat_cfg.get("condition", "always")
            if not self._check_condition(condition, state):
                continue

            result = prepare_domain_prompt(strat_name, str(self.project_dir), state)
            if result is None:
                continue

            logger.info("Generating %s domains...", strat_name)
            response = self.llm.call(
                model=result["model"],
                prompt=result["prompt"],
                temperature=0.5,
                max_tokens=self._int_config("domain_max_tokens", 16000),
            )
            yaml_str = parse_domain_response_text(response)
            strategy_domain_yamls[strat_name] = yaml_str
            logger.info("%s domains generated", strat_name)

        if not strategy_domain_yamls:
            raise RuntimeError("No strategies produced domains")

        # ---- Phase 2: Idea generation (parallel per strategy) ----
        all_ideas = []
        max_concurrent = config.get("max_concurrent", 4)

        for strat_name, yaml_str in strategy_domain_yamls.items():
            combos = prepare_idea_prompts(
                str(self.project_dir), yaml_str, strat_name, state
            )
            logger.info("Generating ideas for %s: %d combos", strat_name, len(combos))

            ideas = asyncio.run(self._generate_ideas_parallel(combos, max_concurrent))

            for idea in ideas:
                idea["strategy"] = strat_name
                idea["iteration"] = iteration

            strategy_to_ideas[strat_name] = ideas
            all_ideas.extend(ideas)

        logger.info("Total raw ideas: %d", len(all_ideas))

        if not all_ideas:
            raise RuntimeError("No ideas generated across all strategies. Check domain quality and prompt template.")

        # ---- Phase 3: Scoring (parallel batches) ----
        batches = prepare_scoring_prompts(all_ideas, str(self.project_dir), state)
        max_scoring = config.get("max_concurrent_scoring", 3)

        logger.info("Scoring %d ideas in %d batches", len(all_ideas), len(batches))
        scored_ideas = asyncio.run(
            self._score_batches_parallel(batches, config, max_scoring)
        )

        # Check for catastrophic scoring loss
        if len(scored_ideas) < len(all_ideas) * 0.5:
            logger.error(
                "Scoring lost too many ideas: %d/%d scored",
                len(scored_ideas), len(all_ideas),
            )
            raise RuntimeError(
                f"Scoring failed: only {len(scored_ideas)}/{len(all_ideas)} ideas scored"
            )
        elif len(scored_ideas) < len(all_ideas):
            lost = len(all_ideas) - len(scored_ideas)
            logger.warning("Scoring lost %d/%d ideas", lost, len(all_ideas))

        # ---- Phase 4: Threshold + Finalize ----
        scored_ideas = apply_threshold(scored_ideas, config)
        retained = [i for i in scored_ideas if i.get("retained")]
        logger.info("Scored %d, retained %d", len(scored_ideas), len(retained))

        result = finalize_iteration(
            str(self.project_dir),
            state,
            strategy_domain_yamls,
            all_ideas,
            scored_ideas,
            strategy_to_ideas,
        )

        # Add path info so the skill knows where to find the output
        result["brainstorm_id"] = state.get("brainstorm_dir", "").split("/")[-1]
        result["iter_dir"] = state.get("iter_dir", "")
        return result

    def apply_flags(self, iteration: int, flags: dict) -> None:
        """Apply love/like/trash flags to an iteration."""
        # Ensure state points to the right brainstorm
        if self.brainstorm_id:
            self._ensure_state_points_to_brainstorm()
        _apply_flags(str(self.project_dir), iteration, flags)

    def close_session(self) -> str:
        """Generate final brainstorm report."""
        if self.brainstorm_id:
            self._ensure_state_points_to_brainstorm()
        return generate_brainstorm_report(str(self.project_dir))

    def _ensure_state_points_to_brainstorm(self) -> None:
        """Make sure brainstorm_state.json points to self.brainstorm_id."""
        from open_collider.skill_interface import _load_state, _save_state
        state = _load_state(self.project_dir)
        if state.get("brainstorm_id") != self.brainstorm_id:
            state["brainstorm_id"] = self.brainstorm_id
            _save_state(self.project_dir, state)

    # ---- Parallel idea generation ----

    async def _generate_ideas_parallel(
        self, combos: list[dict], max_concurrent: int
    ) -> list[dict]:
        semaphore = asyncio.Semaphore(max_concurrent)
        all_ideas = []

        async def _gen_one(combo_info: dict) -> list[dict]:
            async with semaphore:
                combo_id = combo_info["combo_id"]
                model = combo_info["model"]
                prompt = combo_info["prompt"]

                for attempt, delay in enumerate([0] + BACKOFF_DELAYS):
                    if delay > 0:
                        logger.warning(
                            "Combo %s retry #%d after %ds", combo_id, attempt, delay
                        )
                        await asyncio.sleep(delay)
                    try:
                        response = await asyncio.to_thread(
                            self.llm.call,
                            model=model,
                            prompt=prompt,
                            temperature=0.9,
                            max_tokens=self._int_config("generation_max_tokens", 4000),
                        )
                        ideas = parse_idea_response(combo_info, response)
                        logger.info("Combo %s: %d ideas", combo_id, len(ideas))
                        return ideas
                    except Exception as exc:
                        logger.warning(
                            "Combo %s attempt %d: %s", combo_id, attempt, exc
                        )

                logger.error("Combo %s failed after all retries", combo_id)
                return []

        tasks = [_gen_one(c) for c in combos]
        results = await asyncio.gather(*tasks)
        for result in results:
            all_ideas.extend(result)
        return all_ideas

    # ---- Parallel scoring ----

    async def _score_batches_parallel(
        self, batches: list[dict], config: dict, max_concurrent: int
    ) -> list[dict]:
        semaphore = asyncio.Semaphore(max_concurrent)
        all_scored = []

        async def _score_one(batch_info: dict) -> list[dict]:
            async with semaphore:
                try:
                    response = await asyncio.to_thread(
                        self.llm.call,
                        model=batch_info["model"],
                        prompt=batch_info["prompt"],
                        temperature=0.1,
                        max_tokens=self._int_config("scoring_max_tokens", 8000),
                    )
                    scored = parse_scoring_response(batch_info, response, config)
                    logger.info(
                        "Batch %d: %d scored", batch_info["batch_id"], len(scored)
                    )
                    return scored
                except Exception as exc:
                    logger.error(
                        "Batch %d failed: %s", batch_info["batch_id"], exc
                    )
                    return []

        tasks = [_score_one(b) for b in batches]
        results = await asyncio.gather(*tasks)
        for result in results:
            all_scored.extend(result)
        return all_scored

    # ---- Helpers ----

    @staticmethod
    def _check_condition(condition: str, state: dict) -> bool:
        if condition == "always":
            return True
        if condition == "has_loved":
            return state["has_loved"]
        if condition == "has_liked":
            return state["has_liked"]
        if condition == "has_loved_or_liked":
            return state["has_loved"] or state["has_liked"]
        return True

    def _optional_int_config(self, key: str) -> int | None:
        value = self.config.get(key)
        if value is None or value == "":
            return None
        return int(value)

    def _int_config(self, key: str, default: int) -> int:
        value = self.config.get(key, default)
        return int(value)
