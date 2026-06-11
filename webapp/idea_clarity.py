"""Actionable French clarity — generated at creation, refreshed on read if stale."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from webapp.clarity_llm import (
    CLARITY_VERSION,
    _demo_clarity_for_idea,
    _fallback_clarity,
    load_brief,
    needs_clarity_refresh,
)


def _strip_md(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"\[simulated demo idea\]", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _collision_from_idea(idea: dict, text: str) -> dict:
    """Build collision context; prefer domain named in idea text."""
    domain_from_text = ""
    m = re.search(r"Borrowing from ([^,]+),", text, re.I)
    if m:
        domain_from_text = m.group(1).strip()
    if not domain_from_text:
        m = re.search(r"via ([^.]+)\.", text, re.I)
        if m:
            domain_from_text = m.group(1).strip()
    base = idea.get("collision") or {}
    if domain_from_text:
        base = {**base, "domain_name": domain_from_text, "inspiration": domain_from_text}
    return base


def build_clarity(
    idea: dict,
    project_dir: Path,
    collision: dict | None = None,
    *,
    mode: str = "demo",
) -> dict:
    """Build or return stored actionable clarity for an idea."""
    existing = idea.get("clarity") or {}
    if not needs_clarity_refresh(existing):
        return existing

    brief = load_brief(project_dir)
    text = idea.get("text") or ""
    merged_collision = {**(collision or {}), **_collision_from_idea(idea, text)}

    is_demo = (
        mode == "demo"
        or "simulated demo idea" in text.lower()
        or "Borrowing from" in text
    )

    if is_demo:
        clarity = _demo_clarity_for_idea(idea, brief, merged_collision)
    else:
        clarity = _fallback_clarity(idea, brief, merged_collision)

    clarity["summary_fr"] = f"{clarity['headline_fr']} {clarity.get('pour_vous', '')}".strip()
    return clarity


def attach_clarity_to_curated(curated: list[dict], project_dir: Path, *, mode: str = "demo") -> list[dict]:
    """Ensure each curated idea has a v2 clarity block."""
    out = []
    for item in curated:
        c = item.get("clarity")
        if needs_clarity_refresh(c):
            c = build_clarity(item, project_dir, mode=mode)
            out.append({**item, "clarity": c})
        else:
            out.append(item)
    return out


# Legacy compatibility for plain_language imports
def plain_summary(idea: dict) -> str:
    c = idea.get("clarity") or {}
    if c.get("headline_fr"):
        return f"En clair : {c['headline_fr']} {c.get('pour_vous', '')}"
    return idea.get("plain_summary") or "En clair : voir le détail ci-dessous."


def plain_hook(idea: dict, max_len: int = 48) -> str:
    c = idea.get("clarity") or {}
    if c.get("test"):
        t = c["test"]
        if len(t) > max_len:
            t = t[: max_len - 1].rsplit(" ", 1)[0] + "…"
        return t
    return "cette idée"
