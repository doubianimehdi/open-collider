"""Skill interface: prepare prompts and parse responses for Claude Code orchestration.

The actual LLM calls are made by Claude Code (the skill), not by Python.
"""

from __future__ import annotations

import html
import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

import yaml

from open_collider.config import load_project_config
from open_collider.phases.idea_generator import IdeaGenerator, sample_combos
from open_collider.phases.idea_scorer import IdeaScorer, BATCH_SIZE
from open_collider.prompt_resolver import PromptResolver
from open_collider.scoring.data_loader import DataLoader
from open_collider.strategies.fresh import FreshStrategy, parse_domain_response
from open_collider.strategies.deepen import DeepenStrategy
from open_collider.strategies.refresh import RefreshStrategy

logger = logging.getLogger(__name__)


def _save_json(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ======================================================================
# STATE MANAGEMENT
# ======================================================================

def list_brainstorms(project_dir: str) -> list[dict]:
    """List all brainstorm sessions for a project."""
    brainstorms_dir = Path(project_dir) / "brainstorms"
    if not brainstorms_dir.is_dir():
        return []
    results = []
    for entry in sorted(brainstorms_dir.iterdir()):
        if entry.is_dir() and entry.name.startswith("brainstorm_"):
            iters = [d for d in entry.iterdir() if d.is_dir() and d.name.startswith("iter_")]
            loved_path = entry / "loved_ideas.json"
            liked_path = entry / "liked_ideas.json"
            n_loved = len(json.loads(loved_path.read_text())) if loved_path.is_file() else 0
            n_liked = len(json.loads(liked_path.read_text())) if liked_path.is_file() else 0
            results.append({
                "brainstorm_id": entry.name,
                "iterations": len(iters),
                "loved": n_loved,
                "liked": n_liked,
            })
    return results


def start_new_brainstorm(project_dir: str) -> str:
    """Reset state and create a new brainstorm directory."""
    project_path = Path(project_dir)
    brainstorms_dir = project_path / "brainstorms"
    brainstorms_dir.mkdir(parents=True, exist_ok=True)
    max_n = 0
    for entry in brainstorms_dir.iterdir():
        if entry.is_dir() and entry.name.startswith("brainstorm_"):
            try:
                n = int(entry.name.split("_")[1])
                max_n = max(max_n, n)
            except (ValueError, IndexError):
                pass
    new_id = f"brainstorm_{max_n + 1:03d}"
    (brainstorms_dir / new_id).mkdir()
    # Reset state
    state = _make_fresh_state(new_id)
    _save_state(project_path, state)
    return new_id


def init_iteration(project_dir: str, brainstorm_id: str | None = None) -> dict:
    """Initialize an iteration. Returns all state needed by the skill."""
    project_path = Path(project_dir)
    config = load_project_config(project_dir)
    state = _load_state(project_path)

    if brainstorm_id:
        brainstorm_dir = project_path / "brainstorms" / brainstorm_id
        if not brainstorm_dir.is_dir():
            raise FileNotFoundError(
                f"Brainstorm '{brainstorm_id}' not found in {project_path / 'brainstorms'}"
            )
        state["brainstorm_id"] = brainstorm_id
        # Recalculate current_iteration from the actual brainstorm dir
        existing_iters = [
            d for d in brainstorm_dir.iterdir()
            if d.is_dir() and d.name.startswith("iter_")
        ]
        state["current_iteration"] = len(existing_iters)
        _save_state(project_path, state)

    if not state.get("brainstorm_id"):
        start_new_brainstorm(project_dir)
        state = _load_state(project_path)

    brainstorm_dir = project_path / "brainstorms" / state["brainstorm_id"]
    iteration = state["current_iteration"] + 1
    iter_dir = brainstorm_dir / f"iter_{iteration:03d}"
    iter_dir.mkdir(parents=True, exist_ok=True)

    brief = _load_brief(project_path)
    text_bank = _load_text_bank(project_path)
    domain_history = _load_domain_history(brainstorm_dir)
    loved, liked = _load_loved_liked(brainstorm_dir)

    return {
        "iteration": iteration,
        "brainstorm_dir": str(brainstorm_dir),
        "iter_dir": str(iter_dir),
        "brief": brief,
        "text_bank": text_bank,
        "domain_history": domain_history,
        "loved_ideas": loved,
        "liked_ideas": liked,
        "config": config,
        "has_loved": len(loved) > 0,
        "has_liked": len(liked) > 0,
    }


# ======================================================================
# DOMAIN GENERATION
# ======================================================================

def prepare_domain_prompt(strategy: str, project_dir: str, state: dict) -> dict | None:
    """Build a domain generation prompt."""
    config = state["config"]
    brief = state["brief"]
    domain_history = state["domain_history"]
    loved = state["loved_ideas"]
    liked = state["liked_ideas"]

    if strategy == "fresh":
        result = FreshStrategy().build_prompt(domain_history, brief, config)
    elif strategy == "deepen":
        result = DeepenStrategy().build_prompt(loved, domain_history, brief, config)
    elif strategy == "refresh":
        result = RefreshStrategy().build_prompt(loved, liked, brief, config)
    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    if result is None:
        return None
    return {"prompt": result["prompt"], "model": result["model"], "strategy": strategy}


def parse_domain_response_text(response: str) -> str:
    """Parse LLM domain response into validated YAML string."""
    return parse_domain_response(response)


# ======================================================================
# IDEA GENERATION
# ======================================================================

def prepare_idea_prompts(
    project_dir: str,
    domain_bank_yaml: str,
    strategy_name: str,
    state: dict,
) -> list[dict]:
    """Build all idea generation prompts for one strategy."""
    project_path = Path(project_dir)
    config = state["config"]
    iter_dir = Path(state["iter_dir"])
    domains_dir = iter_dir / "domains"
    domains_dir.mkdir(parents=True, exist_ok=True)
    (domains_dir / f"{strategy_name}.yaml").write_text(domain_bank_yaml, encoding="utf-8")

    domain_bank = yaml.safe_load(domain_bank_yaml) or {}
    text_bank = state["text_bank"]

    data_loader = DataLoader(
        base_dir=str(Path(__file__).resolve().parent / "data"),
        project_dir=project_path,
        domain_bank_data=domain_bank,
    )

    prompt_resolver = PromptResolver(project_path)
    gen = IdeaGenerator(config, prompt_resolver)

    # Determine combo count
    strategies_cfg = config.get("strategies", {})
    is_first = state["iteration"] == 1 and not state["has_loved"]
    n_combos = config.get("combos_first_iteration", 24) if is_first else strategies_cfg.get(strategy_name, {}).get("combos", 12)

    text_ids = list(text_bank.get("text_inputs", {}).keys())
    set_ids = list(domain_bank.get("sets", {}).keys())
    stratified = config.get("stratified_sampling", True)
    all_combos = sample_combos(text_ids, set_ids, n_combos, stratified=stratified)

    model = config.get("generation_model", "claude-sonnet-4-20250514")

    strategy_dir = iter_dir / f"strategy_{strategy_name}"
    strategy_dir.mkdir(parents=True, exist_ok=True)

    prompts = []
    for t_id, s_id in all_combos:
        combo = f"{t_id}_{strategy_name}_{s_id}"
        collision_id = f"{combo}_{uuid.uuid4().hex[:8]}"
        cell_dir = strategy_dir / collision_id
        cell_dir.mkdir(parents=True, exist_ok=True)

        prompt = gen.assemble_prompt(t_id, s_id, data_loader)

        # Save prompt for reproducibility
        (cell_dir / "prompt.md").write_text(prompt, encoding="utf-8")

        prompts.append({
            "combo_id": combo,
            "collision_id": collision_id,
            "prompt": prompt,
            "model": model,
            "text_id": t_id,
            "set_id": s_id,
            "cell_dir": str(cell_dir),
        })
    return prompts


def parse_idea_response(combo_info: dict, response: str) -> list[dict]:
    """Parse one combo's LLM response into idea dicts."""
    combo = combo_info["combo_id"]
    collision_id = combo_info["collision_id"]

    # Save raw response for reproducibility
    cell_dir = combo_info.get("cell_dir")
    if cell_dir:
        cell_path = Path(cell_dir)
        cell_path.mkdir(parents=True, exist_ok=True)
        model_short = combo_info.get("model", "unknown").split("-")[0]
        (cell_path / f"response_{model_short}.md").write_text(response, encoding="utf-8")

    gen = IdeaGenerator({}, None)
    ideas = gen.parse_response(response, combo)

    for idea in ideas:
        idea["collision_id"] = collision_id
        idea["idea_id"] = f"{collision_id}_{idea['idea_num']}"
        idea["gen_model"] = combo_info.get("model", "")

    return ideas


# ======================================================================
# SCORING
# ======================================================================

def prepare_scoring_prompts(ideas: list[dict], project_dir: str, state: dict) -> list[dict]:
    """Build scoring prompts in batches."""
    config = state["config"]
    project_path = Path(project_dir)
    prompt_resolver = PromptResolver(project_path)
    scorer = IdeaScorer(config, prompt_resolver)

    judge_config = _load_judge_config(project_path)
    ref_high = judge_config.get("ref_high", judge_config.get("ref_haute", []))
    ref_low = judge_config.get("ref_low", judge_config.get("ref_basse", []))

    # Global renumbering
    global_ideas = []
    for idx, idea in enumerate(ideas, 1):
        gi = dict(idea)
        gi["_global_num"] = idx
        gi["_orig_idea_num"] = idea["idea_num"]
        global_ideas.append(gi)

    batch_size = config.get("scoring_batch_size", BATCH_SIZE)
    batches = [global_ideas[i:i + batch_size] for i in range(0, len(global_ideas), batch_size)]
    model = config.get("scoring_model", "claude-sonnet-4-20250514")

    prompts = []
    for batch_id, batch in enumerate(batches):
        prompt = scorer.assemble_prompt(batch, ref_high, ref_low)
        prompts.append({
            "batch_id": batch_id,
            "prompt": prompt,
            "model": model,
            "ideas_in_batch": batch,
        })
    return prompts


def parse_scoring_response(batch_info: dict, response: str, config: dict) -> list[dict]:
    """Parse one scoring batch. Recalculates aggregate. Does NOT set retained."""
    scorer = IdeaScorer(config)
    return scorer.parse_response(response, batch_info["ideas_in_batch"])


# ======================================================================
# FINALIZATION
# ======================================================================

def finalize_iteration(
    project_dir: str,
    state: dict,
    strategy_domain_yamls: dict[str, str],
    all_ideas: list[dict],
    scored_ideas: list[dict],
    strategy_to_ideas: dict[str, list[dict]],
) -> dict:
    """Save all results, update state, generate REPORT.md."""
    project_path = Path(project_dir)
    config = state["config"]
    brainstorm_dir = Path(state["brainstorm_dir"])
    iter_dir = Path(state["iter_dir"])
    iteration = state["iteration"]

    # NOTE: caller is responsible for calling apply_threshold() before this function.
    # scored_ideas should already have 'retained' field set.

    # Save scored ideas
    _save_json(iter_dir / "scored_ideas.json", scored_ideas)

    retained = [i for i in scored_ideas if i.get("retained")]

    # Update domain history (fresh only)
    if "fresh" in strategy_domain_yamls:
        _update_domain_history(brainstorm_dir, strategy_domain_yamls["fresh"])

    # Build strategies detail
    strategies_detail = {}
    for strat_name, yaml_str in strategy_domain_yamls.items():
        bank = yaml.safe_load(yaml_str) or {}
        n_ideas = len(strategy_to_ideas.get(strat_name, []))
        strategies_detail[strat_name] = {
            "n_sets": len(bank.get("sets", {})),
            "n_ideas": n_ideas,
        }

    # Save iter config with effective config snapshot
    from open_collider.phases.idea_scorer import DEFAULT_WEIGHTS
    _save_json(iter_dir / "config.json", {
        "iteration": iteration,
        "strategies_used": list(strategy_domain_yamls.keys()),
        "strategies_detail": strategies_detail,
        "ideas_generated": len(all_ideas),
        "ideas_retained": len(retained),
        "timestamp": datetime.now().isoformat(),
        "effective_config": {
            "scoring_axes": config.get("judge_axes", DEFAULT_WEIGHTS),
            "score_threshold": config.get("score_threshold"),
            "models": {
                "domain": config.get("domain_model"),
                "generation": config.get("generation_model"),
                "scoring": config.get("scoring_model"),
            },
        },
    })

    # Update brainstorm state
    bs_state = _load_state(project_path)
    bs_state["current_iteration"] = iteration
    bs_state["status"] = "awaiting_curation"
    bs_state["total_ideas_generated"] = bs_state.get("total_ideas_generated", 0) + len(all_ideas)
    bs_state["last_activity"] = datetime.now().isoformat()
    _save_state(project_path, bs_state)

    # Generate/update REPORT.md
    generate_iter_html_report(project_dir, iteration)
    generate_report(project_dir, state)

    return {
        "iteration": iteration,
        "ideas_generated": len(all_ideas),
        "ideas_retained": len(retained),
        "strategies_detail": strategies_detail,
    }


def apply_flags(project_dir: str, iteration: int, flags: dict) -> None:
    """Save flags and rebuild loved/liked stores. Sets status to 'ready'."""
    project_path = Path(project_dir)
    bs_state = _load_state(project_path)
    brainstorm_dir = project_path / "brainstorms" / bs_state["brainstorm_id"]
    iter_dir = brainstorm_dir / f"iter_{iteration:03d}"

    _save_json(iter_dir / "flags.json", flags)

    # Rebuild loved/liked from ALL iterations' flags + scored_ideas
    loved, liked = [], []
    for idir in sorted(brainstorm_dir.iterdir()):
        if not idir.is_dir() or not idir.name.startswith("iter_"):
            continue
        flags_path = idir / "flags.json"
        scored_path = idir / "scored_ideas.json"
        if not flags_path.is_file() or not scored_path.is_file():
            continue
        iter_flags = json.loads(flags_path.read_text())
        scored = json.loads(scored_path.read_text())
        id_to_idea = {i["idea_id"]: i for i in scored}
        for idea_id, flag in iter_flags.items():
            idea = id_to_idea.get(idea_id)
            if not idea:
                continue
            if flag in ("loved", "love"):
                loved.append(idea)
            elif flag in ("liked", "like"):
                liked.append(idea)

    _save_json(brainstorm_dir / "loved_ideas.json", loved)
    _save_json(brainstorm_dir / "liked_ideas.json", liked)

    bs_state["status"] = "ready"
    bs_state["total_loved"] = len(loved)
    bs_state["total_liked"] = len(liked)
    bs_state["last_activity"] = datetime.now().isoformat()
    _save_state(project_path, bs_state)

    # Generate iteration report
    generate_iter_report(project_dir, iteration)
    generate_iter_html_report(project_dir, iteration)
    generate_report(project_dir)


def mark_curated(project_dir: str) -> None:
    """Set status to awaiting_flags after curation."""
    project_path = Path(project_dir)
    bs_state = _load_state(project_path)
    bs_state["status"] = "awaiting_flags"
    bs_state["last_activity"] = datetime.now().isoformat()
    _save_state(project_path, bs_state)


def generate_iter_report(project_dir: str, iteration: int) -> str:
    """Generate iter_NNN/ITER_REPORT.md: all curated ideas with their flags.

    Called after flags are applied. Shows every curated idea with its flag status.
    """
    project_path = Path(project_dir)
    bs_state = _load_state(project_path)
    brainstorm_dir = project_path / "brainstorms" / bs_state.get("brainstorm_id", "")
    iter_dir = brainstorm_dir / f"iter_{iteration:03d}"

    curated_path = iter_dir / "curated_ideas.json"
    insights_path = iter_dir / "insights_without_collision.json"
    flags_path = iter_dir / "flags.json"
    config_path = iter_dir / "config.json"

    curated = json.loads(curated_path.read_text()) if curated_path.is_file() else []
    insights = json.loads(insights_path.read_text()) if insights_path.is_file() else []
    flags = json.loads(flags_path.read_text()) if flags_path.is_file() else {}
    iter_cfg = json.loads(config_path.read_text()) if config_path.is_file() else {}

    lines = [f"# Iteration {iteration} Report", ""]
    strategies = ", ".join(iter_cfg.get("strategies_used", []))
    lines.append(f"**Strategies:** {strategies}")
    lines.append(
        f"**Generated:** {iter_cfg.get('ideas_generated', '?')} | "
        f"**Retained:** {iter_cfg.get('ideas_retained', '?')} | "
        f"**Curated:** {len(curated)} | "
        f"**Insights without collision:** {len(insights)}"
    )

    n_loved = sum(1 for v in flags.values() if v in ("loved", "love"))
    n_liked = sum(1 for v in flags.values() if v in ("liked", "like"))
    n_trashed = len(flags) - n_loved - n_liked
    lines.append(f"**Flags:** {n_loved} loved, {n_liked} liked, {n_trashed} trashed")

    fb_path = iter_dir / "feedback.txt"
    if fb_path.is_file():
        lines.append(f"\n**Feedback:** {fb_path.read_text(encoding='utf-8').strip()}")

    lines.append("\n---\n")

    if curated:
        lines.append(f"## Curated Ideas ({len(curated)})")
        lines.append("")
        for c in curated:
            idea_id = c.get("idea_id", "")
            flag = flags.get(idea_id, "unflagged")
            flag_label = {"loved": "❤️ LOVED", "liked": "👍 LIKED", "trashed": "🗑️ TRASHED"}.get(flag, "")

            lines.append(f"### #{c.get('rank', '?')} [{c.get('score', '?')}] {flag_label}")
            lines.append(f"\n{c.get('text', '')}")
            if c.get("why_selected"):
                lines.append(f"\n**Why selected:** {c['why_selected']}")
            if c.get("source_note"):
                lines.append(f"**Source:** {c['source_note']}")
            if c.get("challenge"):
                lines.append(f"**Challenge:** {c['challenge']}")
            lines.append("")

    if insights:
        lines.append("---\n")
        lines.append(f"## Insights Without Collision ({len(insights)})")
        lines.append("")
        lines.append("*Curator pass 2: high-signal observations that did not arise from a true bisociation but are still worth surfacing.*")
        lines.append("")
        for c in insights:
            idea_id = c.get("idea_id", "")
            flag = flags.get(idea_id, "unflagged")
            flag_label = {"loved": "❤️ LOVED", "liked": "👍 LIKED", "trashed": "🗑️ TRASHED"}.get(flag, "")

            lines.append(f"### #{c.get('rank', '?')} [{c.get('score', '?')}] {flag_label}")
            lines.append(f"\n{c.get('text', '')}")
            if c.get("why_kept"):
                lines.append(f"\n**Why kept:** {c['why_kept']}")
            lines.append("")

    report = "\n".join(lines)
    (iter_dir / "ITER_REPORT.md").write_text(report, encoding="utf-8")
    return report


def generate_iter_html_report(project_dir: str, iteration: int) -> str:
    """Generate iter_NNN/ITER_REPORT.html for quick browser review."""
    project_path = Path(project_dir)
    bs_state = _load_state(project_path)
    brainstorm_dir = project_path / "brainstorms" / bs_state.get("brainstorm_id", "")
    iter_dir = brainstorm_dir / f"iter_{iteration:03d}"

    config_path = iter_dir / "config.json"
    scored_path = iter_dir / "scored_ideas.json"
    curated_path = iter_dir / "curated_ideas.json"
    insights_path = iter_dir / "insights_without_collision.json"
    flags_path = iter_dir / "flags.json"

    iter_cfg = _load_json_if_exists(config_path, {})
    scored = _load_json_if_exists(scored_path, [])
    curated = _load_json_if_exists(curated_path, [])
    insights = _load_json_if_exists(insights_path, [])
    flags = _load_json_if_exists(flags_path, {})
    numbering = _load_numbering_map(iter_dir)
    retained = sorted(
        [idea for idea in scored if idea.get("retained")],
        key=lambda idea: idea.get("score_aggregate", 0),
        reverse=True,
    )

    title = f"{project_path.name}: iteration {iteration}"
    body = [
        _html_header(title),
        "<main class=\"shell\">",
        "<div class=\"page-frame\" aria-hidden=\"true\"></div>",
        f"<p class=\"eyebrow\">Open Collider report · { _e(project_path.name) }</p>",
        f"<h1>Iteration {iteration}</h1>",
        f"<p class=\"dek\">{_e(brainstorm_dir.name)} · same source material, scored and curated through distant-domain collision.</p>",
        "<section class=\"summary-grid\">",
        _metric("Generated", iter_cfg.get("ideas_generated", len(scored))),
        _metric("Retained", iter_cfg.get("ideas_retained", len(retained))),
        _metric("Curated", len(curated)),
        _metric("Insights", len(insights)),
        "</section>",
    ]
    if curated:
        body.append(_render_idea_section(
            "Curated Ideas",
            curated,
            flags,
            numbering,
            section_label="Agent curation",
            section_class="curated-priority",
            highlighted=True,
        ))
        if insights:
            body.append(_render_idea_section(
                "Insights Without Collision",
                insights,
                flags,
                numbering,
                section_label="Useful but less collision-shaped",
                section_class="insights-compact",
            ))
    elif insights:
        body.append(_render_idea_section(
            "Insights Without Collision",
            insights,
            flags,
            numbering,
            section_label="Useful but less collision-shaped",
            section_class="insights-compact",
        ))
    if retained:
        body.append(_render_idea_section(
            "Raw Retained Pool",
            retained,
            flags,
            section_label="Scored pool",
            section_class="raw-pool",
        ))
    body.extend(["</main>", "</body></html>"])

    report = "\n".join(body)
    (iter_dir / "ITER_REPORT.html").write_text(report, encoding="utf-8")
    return report


def generate_brainstorm_report(project_dir: str) -> str:
    """Generate brainstorm_NNN/REPORT.md: aggregated across all iterations.

    Called when closing the session. Loved/liked ideas on top, trashed below.
    """
    project_path = Path(project_dir)
    bs_state = _load_state(project_path)
    brainstorm_dir = project_path / "brainstorms" / bs_state.get("brainstorm_id", "")

    # Collect data from all iterations
    iter_summaries = []
    all_loved = []
    all_liked = []
    all_trashed = []
    all_insights = []
    all_feedback = []

    for idir in sorted(brainstorm_dir.iterdir()):
        if not idir.is_dir() or not idir.name.startswith("iter_"):
            continue
        config_path = idir / "config.json"
        if not config_path.is_file():
            continue

        iter_cfg = json.loads(config_path.read_text())
        curated_path = idir / "curated_ideas.json"
        insights_path = idir / "insights_without_collision.json"
        flags_path = idir / "flags.json"
        fb_path = idir / "feedback.txt"

        curated = json.loads(curated_path.read_text()) if curated_path.is_file() else []
        insights = json.loads(insights_path.read_text()) if insights_path.is_file() else []
        flags = json.loads(flags_path.read_text()) if flags_path.is_file() else {}

        n_loved = sum(1 for v in flags.values() if v in ("loved", "love"))
        n_liked = sum(1 for v in flags.values() if v in ("liked", "like"))
        n_trashed = len(flags) - n_loved - n_liked

        iter_summaries.append({
            "iteration": iter_cfg.get("iteration", "?"),
            "generated": iter_cfg.get("ideas_generated", 0),
            "retained": iter_cfg.get("ideas_retained", 0),
            "curated": len(curated),
            "insights": len(insights),
            "loved": n_loved,
            "liked": n_liked,
            "trashed": n_trashed,
        })

        for c in curated:
            idea_id = c.get("idea_id", "")
            flag = flags.get(idea_id, "trashed")
            entry = {**c, "flag": flag, "iteration": iter_cfg.get("iteration", "?")}
            if flag in ("loved", "love"):
                all_loved.append(entry)
            elif flag in ("liked", "like"):
                all_liked.append(entry)
            else:
                all_trashed.append(entry)

        for c in insights:
            idea_id = c.get("idea_id", "")
            flag = flags.get(idea_id, "unflagged")
            all_insights.append({**c, "flag": flag, "iteration": iter_cfg.get("iteration", "?")})

        if fb_path.is_file():
            fb_text = fb_path.read_text(encoding="utf-8").strip()
            if fb_text:
                all_feedback.append((iter_cfg.get("iteration", "?"), fb_text))

    # Build report
    lines = [f"# {project_path.name}: {brainstorm_dir.name}", ""]
    lines.append(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append("| Iter | Generated | Retained | Curated | Insights | Loved | Liked | Trashed |")
    lines.append("|------|-----------|----------|---------|----------|-------|-------|---------|")
    for s in iter_summaries:
        lines.append(
            f"| {s['iteration']} | {s['generated']} | {s['retained']} | {s['curated']} | "
            f"{s['insights']} | {s['loved']} | {s['liked']} | {s['trashed']} |"
        )
    lines.append("")

    # Feedback
    if all_feedback:
        lines.append("## Feedback")
        lines.append("")
        for iter_num, fb in all_feedback:
            lines.append(f"- **Iter {iter_num}:** {fb}")
        lines.append("")

    # Loved ideas
    if all_loved:
        lines.append("---")
        lines.append("")
        lines.append(f"## Loved Ideas ({len(all_loved)})")
        lines.append("")
        for c in all_loved:
            lines.append(f"### [{c.get('score', '?')}] (iter {c['iteration']})")
            lines.append(f"\n{c.get('text', '')}")
            if c.get("why_selected"):
                lines.append(f"\n**Why selected:** {c['why_selected']}")
            if c.get("source_note"):
                lines.append(f"**Source:** {c['source_note']}")
            if c.get("challenge"):
                lines.append(f"**Challenge:** {c['challenge']}")
            lines.append("")

    # Liked ideas
    if all_liked:
        lines.append("---")
        lines.append("")
        lines.append(f"## Liked Ideas ({len(all_liked)})")
        lines.append("")
        for c in all_liked:
            lines.append(f"### [{c.get('score', '?')}] (iter {c['iteration']})")
            lines.append(f"\n{c.get('text', '')}")
            if c.get("why_selected"):
                lines.append(f"\n**Why selected:** {c['why_selected']}")
            lines.append("")

    # Trashed ideas (shorter format)
    if all_trashed:
        lines.append("---")
        lines.append("")
        lines.append(f"## Trashed Ideas ({len(all_trashed)})")
        lines.append("")
        for c in all_trashed:
            # First line of text only as summary
            first_line = c.get("text", "").split("\n")[0][:150]
            lines.append(f"- [{c.get('score', '?')}] (iter {c['iteration']}) {first_line}")
        lines.append("")

    # Insights without collision (curator pass 2, kept separate from the curated pool)
    if all_insights:
        lines.append("---")
        lines.append("")
        lines.append(f"## Insights Without Collision ({len(all_insights)})")
        lines.append("")
        lines.append("*High-signal observations that did not arise from a true bisociation but are still worth surfacing. Aggregated across all iterations.*")
        lines.append("")
        for c in all_insights:
            flag = c.get("flag", "unflagged")
            flag_label = {"loved": "❤️ LOVED", "liked": "👍 LIKED", "trashed": "🗑️ TRASHED"}.get(flag, "")
            lines.append(f"### [{c.get('score', '?')}] (iter {c['iteration']}) {flag_label}")
            lines.append(f"\n{c.get('text', '')}")
            if c.get("why_kept"):
                lines.append(f"\n**Why kept:** {c['why_kept']}")
            lines.append("")

    report = "\n".join(lines)
    (brainstorm_dir / "REPORT.md").write_text(report, encoding="utf-8")
    _write_brainstorm_html_report(project_path, brainstorm_dir, iter_summaries)
    for summary in iter_summaries:
        if isinstance(summary.get("iteration"), int):
            generate_iter_html_report(project_dir, summary["iteration"])
    return report


def generate_report(project_dir: str, state: dict | None = None) -> str:
    """Backward-compatible wrapper: generates the brainstorm report."""
    return generate_brainstorm_report(project_dir)


def _write_brainstorm_html_report(
    project_path: Path,
    brainstorm_dir: Path,
    iter_summaries: list[dict],
) -> str:
    """Write brainstorm_NNN/REPORT.html with all retained ideas by iteration."""
    title = f"{project_path.name}: {brainstorm_dir.name}"
    body = [
        _html_header(title),
        "<main class=\"shell\">",
        "<div class=\"page-frame\" aria-hidden=\"true\"></div>",
        f"<p class=\"eyebrow\">Open Collider report · { _e(project_path.name) }</p>",
        f"<h1>{_e(brainstorm_dir.name)}</h1>",
        f"<p class=\"dek\">Last updated: {_e(datetime.now().strftime('%Y-%m-%d %H:%M'))}. Aggregated brainstorm report with raw retained ideas, curation, and flagging state.</p>",
        "<section class=\"summary-table-wrap\">",
        "<h2>Summary</h2>",
        "<table class=\"summary-table\">",
        "<thead><tr><th>Iter</th><th>Generated</th><th>Retained</th><th>Curated</th>"
        "<th>Insights</th><th>Loved</th><th>Liked</th><th>Trashed</th></tr></thead>",
        "<tbody>",
    ]

    for summary in iter_summaries:
        body.append(
            "<tr>"
            f"<td>{_e(summary.get('iteration', '?'))}</td>"
            f"<td>{_e(summary.get('generated', 0))}</td>"
            f"<td>{_e(summary.get('retained', 0))}</td>"
            f"<td>{_e(summary.get('curated', 0))}</td>"
            f"<td>{_e(summary.get('insights', 0))}</td>"
            f"<td>{_e(summary.get('loved', 0))}</td>"
            f"<td>{_e(summary.get('liked', 0))}</td>"
            f"<td>{_e(summary.get('trashed', 0))}</td>"
            "</tr>"
        )

    body.extend(["</tbody></table>", "</section>"])

    for summary in iter_summaries:
        iteration = summary.get("iteration")
        if not isinstance(iteration, int):
            continue
        iter_dir = brainstorm_dir / f"iter_{iteration:03d}"
        scored = _load_json_if_exists(iter_dir / "scored_ideas.json", [])
        curated = _load_json_if_exists(iter_dir / "curated_ideas.json", [])
        insights = _load_json_if_exists(iter_dir / "insights_without_collision.json", [])
        flags = _load_json_if_exists(iter_dir / "flags.json", {})
        numbering = _load_numbering_map(iter_dir)
        retained = sorted(
            [idea for idea in scored if idea.get("retained")],
            key=lambda idea: idea.get("score_aggregate", 0),
            reverse=True,
        )

        body.append(
            f"<section class=\"iteration\"><div class=\"iteration-heading\">"
            f"<p class=\"eyebrow\">Iteration {iteration}</p>"
            f"<h2>Curated first, raw pool last</h2>"
            "</div>"
        )
        if curated:
            body.append(_render_idea_section(
                "Curated Ideas",
                curated,
                flags,
                numbering,
                section_label="Agent curation",
                section_class="curated-priority",
                highlighted=True,
            ))
            if insights:
                body.append(_render_idea_section(
                    "Insights Without Collision",
                    insights,
                    flags,
                    numbering,
                    section_label="Useful but less collision-shaped",
                    section_class="insights-compact",
                ))
        elif insights:
            body.append(_render_idea_section(
                "Insights Without Collision",
                insights,
                flags,
                numbering,
                section_label="Useful but less collision-shaped",
                section_class="insights-compact",
            ))
        if retained:
            body.append(_render_idea_section(
                "Raw Retained Pool",
                retained,
                flags,
                section_label="Scored pool",
                section_class="raw-pool",
            ))
        body.append("</section>")

    body.extend(["</main>", "</body></html>"])
    report = "\n".join(body)
    (brainstorm_dir / "REPORT.html").write_text(report, encoding="utf-8")
    return report


def _html_header(title: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_e(title)}</title>
  <style>
    :root {{
      --paper: #efede4;
      --paper-warm: #e6e2d6;
      --card: #f7f5ef;
      --ink: #191917;
      --body: #4f4e49;
      --muted: #77736c;
      --line: #2c2a26;
      --hairline: #d5d0c4;
      --accent: #d9775c;
      --accent-dark: #a95542;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: Georgia, "Times New Roman", ui-serif, serif;
      line-height: 1.55;
    }}
    .shell {{
      position: relative;
      width: min(1360px, calc(100vw - 48px));
      margin: 0 auto;
      padding: 58px 0 70px;
    }}
    .page-frame::before,
    .page-frame::after {{
      content: "";
      position: fixed;
      width: 22px;
      height: 22px;
      pointer-events: none;
      z-index: 1;
    }}
    .page-frame::before {{
      left: 24px;
      top: 24px;
      border-left: 2px solid var(--accent);
      border-top: 2px solid var(--accent);
    }}
    .page-frame::after {{
      right: 24px;
      bottom: 24px;
      border-right: 2px solid var(--accent);
      border-bottom: 2px solid var(--accent);
    }}
    .eyebrow {{
      margin: 0 0 18px;
      color: var(--accent);
      font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
      font-size: 14px;
      font-weight: 800;
      letter-spacing: .16em;
      text-transform: uppercase;
    }}
    h1 {{
      max-width: 1100px;
      margin: 0 0 24px;
      font-size: clamp(42px, 5.2vw, 78px);
      line-height: 1.03;
      letter-spacing: 0;
      text-wrap: balance;
    }}
    h2 {{
      margin: 0 0 8px;
      font-size: clamp(28px, 2.8vw, 44px);
      line-height: 1.06;
      letter-spacing: 0;
      text-wrap: balance;
    }}
    h3 {{
      margin: 0;
      font-size: 23px;
      line-height: 1.12;
      letter-spacing: 0;
      text-wrap: pretty;
    }}
    .dek {{
      max-width: 860px;
      margin: 0 0 36px;
      color: var(--muted);
      font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
      font-size: 15px;
      font-weight: 700;
    }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 1px;
      margin: 34px 0 42px;
      border-top: 2px solid var(--line);
      border-bottom: 2px solid var(--line);
      background: var(--hairline);
    }}
    .metric {{
      padding: 18px 20px;
      background: var(--paper);
    }}
    .metric-value {{
      display: block;
      margin-bottom: 4px;
      font-size: 34px;
      font-weight: 800;
      line-height: 1;
    }}
    .metric-label {{
      color: var(--muted);
      font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
      font-size: 12px;
      font-weight: 800;
      letter-spacing: .14em;
      text-transform: uppercase;
    }}
    .summary-table-wrap {{
      margin: 34px 0 42px;
      padding: 22px 0 8px;
      overflow-x: auto;
      border-top: 2px solid var(--line);
      border-bottom: 2px solid var(--line);
    }}
    .summary-table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 720px;
      font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
      font-size: 13px;
    }}
    .summary-table th, .summary-table td {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--hairline);
      text-align: left;
    }}
    .summary-table th {{
      color: var(--accent-dark);
      font-size: 12px;
      letter-spacing: .12em;
      text-transform: uppercase;
    }}
    .iteration {{
      margin-top: 48px;
    }}
    .iteration-heading {{
      padding-bottom: 22px;
    }}
    .idea-section {{
      margin: 44px 0;
    }}
    .curated-priority {{
      margin-top: 42px;
      padding: 34px 38px 38px;
      border-top: 2px solid var(--line);
      border-bottom: 2px solid var(--line);
      background: var(--paper-warm);
    }}
    .curated-priority .idea-card {{
      background: var(--card);
    }}
    .insights-compact {{
      margin-top: 34px;
      padding-top: 26px;
      border-top: 1px solid var(--hairline);
    }}
    .insights-compact .idea-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px 24px;
    }}
    .insights-compact .idea-card {{
      grid-template-columns: 46px minmax(0, 1fr);
      padding-top: 18px;
      padding-bottom: 18px;
      background: color-mix(in srgb, var(--card) 58%, transparent);
    }}
    .insights-compact h3 {{
      font-size: 20px;
    }}
    .insights-compact .idea-body {{
      font-size: 16px;
    }}
    .raw-pool {{
      margin-top: 54px;
      padding-top: 28px;
      border-top: 1px solid var(--hairline);
    }}
    .raw-pool .idea-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px 24px;
    }}
    .raw-pool h2,
    .raw-pool .section-subtitle {{
      color: var(--muted);
    }}
    .raw-pool .idea-card {{
      background: transparent;
    }}
    .raw-pool .idea-body {{
      font-size: 16px;
    }}
    .section-kicker {{
      margin: 0 0 8px;
      color: var(--accent);
      font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
      font-size: 13px;
      font-weight: 800;
      letter-spacing: .15em;
      text-transform: uppercase;
    }}
    .section-subtitle {{
      margin: 0 0 22px;
      color: var(--muted);
      font-size: 17px;
      font-style: italic;
    }}
    .idea-grid {{
      display: flex;
      flex-direction: column;
      gap: 22px;
    }}
    .idea-card {{
      position: relative;
      display: grid;
      grid-template-columns: 54px minmax(0, 1fr);
      gap: 18px;
      padding: 24px 26px 24px 0;
      background: color-mix(in srgb, var(--card) 82%, transparent);
    }}
    .idea-card::before {{
      content: "";
      position: absolute;
      left: 0;
      top: 0;
      bottom: 0;
      width: 2px;
      background: var(--line);
    }}
    .idea-card.is-highlighted::before {{
      background: var(--accent);
    }}
    .idea-number {{
      padding-top: 4px;
      color: var(--accent);
      font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
      font-size: 15px;
      font-weight: 800;
      text-align: right;
      letter-spacing: .12em;
    }}
    .idea-content {{
      min-width: 0;
    }}
    .idea-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 12px 0 14px;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 2px 0;
      color: var(--accent);
      font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: .08em;
      text-transform: uppercase;
    }}
    .pill + .pill::before {{
      content: "/";
      margin-right: 8px;
      color: var(--hairline);
    }}
    .score {{ color: var(--accent-dark); }}
    .idea-body {{
      max-width: 72ch;
      color: var(--body);
      font-size: 18px;
    }}
    .idea-body p {{ margin: 9px 0; }}
    .idea-body strong {{
      color: var(--ink);
      font-weight: 800;
    }}
    .judge-note {{
      margin-top: 16px;
      color: var(--accent-dark);
      font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
      font-size: 13px;
      font-weight: 700;
      letter-spacing: .04em;
    }}
    @media (max-width: 900px) {{
      .shell {{ width: min(100vw - 24px, 1360px); padding-top: 34px; }}
      .curated-priority {{ padding: 28px 18px 30px; }}
      .insights-compact .idea-grid {{ grid-template-columns: 1fr; }}
      .raw-pool .idea-grid {{ grid-template-columns: 1fr; }}
      .idea-card {{
        grid-template-columns: 42px minmax(0, 1fr);
        padding-right: 12px;
      }}
      h1 {{ font-size: clamp(34px, 10vw, 54px); }}
      h2 {{ font-size: 30px; }}
      .page-frame::before,
      .page-frame::after {{ display: none; }}
    }}
  </style>
</head>
<body>"""


def _metric(label: str, value) -> str:
    return (
        "<div class=\"metric\">"
        f"<span class=\"metric-value\">{_e(value)}</span>"
        f"<span class=\"metric-label\">{_e(label)}</span>"
        "</div>"
    )


def _render_idea_section(
    title: str,
    ideas: list[dict],
    flags: dict | None = None,
    numbering: dict[str, int] | None = None,
    *,
    section_label: str | None = None,
    section_class: str | None = None,
    highlighted: bool = False,
) -> str:
    flags = flags or {}
    if not ideas:
        return ""
    numbering = numbering or {}
    cards = "\n".join(
        _render_idea_card(idea, flags, numbering, highlighted=highlighted)
        for idea in ideas
    )
    label_html = (
        f"<p class=\"section-kicker\">{_e(section_label)}</p>"
        if section_label
        else ""
    )
    class_attr = "idea-section"
    if section_class:
        class_attr = f"{class_attr} {section_class}"
    return (
        f"<section class=\"{_e(class_attr)}\">"
        f"{label_html}"
        f"<h2>{_e(title)}</h2>"
        f"<p class=\"section-subtitle\">{len(ideas)} ideas shown.</p>"
        f"<div class=\"idea-grid\">{cards}</div>"
        "</section>"
    )


def _render_idea_card(
    idea: dict,
    flags: dict,
    numbering: dict[str, int],
    *,
    highlighted: bool = False,
) -> str:
    text = idea.get("text", "")
    title = _extract_labeled_line(text, "Territory") or _first_nonempty_line(text) or "Idea"
    score = idea.get("score_aggregate", idea.get("score", "?"))
    idea_id = idea.get("idea_id", "")
    flag = flags.get(idea_id)
    display_number = _idea_display_number(idea, numbering)

    meta = [f"<span class=\"pill score\">Score {_e(score)}</span>"]
    if flag:
        meta.append(f"<span class=\"pill\">{_e(flag)}</span>")
    if idea.get("combo"):
        meta.append(f"<span class=\"pill\">{_e(idea['combo'])}</span>")

    note = idea.get("judge_note") or idea.get("why_selected") or idea.get("why_kept")
    note_html = f"<div class=\"judge-note\">{_e(note)}</div>" if note else ""
    card_class = "idea-card is-highlighted" if highlighted else "idea-card"

    return (
        f"<article class=\"{card_class}\">"
        f"<div class=\"idea-number\">{_e(display_number)}</div>"
        "<div class=\"idea-content\">"
        f"<h3>{_e(title)}</h3>"
        f"<div class=\"idea-meta\">{''.join(meta)}</div>"
        f"<div class=\"idea-body\">{_format_idea_text_html(text, title)}</div>"
        f"{note_html}"
        "</div>"
        "</article>"
    )


def _format_idea_text_html(text: str, title: str | None = None) -> str:
    lines = []
    skipped_title = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if (
            title
            and not skipped_title
            and _normalize_card_text(line) == _normalize_card_text(title)
        ):
            skipped_title = True
            continue
        skipped_title = True
        label, sep, value = line.partition(":")
        if sep and len(label) <= 28:
            lines.append(f"<p><strong>{_e(label)}:</strong> {_e(value.strip())}</p>")
        else:
            lines.append(f"<p>{_e(line)}</p>")
    return "\n".join(lines)


def _extract_labeled_line(text: str, label: str) -> str | None:
    prefix = f"{label}:"
    for line in text.splitlines():
        if line.strip().lower().startswith(prefix.lower()):
            return line.split(":", 1)[1].strip()
    return None


def _first_nonempty_line(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _normalize_card_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("*", "").strip()).lower()


def _load_json_if_exists(path: Path, default):
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def _load_numbering_map(iter_dir: Path) -> dict[str, int]:
    numbering = _load_json_if_exists(iter_dir / "numbering_map.json", [])
    if not isinstance(numbering, list):
        return {}
    return {
        str(entry.get("idea_id")): int(entry["number"])
        for entry in numbering
        if entry.get("idea_id") and isinstance(entry.get("number"), int)
    }


def _idea_display_number(idea: dict, numbering: dict[str, int]) -> str:
    idea_id = str(idea.get("idea_id", ""))
    if idea_id in numbering:
        return f"{numbering[idea_id]:02d}"
    for key in ("rank", "idea_num"):
        value = idea.get(key)
        if isinstance(value, int):
            return f"{value:02d}"
    return "·"


def _e(value) -> str:
    return html.escape(str(value), quote=True)


# ======================================================================
# PRIVATE HELPERS
# ======================================================================

def _make_fresh_state(brainstorm_id: str) -> dict:
    return {
        "current_iteration": 0,
        "brainstorm_id": brainstorm_id,
        "status": "new",
        "total_ideas_generated": 0,
        "total_loved": 0,
        "total_liked": 0,
        "created_at": datetime.now().isoformat(),
        "last_activity": datetime.now().isoformat(),
    }


def _load_state(project_path: Path) -> dict:
    state_path = project_path / "brainstorm_state.json"
    if state_path.is_file():
        return json.loads(state_path.read_text(encoding="utf-8"))
    return _make_fresh_state("")


def _save_state(project_path: Path, state: dict) -> None:
    state_path = project_path / "brainstorm_state.json"
    _save_json(state_path, state)


def _load_brief(project_path: Path) -> dict:
    with open(project_path / "brief_validated.json", encoding="utf-8") as f:
        return json.load(f)


def _load_text_bank(project_path: Path) -> dict:
    """Load input_bank.yaml. Expects format: text_inputs: {T01: {...}, ...}"""
    with open(project_path / "input_bank.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_domain_history(brainstorm_dir: Path) -> list[dict]:
    path = brainstorm_dir / "domain_history.yaml"
    if path.is_file():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return []


def _load_loved_liked(brainstorm_dir: Path) -> tuple[list[dict], list[dict]]:
    loved, liked = [], []
    loved_path = brainstorm_dir / "loved_ideas.json"
    liked_path = brainstorm_dir / "liked_ideas.json"
    if loved_path.is_file():
        loved = json.loads(loved_path.read_text())
    if liked_path.is_file():
        liked = json.loads(liked_path.read_text())
    return loved, liked


def _load_judge_config(project_path: Path) -> dict:
    path = project_path / "judge_config.json"
    if path.is_file():
        return json.loads(path.read_text())
    return {}


def _update_domain_history(brainstorm_dir: Path, fresh_yaml: str) -> None:
    try:
        bank = yaml.safe_load(fresh_yaml) or {}
        families = []
        for set_id, set_data in bank.get("sets", {}).items():
            families.append({
                "name": set_data.get("name", set_id),
                "set_id": set_id,
                "domains": set_data.get("domains", []),
            })
        history = _load_domain_history(brainstorm_dir)
        history.extend(families)
        path = brainstorm_dir / "domain_history.yaml"
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(history, f, allow_unicode=True, default_flow_style=False)
    except yaml.YAMLError:
        logger.warning("Could not update domain history")
