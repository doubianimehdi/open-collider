"""Session navigation, collision context, and actionable guidance."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import yaml

from webapp.clarity_llm import needs_clarity_refresh
from webapp.idea_clarity import build_clarity, plain_summary, plain_hook
from webapp.recommendations import suggest_next_step

STEPS = [
    {"n": 1, "key": "prepare", "label": "Préparer", "hint": "Brief et textes"},
    {"n": 2, "key": "collide", "label": "Générer", "hint": "Lancer une session d'idées"},
    {"n": 3, "key": "judge", "label": "Choisir", "hint": "♥ / ↑ / ✕ sur chaque carte"},
    {"n": 4, "key": "iterate", "label": "Relancer", "hint": "Nouvelle session ou bilan"},
    {"n": 5, "key": "synthesis", "label": "Bilan", "hint": "Lire, choisir, valider"},
]


def _validation_path(brainstorm_dir: Path) -> Path:
    return brainstorm_dir / "synthesis_done.json"


def load_validation(brainstorm_dir: Path) -> dict:
    p = _validation_path(brainstorm_dir)
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"done": False}


def save_validation(brainstorm_dir: Path, *, chosen: list[str], note: str = "") -> dict:
    data = {
        "done": True,
        "validated_at": datetime.now().strftime("%d/%m/%Y à %H:%M"),
        "chosen": chosen,
        "note": note.strip(),
    }
    _validation_path(brainstorm_dir).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return data


def _normalize_flag(flag: str) -> str:
    if flag in ("loved", "love"):
        return "loved"
    if flag in ("liked", "like"):
        return "liked"
    return "trashed"


def _load_text_meta(project_dir: Path) -> dict[str, dict]:
    texts_dir = project_dir / "texts"
    meta = {}
    if not texts_dir.is_dir():
        return meta
    for f in sorted(texts_dir.glob("*.md")):
        tid = f.stem.upper() if f.stem.startswith("t") else f.stem
        content = f.read_text(encoding="utf-8")
        title = content.split("\n")[0].strip("# ").strip()[:80] if content else f.stem
        meta[f.stem] = {"id": f.stem, "title": title, "preview": content[:200].strip()}
        meta[tid] = meta[f.stem]
    return meta


def _domain_for_set(iter_dir: Path, set_id: str) -> dict:
    """Resolve domain set name and sample active principle from iteration domains."""
    domains_dir = iter_dir / "domains"
    if not domains_dir.is_dir():
        return {"set_name": set_id, "domain_name": "", "active_principle": ""}
    for yf in domains_dir.glob("*.yaml"):
        bank = yaml.safe_load(yf.read_text(encoding="utf-8")) or {}
        for sid, s in (bank.get("sets") or {}).items():
            if sid == set_id or s.get("name", "") == set_id:
                domains = s.get("domains") or []
                d0 = domains[0] if domains else {}
                return {
                    "set_name": s.get("name", sid),
                    "domain_name": d0.get("name", ""),
                    "active_principle": d0.get("active_principle", ""),
                    "strategy": yf.stem,
                }
    return {"set_name": set_id, "domain_name": "", "active_principle": ""}


def _parse_source_note(note: str) -> dict:
    """Parse 'fresh strategy · T01 × Glass physics' style notes."""
    m = re.match(r"(?P<strategy>\w+)\s+strategy\s·\s*(?P<text_id>\S+)\s×\s*(?P<set>.+)", note or "")
    if m:
        return m.groupdict()
    return {"strategy": "", "text_id": "", "set": note}


def _action_for(flag: str, idea: dict, *, view: str = "synthesis") -> str:
    return suggest_next_step(flag, idea, view=view)


def enrich_idea(idea: dict, iter_dir: Path, text_meta: dict, project_dir: Path | None = None) -> dict:
    """Attach collision context and suggested action to an idea."""
    text_id = idea.get("text_id") or _parse_source_note(idea.get("source_note", "")).get("text_id", "")
    set_id = idea.get("set_id") or _parse_source_note(idea.get("source_note", "")).get("set", "")
    dom = _domain_for_set(iter_dir, set_id) if iter_dir.is_dir() else {}

    tm = text_meta.get(text_id, text_meta.get(text_id.lower(), {}))
    flag = _normalize_flag(idea.get("flag", "trashed"))

    collision = {
        "text_id": text_id,
        "text_title": tm.get("title", text_id),
        "text_preview": tm.get("preview", ""),
        "strategy": idea.get("strategy") or dom.get("strategy", ""),
        "domain_set": dom.get("set_name", set_id),
        "domain_name": dom.get("domain_name", ""),
        "active_principle": dom.get("active_principle", ""),
        "source_note": idea.get("source_note", ""),
    }
    collision["inspiration"] = _simple_inspiration(collision, idea.get("text", ""))

    enriched = {**idea, "collision": collision}
    if needs_clarity_refresh(enriched.get("clarity")):
        pd = project_dir or (iter_dir.parent.parent.parent if iter_dir.is_dir() else Path("."))
        enriched["clarity"] = build_clarity(enriched, pd, collision)
    enriched["plain_summary"] = plain_summary(enriched)
    enriched["plain_hook"] = plain_hook(enriched)
    enriched["action"] = _action_for(flag, enriched, view="synthesis")
    return enriched


def _simple_inspiration(collision: dict, idea_text: str = "") -> str:
    from_text = ""
    m = re.search(r"Borrowing from ([^,]+),", idea_text or "", re.I)
    if m:
        from_text = m.group(1).strip()
    if not from_text:
        m = re.search(r"via ([^.]+)\.", idea_text or "", re.I)
        if m:
            from_text = m.group(1).strip()
    name = from_text or collision.get("domain_name") or collision.get("domain_set") or ""
    name = re.split(r"[,(]", name)[0].strip()
    if len(name) > 48:
        name = name[:47].rsplit(" ", 1)[0] + "…"
    return name or "inspiration inconnue"


def compute_step(session: dict | None, *, view: str = "project", iteration: int | None = None) -> int:
    if view == "synthesis":
        if session and session.get("synthesis_done"):
            return 5
        return 5
    if view == "run":
        return 2
    if view == "iteration" and iteration is not None:
        if not session:
            return 3
        iters = session.get("iterations_detail") or []
        match = next((i for i in iters if i.get("iteration") == iteration), None)
        if match and not match.get("flagged"):
            return 3
        return 4
    if not session or not session.get("iterations_detail"):
        return 2
    last = session["iterations_detail"][-1]
    if not last.get("flagged"):
        return 3
    if session.get("synthesis_done") or session.get("has_report"):
        return 5
    return 4


def build_navigation(
    project_dir: Path,
    brainstorm_id: str | None,
    *,
    view: str = "project",
    iteration: int | None = None,
    session: dict | None = None,
) -> dict:
    brief_path = project_dir / "brief.yaml"
    brief = {}
    if brief_path.is_file():
        brief = yaml.safe_load(brief_path.read_text(encoding="utf-8")) or {}

    step_n = compute_step(session, view=view, iteration=iteration)
    current = next(s for s in STEPS if s["n"] == step_n)

    prev = next((s for s in STEPS if s["n"] == step_n - 1), None)
    nxt = next((s for s in STEPS if s["n"] == step_n + 1), None)

    now_actions = {
        1: "Remplir le brief et ajouter au moins un texte (notes, memo, brouillon).",
        2: "Lancer une session pour obtenir de nouvelles idées.",
        3: "Parcourir les cartes : ♥ favorites · ↑ intéressantes · ✕ à écarter. Puis enregistrer.",
        4: "Relancer une session (vos ♥ guident la suite) ou ouvrir le bilan.",
        5: "Lire vos favorites ♥, cocher celles à retenir, puis valider le bilan.",
    }

    validation = {}
    if brainstorm_id:
        bdir = project_dir / "brainstorms" / brainstorm_id
        if bdir.is_dir():
            validation = load_validation(bdir)

    synthesis_complete = bool(validation.get("done"))
    if synthesis_complete and view == "synthesis":
        n_chosen = len(validation.get("chosen") or [])
        now_actions[5] = (
            f"Bilan validé le {validation.get('validated_at', '')} — "
            f"{n_chosen} idée{'s' if n_chosen != 1 else ''} retenue{'s' if n_chosen != 1 else ''}."
        )
        if validation.get("note"):
            now_actions[5] += f" Prochaine étape notée : « {validation['note']} »"

    next_links = []
    name = project_dir.name
    if brainstorm_id:
        if step_n <= 3:
            next_links.append({
                "label": "Enregistrer le verdict",
                "hint": "Puis itérer ou synthétiser",
                "hash": f"#/p/{name}/b/{brainstorm_id}/i/{iteration or 1}",
            })
        if step_n >= 3:
            next_links.append({
                "label": "Itération suivante",
                "hint": "Approfondir vos ♥ love",
                "action": "startRun",
            })
        if step_n >= 4:
            next_links.append({
                "label": "Voir le bilan",
                "hint": "Vos idées retenues, en clair",
                "hash": f"#/p/{name}/b/{brainstorm_id}/synthesis",
            })

    return {
        "project": name,
        "session_id": brainstorm_id,
        "objective": brief.get("objective", ""),
        "context_line": brief.get("context", "")[:160],
        "steps": STEPS,
        "current_step": step_n,
        "current": current,
        "came_from": prev["label"] if prev else None,
        "now_label": current["label"],
        "now_hint": current["hint"],
        "now_action": now_actions.get(step_n, ""),
        "next_step": None if synthesis_complete else (nxt["label"] if nxt else None),
        "next_links": next_links,
        "reference_texts": list(_load_text_meta(project_dir).values()),
        "synthesis_complete": synthesis_complete,
        "validation": validation if validation.get("done") else None,
    }


def enrich_synthesis(synthesis: dict, project_dir: Path, brainstorm_id: str) -> dict:
    """Add navigation + collision context to synthesis payload."""
    brainstorm_dir = project_dir / "brainstorms" / brainstorm_id
    text_meta = _load_text_meta(project_dir)

    validation = load_validation(brainstorm_dir)

    session = {
        "iterations_detail": synthesis.get("timeline", []),
        "has_report": synthesis.get("has_report"),
        "synthesis_done": validation.get("done", False),
    }
    nav = build_navigation(
        project_dir, brainstorm_id, view="synthesis", session=session,
    )

    validation = load_validation(brainstorm_dir)

    def enrich_list(items: list[dict]) -> list[dict]:
        out = []
        for item in items:
            if needs_clarity_refresh(item.get("clarity")):
                item = {**item, "clarity": build_clarity(item, project_dir, mode="demo")}
            it_n = item.get("iteration", 1)
            iter_dir = brainstorm_dir / f"iter_{it_n:03d}"
            flag = _normalize_flag(item.get("flag", "trashed"))
            enriched = enrich_idea({**item, "flag": flag}, iter_dir, text_meta, project_dir=project_dir)
            enriched["action"] = _action_for(flag, enriched, view="synthesis")
            enriched["link"] = f"#/p/{project_dir.name}/b/{brainstorm_id}/i/{it_n}#idea-{item.get('idea_id', '')}"
            if validation.get("done") and item.get("idea_id") in (validation.get("chosen") or []):
                enriched["retained"] = True
            out.append(enriched)
        return out

    synthesis["navigation"] = nav
    synthesis["validation"] = validation
    synthesis["shortlist"] = enrich_list(synthesis.get("shortlist", []))
    synthesis["explore"] = enrich_list(synthesis.get("explore", []))
    synthesis["discarded"] = enrich_list(synthesis.get("discarded", []))
    return synthesis
