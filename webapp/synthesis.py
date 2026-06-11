"""Build a structured session synthesis for the Web UI ideation report."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import yaml


def _normalize_flag(flag: str) -> str:
    if flag in ("loved", "love"):
        return "loved"
    if flag in ("liked", "like"):
        return "liked"
    return "trashed"


def _idea_entry(curated: dict, flags: dict, iteration: int) -> dict:
    idea_id = curated.get("idea_id", "")
    flag = _normalize_flag(flags.get(idea_id, "trashed"))
    scores = curated.get("scores") or {}
    return {
        "idea_id": idea_id,
        "iteration": iteration,
        "flag": flag,
        "rank": curated.get("rank"),
        "score": curated.get("score") or curated.get("score_aggregate"),
        "text": curated.get("text", ""),
        "why_selected": curated.get("why_selected") or curated.get("why_kept"),
        "source_note": curated.get("source_note", ""),
        "challenge": curated.get("challenge", ""),
        "clarity": curated.get("clarity"),
        "scores": {
            "originality": scores.get("originality"),
            "resistance": scores.get("resistance"),
            "thesis_density": scores.get("thesis_density"),
            "concrete_grounding": scores.get("concrete_grounding"),
            "cognitive_load": scores.get("cognitive_load"),
        },
    }


def build_synthesis(project_dir: Path, brainstorm_id: str) -> dict:
    """Aggregate session data into sections optimized for ideation review."""
    brainstorm_dir = project_dir / "brainstorms" / brainstorm_id
    if not brainstorm_dir.is_dir():
        raise FileNotFoundError(f"Session {brainstorm_id} not found")

    brief_path = project_dir / "brief.yaml"
    brief = {}
    if brief_path.is_file():
        brief = yaml.safe_load(brief_path.read_text(encoding="utf-8")) or {}

    loved: list[dict] = []
    liked: list[dict] = []
    trashed: list[dict] = []
    insights: list[dict] = []
    feedback: list[dict] = []
    timeline: list[dict] = []

    for idir in sorted(brainstorm_dir.iterdir()):
        if not idir.is_dir() or not idir.name.startswith("iter_"):
            continue
        cfg_path = idir / "config.json"
        if not cfg_path.is_file():
            continue

        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        iteration = cfg.get("iteration") or int(idir.name.split("_")[1])

        curated_path = idir / "curated_ideas.json"
        flags_path = idir / "flags.json"
        insights_path = idir / "insights_without_collision.json"
        fb_path = idir / "feedback.txt"

        curated = json.loads(curated_path.read_text()) if curated_path.is_file() else []
        flags = json.loads(flags_path.read_text()) if flags_path.is_file() else {}

        n_loved = sum(1 for v in flags.values() if _normalize_flag(v) == "loved")
        n_liked = sum(1 for v in flags.values() if _normalize_flag(v) == "liked")
        n_trashed = len(flags) - n_loved - n_liked

        timeline.append({
            "iteration": iteration,
            "generated": cfg.get("ideas_generated", 0),
            "retained": cfg.get("ideas_retained", 0),
            "curated": len(curated),
            "loved": n_loved,
            "liked": n_liked,
            "trashed": n_trashed,
            "strategies": cfg.get("strategies_used", []),
            "flagged": flags_path.is_file(),
        })

        for c in curated:
            entry = _idea_entry(c, flags, iteration)
            if entry["flag"] == "loved":
                loved.append(entry)
            elif entry["flag"] == "liked":
                liked.append(entry)
            else:
                trashed.append({
                    **entry,
                    "summary": entry["text"].split("\n")[0][:180],
                })

        if insights_path.is_file():
            raw_insights = json.loads(insights_path.read_text())
            for c in raw_insights:
                idea_id = c.get("idea_id", "")
                flag = flags.get(idea_id, "unflagged")
                insights.append({
                    "idea_id": idea_id,
                    "iteration": iteration,
                    "flag": flag,
                    "score": c.get("score") or c.get("score_aggregate"),
                    "text": c.get("text", ""),
                    "why_kept": c.get("why_kept", ""),
                })

        if fb_path.is_file():
            fb_text = fb_path.read_text(encoding="utf-8").strip()
            if fb_text:
                feedback.append({"iteration": iteration, "text": fb_text})

    loved.sort(key=lambda x: (-float(x.get("score") or 0), x.get("iteration", 0)))
    liked.sort(key=lambda x: (-float(x.get("score") or 0), x.get("iteration", 0)))

    report_path = brainstorm_dir / "REPORT.md"
    updated = datetime.now().strftime("%Y-%m-%d %H:%M")
    if report_path.is_file():
        updated = datetime.fromtimestamp(report_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")

    return {
        "project": project_dir.name,
        "session_id": brainstorm_id,
        "objective": brief.get("objective", ""),
        "updated": updated,
        "stats": {
            "iterations": len(timeline),
            "loved": len(loved),
            "liked": len(liked),
            "trashed": len(trashed),
            "insights": len(insights),
            "has_feedback": bool(feedback),
        },
        "feedback": feedback,
        "timeline": timeline,
        "shortlist": loved,
        "explore": liked,
        "discarded": trashed,
        "insights": insights,
        "has_report": report_path.is_file(),
        "has_html": (brainstorm_dir / "REPORT.html").is_file(),
    }
