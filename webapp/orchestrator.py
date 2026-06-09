"""Web orchestrator: runs a brainstorm iteration with live progress events.

Reuses all prepare/parse logic from open_collider.skill_interface, adds:
- per-step progress events pushed to an in-memory queue (consumed by the API)
- a deterministic demo-mode LLM so the whole flow works without an API key
- an automatic curation step (top retained ideas -> curated_ideas.json)
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import yaml

from open_collider.config import load_project_config
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
    mark_curated,
    _save_json,
)

logger = logging.getLogger(__name__)

CURATED_TOP_N = 12


# ======================================================================
# DEMO-MODE LLM
# ======================================================================

_DEMO_FAMILIES = [
    ("Glass physics & fracture mechanics", [
        "Prince Rupert's drop dynamics", "Tempered glass stress fields",
        "Crack-tip propagation", "Annealing point chemistry", "Obsidian conchoidal fracture"]),
    ("Fermentation biology", [
        "Koji mold enzymatic infiltration", "Lambic spontaneous inoculation",
        "Lactobacillus pH gating", "Solid-state fermentation gradients", "SCOBY pellicle architecture"]),
    ("Deep-sea hydrothermal ecology", [
        "Chemosynthetic symbiosis", "Thermal plume stratification",
        "Vent succession cycles", "Barophile membrane adaptation", "Black smoker mineral chimneys"]),
    ("Medieval siegecraft logistics", [
        "Counterwall circumvallation", "Sapping and counter-mining",
        "Provision decay accounting", "Trebuchet counterweight tuning", "Parley protocol economics"]),
    ("Avalanche forecasting", [
        "Weak-layer persistence", "Slab tensile release",
        "Remote triggering propagation", "Faceted crystal metamorphism", "Terrain trap mapping"]),
    ("Cathedral acoustics engineering", [
        "Reverberation tail shaping", "Helmholtz resonator vases",
        "Choir screen diffusion", "Stone absorption coefficients", "Whispering gallery modes"]),
    ("Ant colony task allocation", [
        "Response-threshold polyethism", "Trophallaxis information flow",
        "Stigmergic trail decay", "Queen pheromone gradients", "Raid front turbulence"]),
    ("Forensic entomology", [
        "Succession wave dating", "Larval thermal histories",
        "Species arrival latencies", "Microclimate correction factors", "Toxicological bioaccumulation"]),
]

_DEMO_MECHANISMS = [
    "inverts the usual relationship between strength and fragility: the most resistant structure fails catastrophically at its least-watched edge",
    "shows that transformation happens invisibly for days before any surface change is detectable",
    "relies on decay as the carrier of information, not the loss of it",
    "allocates work without any central planner, purely through local response thresholds",
    "turns waiting into the primary instrument of control",
    "uses the boundary layer, not the core, as the site where all the real exchange happens",
    "demonstrates that the timing of arrival encodes more information than the arrival itself",
    "shapes outcomes by removing energy at precise moments rather than adding it",
]

_DEMO_IDEA_VERBS = [
    "Re-architect", "Invert", "Stage", "Instrument", "Decay-weight", "Stratify",
    "Seed", "Quarantine", "Triangulate", "Anneal",
]
_DEMO_IDEA_OBJECTS = [
    "the onboarding funnel", "the feedback loop", "the discovery surface",
    "the trust boundary", "the pricing ladder", "the retention mechanism",
    "the content pipeline", "the recommendation engine", "the community layer",
]


class DemoLLM:
    """Deterministic-ish fake LLM. Instant, no API key, clearly simulated."""

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._call_delay = 0.25

    def call(self, model: str, prompt: str, temperature: float = 0.7,
             max_tokens: int = 8000) -> str:
        time.sleep(self._call_delay)
        if "IDEAS TO EVALUATE" in prompt:
            return self._scoring_response(prompt)
        # All three domain strategies (fresh/deepen/refresh) share this preamble
        if "creative bisociation (Arthur Koestler)" in prompt:
            return self._domain_response()
        return self._idea_response(prompt)

    def _domain_response(self) -> str:
        families = self._rng.sample(_DEMO_FAMILIES, 4)
        sets = {}
        for i, (fam, specs) in enumerate(families, 1):
            domains = []
            for spec in self._rng.sample(specs, 3):
                mech = self._rng.choice(_DEMO_MECHANISMS)
                domains.append({
                    "name": spec,
                    "active_principle": (
                        f"A specialist in {spec.lower()} — whose work {mech}. "
                        f"The mechanism is well documented and counter-intuitive. "
                        f"What would it mean to apply this directly to the project's territory?"
                    ),
                })
            sets[f"DS{i}"] = {"name": fam, "domains": domains}
        return "```yaml\n" + yaml.dump({"sets": sets}, allow_unicode=True, sort_keys=False) + "```"

    def _idea_response(self, prompt: str) -> str:
        # Pull domain names out of the prompt for plausible attribution
        domain_names = re.findall(r"\d+\.\s+\*\*(.+?)\*\*", prompt)[:3] or ["a distant domain"]
        n = self._rng.randint(5, 8)
        lines = []
        for i in range(1, n + 1):
            dom = self._rng.choice(domain_names)
            verb = self._rng.choice(_DEMO_IDEA_VERBS)
            obj = self._rng.choice(_DEMO_IDEA_OBJECTS)
            mech = self._rng.choice(_DEMO_MECHANISMS)
            lines.append(
                f"{i}. **{verb} {obj} via {dom.lower()}.** "
                f"Borrowing from {dom.lower()}, which {mech}, this idea applies the same "
                f"structural mechanism to the brief. The transfer is concrete and testable: "
                f"the mechanism, not the metaphor, is what crosses over. "
                f"*[simulated demo idea]*"
            )
        return "\n\n".join(lines)

    def _scoring_response(self, prompt: str) -> str:
        nums = re.findall(r"(?:^|\n)(\d+)\.\s+", prompt.split("IDEAS TO EVALUATE")[-1])
        rows = ["| # | Orig. | Resist. | Thesis | Ground. | Cogn. | SCORE |",
                "|---|-------|---------|--------|---------|-------|-------|"]
        notes = []
        for num in nums:
            s = [round(self._rng.uniform(2.5, 5.0) * 2) / 2 for _ in range(5)]
            agg = round(s[0] * 0.25 + s[1] * 0.20 + s[2] * 0.20 + s[3] * 0.20 + s[4] * 0.15, 2)
            rows.append(f"| {num} | {s[0]} | {s[1]} | {s[2]} | {s[3]} | {s[4]} | **{agg}** |")
            if agg >= 4.0:
                notes.append(f"✓ Idea #{num} — Score {agg} — Strong structural transfer with a verifiable mechanism.")
        return "\n".join(rows) + "\n\n" + "\n".join(notes)


# ======================================================================
# RUN REGISTRY
# ======================================================================

class Run:
    def __init__(self, run_id: str, project: str, brainstorm_id: str, mode: str) -> None:
        self.run_id = run_id
        self.project = project
        self.brainstorm_id = brainstorm_id
        self.mode = mode
        self.status = "running"          # running | done | error
        self.events: list[dict] = []
        self.result: dict | None = None
        self.error: str | None = None
        self.started_at = datetime.now().isoformat()
        self._lock = threading.Lock()

    def emit(self, type_: str, **data) -> None:
        with self._lock:
            self.events.append({"type": type_, "ts": time.time(), **data})

    def snapshot(self, since: int = 0) -> dict:
        with self._lock:
            return {
                "run_id": self.run_id,
                "project": self.project,
                "brainstorm_id": self.brainstorm_id,
                "mode": self.mode,
                "status": self.status,
                "error": self.error,
                "result": self.result,
                "events": self.events[since:],
                "next_cursor": len(self.events),
            }


RUNS: dict[str, Run] = {}


def start_run(project_dir: Path, brainstorm_id: str, mode: str) -> Run:
    run = Run(uuid.uuid4().hex[:12], project_dir.name, brainstorm_id, mode)
    RUNS[run.run_id] = run
    thread = threading.Thread(
        target=_run_iteration, args=(run, project_dir), daemon=True
    )
    thread.start()
    return run


# ======================================================================
# STREAMING ITERATION
# ======================================================================

def _make_llm(mode: str):
    if mode == "demo":
        return DemoLLM()
    from open_collider.llm.client import LLMClient
    return LLMClient()


def _run_iteration(run: Run, project_dir: Path) -> None:
    try:
        llm = _make_llm(run.mode)
        state = init_iteration(str(project_dir), brainstorm_id=run.brainstorm_id)
        config = state["config"]
        iteration = state["iteration"]
        run.emit("init", iteration=iteration, brainstorm_id=run.brainstorm_id)

        # ---- Phase 1: Domains ----
        run.emit("phase", phase="domains")
        strategies_cfg = config.get("strategies", {})
        strategy_domain_yamls: dict[str, str] = {}
        strategy_to_ideas: dict[str, list[dict]] = {}

        for strat_name, strat_cfg in strategies_cfg.items():
            if not strat_cfg.get("enabled", True):
                continue
            if not _check_condition(strat_cfg.get("condition", "always"), state):
                continue
            prep = prepare_domain_prompt(strat_name, str(project_dir), state)
            if prep is None:
                continue
            run.emit("domains_start", strategy=strat_name)
            response = llm.call(model=prep["model"], prompt=prep["prompt"],
                                temperature=0.5, max_tokens=16000)
            yaml_str = parse_domain_response_text(response)
            strategy_domain_yamls[strat_name] = yaml_str
            bank = yaml.safe_load(yaml_str) or {}
            sets_summary = [
                {"id": sid, "name": s.get("name", sid),
                 "domains": [d.get("name", "") for d in (s.get("domains") or [])]}
                for sid, s in (bank.get("sets") or {}).items()
            ]
            run.emit("domains_done", strategy=strat_name,
                     n_sets=len(sets_summary), sets=sets_summary)

        if not strategy_domain_yamls:
            raise RuntimeError("No strategies produced domains")

        # ---- Phase 2: Collisions ----
        run.emit("phase", phase="collide")
        all_ideas: list[dict] = []
        max_concurrent = config.get("max_concurrent", 4)

        for strat_name, yaml_str in strategy_domain_yamls.items():
            combos = prepare_idea_prompts(str(project_dir), yaml_str, strat_name, state)
            run.emit("collide_start", strategy=strat_name, n_combos=len(combos))
            ideas = asyncio.run(_generate_parallel(run, llm, combos, max_concurrent))
            for idea in ideas:
                idea["strategy"] = strat_name
                idea["iteration"] = iteration
            strategy_to_ideas[strat_name] = ideas
            all_ideas.extend(ideas)
            run.emit("collide_strategy_done", strategy=strat_name,
                     n_ideas=len(ideas), total_ideas=len(all_ideas))

        if not all_ideas:
            raise RuntimeError("No ideas generated. Check domain quality and prompt template.")

        # ---- Phase 3: Scoring ----
        run.emit("phase", phase="score", total_ideas=len(all_ideas))
        batches = prepare_scoring_prompts(all_ideas, str(project_dir), state)
        max_scoring = config.get("max_concurrent_scoring", 3)
        run.emit("score_start", n_batches=len(batches), n_ideas=len(all_ideas))
        scored_ideas = asyncio.run(
            _score_parallel(run, llm, batches, config, max_scoring)
        )

        if len(scored_ideas) < len(all_ideas) * 0.5:
            raise RuntimeError(
                f"Scoring failed: only {len(scored_ideas)}/{len(all_ideas)} ideas scored"
            )

        # ---- Phase 4: Threshold + curate + finalize ----
        run.emit("phase", phase="curate")
        scored_ideas = apply_threshold(scored_ideas, config)
        retained = [i for i in scored_ideas if i.get("retained")]
        threshold_used = retained[0].get("threshold_used") if retained else config.get("score_threshold")

        result = finalize_iteration(
            str(project_dir), state, strategy_domain_yamls,
            all_ideas, scored_ideas, strategy_to_ideas,
        )

        curated = _curate(Path(state["iter_dir"]), retained, strategy_domain_yamls)
        mark_curated(str(project_dir))

        result["brainstorm_id"] = run.brainstorm_id
        result["curated"] = len(curated)
        result["threshold_used"] = threshold_used
        run.result = result
        run.status = "done"
        run.emit("done", **{k: v for k, v in result.items() if k != "strategies_detail"},
                 strategies_detail=result.get("strategies_detail", {}))

    except Exception as exc:  # surface everything to the UI
        logger.exception("Run %s failed", run.run_id)
        run.status = "error"
        run.error = str(exc)
        run.emit("error", message=str(exc))
        _cleanup_failed_iteration(locals().get("state"))


def _cleanup_failed_iteration(state: dict | None) -> None:
    """Remove the iter dir of a failed run if it never produced scored ideas."""
    if not state:
        return
    iter_dir = Path(state.get("iter_dir", ""))
    if iter_dir.is_dir() and not (iter_dir / "scored_ideas.json").is_file():
        import shutil
        shutil.rmtree(iter_dir, ignore_errors=True)


async def _generate_parallel(run: Run, llm, combos: list[dict], max_concurrent: int) -> list[dict]:
    semaphore = asyncio.Semaphore(max_concurrent)
    all_ideas: list[dict] = []
    done_count = 0
    lock = asyncio.Lock()

    async def _one(combo: dict) -> list[dict]:
        nonlocal done_count
        async with semaphore:
            try:
                response = await asyncio.to_thread(
                    llm.call, model=combo["model"], prompt=combo["prompt"],
                    temperature=0.9, max_tokens=4000,
                )
                ideas = parse_idea_response(combo, response)
            except Exception as exc:
                logger.warning("Combo %s failed: %s", combo["combo_id"], exc)
                ideas = []
            async with lock:
                done_count += 1
                run.emit("combo_done",
                         combo_id=combo["combo_id"],
                         text_id=combo["text_id"], set_id=combo["set_id"],
                         n_ideas=len(ideas),
                         combos_done=done_count, combos_total=len(combos))
            return ideas

    results = await asyncio.gather(*[_one(c) for c in combos])
    for r in results:
        all_ideas.extend(r)
    return all_ideas


async def _score_parallel(run: Run, llm, batches: list[dict], config: dict,
                          max_concurrent: int) -> list[dict]:
    semaphore = asyncio.Semaphore(max_concurrent)
    all_scored: list[dict] = []
    done_count = 0
    lock = asyncio.Lock()

    async def _one(batch: dict) -> list[dict]:
        nonlocal done_count
        async with semaphore:
            try:
                response = await asyncio.to_thread(
                    llm.call, model=batch["model"], prompt=batch["prompt"],
                    temperature=0.1, max_tokens=8000,
                )
                scored = parse_scoring_response(batch, response, config)
            except Exception as exc:
                logger.error("Batch %d failed: %s", batch["batch_id"], exc)
                scored = []
            async with lock:
                done_count += 1
                run.emit("batch_scored", batch_id=batch["batch_id"],
                         n_scored=len(scored),
                         batches_done=done_count, batches_total=len(batches))
            return scored

    results = await asyncio.gather(*[_one(b) for b in batches])
    for r in results:
        all_scored.extend(r)
    return all_scored


def _curate(iter_dir: Path, retained: list[dict],
            strategy_domain_yamls: dict[str, str]) -> list[dict]:
    """Top retained ideas by score -> curated_ideas.json (rank, score, source note)."""
    set_names: dict[str, str] = {}
    for yaml_str in strategy_domain_yamls.values():
        bank = yaml.safe_load(yaml_str) or {}
        for sid, s in (bank.get("sets") or {}).items():
            set_names[sid] = s.get("name", sid)

    top = sorted(retained, key=lambda i: i.get("score_aggregate", 0), reverse=True)
    curated = []
    for rank, idea in enumerate(top[:CURATED_TOP_N], 1):
        set_id = idea.get("set_id", "")
        curated.append({
            "idea_id": idea.get("idea_id", ""),
            "rank": rank,
            "score": idea.get("score_aggregate", 0),
            "text": idea.get("text", ""),
            "why_selected": idea.get("judge_note", ""),
            "source_note": (
                f"{idea.get('strategy', '?')} strategy · "
                f"{idea.get('text_id', '?')} × {set_names.get(set_id, set_id)}"
            ),
            "scores": idea.get("scores", {}),
            "strategy": idea.get("strategy", ""),
            "set_id": set_id,
            "text_id": idea.get("text_id", ""),
        })
    _save_json(iter_dir / "curated_ideas.json", curated)
    insights_path = iter_dir / "insights_without_collision.json"
    if not insights_path.is_file():
        _save_json(insights_path, [])
    return curated


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
