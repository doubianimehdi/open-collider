"""LLM-generated actionable French clarity at idea creation time."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

CLARITY_VERSION = 2


def load_brief(project_dir: Path) -> dict:
    for name in ("brief_validated.json", "brief.yaml"):
        p = project_dir / name
        if p.is_file():
            if name.endswith(".json"):
                return json.loads(p.read_text(encoding="utf-8"))
            return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {}

# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------

_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "projects" / "_template" / "prompts" / "idea_clarity.md"
)


def _format_brief(brief: dict) -> str:
    if not brief:
        return "(aucun brief validé)"
    lines = []
    for key in ("objective", "context", "constraints", "forbidden"):
        val = brief.get(key)
        if val:
            label = key.replace("_", " ").title()
            if isinstance(val, list):
                lines.append(f"**{label}:** " + "; ".join(str(x) for x in val))
            else:
                lines.append(f"**{label}:** {val}")
    return "\n".join(lines) or str(brief)


def _ideas_block(ideas: list[dict]) -> str:
    parts = []
    for idea in ideas:
        num = idea.get("idea_num", len(parts) + 1)
        text = (idea.get("text") or "").strip()
        parts.append(f"## Idea {num}\n{text}")
    return "\n\n".join(parts)


def build_clarity_prompt(
    ideas: list[dict],
    brief: dict,
    collision_ctx: dict | None = None,
) -> str:
    """Build batch clarity prompt for one combo's ideas."""
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    ctx = collision_ctx or {}
    return template.replace("{brief_content}", _format_brief(brief)).replace(
        "{ideas_block}", _ideas_block(ideas)
    ).replace("{text_id}", ctx.get("text_id", "?")).replace(
        "{domain_set}", ctx.get("domain_set", "?")
    ).replace("{domain_name}", ctx.get("domain_name", "?")).replace(
        "{active_principle}", ctx.get("active_principle", "")
    )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _normalize_clarity_block(raw: dict, *, source: str) -> dict:
    actions = raw.get("actions") or []
    if isinstance(actions, str):
        actions = [a.strip() for a in re.split(r"\n\s*-\s*", actions) if a.strip()]
    headline = (raw.get("headline_fr") or raw.get("headline") or "").strip()
    pour_vous = (raw.get("pour_vous") or "").strip()
    test = (raw.get("test") or "").strip()
    return {
        "version": CLARITY_VERSION,
        "source": source,
        "headline_fr": headline,
        "pour_vous": pour_vous,
        "actions": [a.strip() for a in actions if a.strip()][:3],
        "test": test,
        "summary_fr": f"{headline} {pour_vous}".strip(),
    }


def parse_clarity_response(raw: str) -> dict[int, dict]:
    """Parse LLM response into {idea_num: clarity_dict}."""
    out: dict[int, dict] = {}
    if not raw:
        return out

    # Split on ### En clair — Idea N
    sections = re.split(
        r"\n#{1,3}\s*En clair\s*[—\-–]\s*[Ii]dea\s+(\d+)",
        "\n" + raw,
    )
    if len(sections) >= 3:
        for i in range(1, len(sections), 2):
            num = int(sections[i])
            body = sections[i + 1].strip()
            parsed = _parse_clarity_body(body)
            if parsed:
                out[num] = _normalize_clarity_block(parsed, source="llm")
        if out:
            return out

    # Fallback: YAML blocks per idea
    for m in re.finditer(
        r"(?:^|\n)(?:#{1,3}\s*)?(?:En clair\s*[—\-–]\s*)?[Ii]dea\s+(\d+)\s*\n(.*?)(?=\n(?:#{1,3}|En clair|[Ii]dea\s+\d+|\Z))",
        raw,
        re.DOTALL | re.I,
    ):
        num = int(m.group(1))
        parsed = _parse_clarity_body(m.group(2))
        if parsed:
            out[num] = _normalize_clarity_block(parsed, source="llm")

    return out


def _parse_clarity_body(body: str) -> dict | None:
    body = body.strip()
    if not body:
        return None
    # Try YAML key: value format
    try:
        data = yaml.safe_load(body)
        if isinstance(data, dict):
            return data
    except yaml.YAMLError:
        pass

    result: dict[str, Any] = {}
    for key in ("headline_fr", "pour_vous", "test"):
        m = re.search(rf"^{key}:\s*(.+)$", body, re.M | re.I)
        if m:
            result[key] = m.group(1).strip().strip('"')
    actions_m = re.search(r"^actions:\s*\n((?:\s*-\s*.+\n?)+)", body, re.M | re.I)
    if actions_m:
        result["actions"] = re.findall(r"^\s*-\s*(.+)$", actions_m.group(1), re.M)
    return result if result.get("headline_fr") or result.get("pour_vous") else None


def _extract_domain_from_text(text: str) -> str:
    m = re.search(r"Borrowing from ([^,]+),", text, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"via ([^.]+)\.", text, re.I)
    if m:
        return m.group(1).strip()
    return ""


def _brief_product_hint(brief: dict) -> str:
    blob = " ".join(
        str(brief.get(k, "")) for k in ("objective", "context", "constraints")
    ).lower()
    if "discover weekly" in blob or "spotify" in blob:
        return "Discover Weekly"
    if "recommend" in blob or "playlist" in blob or "bulle" in blob or "taste" in blob:
        return "les recommandations musicales"
    if "onboard" in blob:
        return "l'accueil des nouveaux utilisateurs"
    return "votre produit"


def _mechanism_fr(text: str) -> str:
    low = text.lower()
    if "invisibly for days before any surface change" in low:
        return (
            "les changements commencent invisibles — longtemps avant qu'on puisse les voir en surface"
        )
    if "local response threshold" in low or "without any central planner" in low:
        return "chaque acteur réagit localement, sans chef d'orchestre visible"
    if "decay as the carrier" in low:
        return "c'est la lente dégradation qui porte l'information, pas un choc brutal"
    if "waiting into the primary instrument" in low:
        return "l'attente devient le levier principal — pas l'action immédiate"
    m = re.search(r"which (.+?), this idea", text, re.I)
    if m:
        return m.group(1).strip().rstrip(".")[:160]
    return "un mécanisme qui agit en coulisse avant l'effet visible"


def _demo_clarity_for_idea(idea: dict, brief: dict, collision_ctx: dict | None = None) -> dict:
    """Deterministic clarity for demo mode — brief-anchored, no meta-instructions."""
    text = idea.get("text") or ""
    objective = brief.get("objective") or brief.get("context") or "votre projet"
    short_obj = objective.split(".")[0][:120]
    product = _brief_product_hint(brief)
    domain = _extract_domain_from_text(text) or (
        (collision_ctx or {}).get("domain_name") or "un autre domaine"
    )
    mechanism = _mechanism_fr(text)

    low = text.lower()
    if any(k in low for k in ("recommendation", "discover", "pricing ladder")) and product == "Discover Weekly":
        obj_key = "recommendations"
    elif "onboarding" in low:
        obj_key = "onboarding"
    elif "retention" in low:
        obj_key = "retention"
    elif "feedback" in low:
        obj_key = "feedback"
    elif "trust" in low:
        obj_key = "trust"
    elif "community" in low:
        obj_key = "community"
    elif "content" in low:
        obj_key = "content"
    else:
        obj_key = "discovery"

    templates = {
        "recommendations": {
            "headline_fr": f"Faire évoluer {product} avant que l'utilisateur ne voie un changement.",
            "pour_vous": (
                f"Pour « {short_obj} », la piste n'est pas de chambouler la playlist d'un coup : "
                f"{mechanism}. Inspiré de {domain}."
            ),
            "actions": [
                f"Repérer 3 signaux d'écoute faibles (replays discrets, skips tardifs, morceaux jamais partagés).",
                f"Tester UNE micro-variante dans {product} cette semaine — un titre « hors bulle » inséré sans annonce.",
                "Mesurer à J+7 : est-ce que la personne ré-ouvre la playlist sans y penser ?",
            ],
            "test": (
                f"Montrer la playlist à une personne qui ne connaît pas Spotify : "
                f"« Qu'est-ce qui a changé depuis la semaine dernière ? » — notez si elle ne voit rien."
            ),
        },
        "discovery": {
            "headline_fr": "Élargir la découverte sans annoncer qu'on sort de la bulle.",
            "pour_vous": (
                f"Pour « {short_obj} », {mechanism}. "
                f"Mécanisme emprunté à {domain}."
            ),
            "actions": [
                "Lister ce que l'utilisateur croit « normal » dans son feed — et ce qui manque.",
                "Introduire un seul contenu adjacent (pas opposé) sans label « pour vous ».",
                "Noter si la personne revient au contenu adjacent dans les 7 jours.",
            ],
            "test": "Demander à 2 utilisateurs : « Qu'avez-vous découvert sans le chercher ? » — 30 min.",
        },
        "retention": {
            "headline_fr": "Garder l'engagement avant qu'il ne se voie partir.",
            "pour_vous": (
                f"Pour « {short_obj} », {mechanism}. "
                f"Piste : {domain}."
            ),
            "actions": [
                "Identifier 3 signaux faibles de désengagement sans plainte visible.",
                "Une micro-intervention discrète : rappel différé ou contenu « invisible ».",
                "Mesurer délai entre visites sur 7 jours.",
            ],
            "test": "Parler à 2 utilisateurs : « Quand [produit] vous a-t-il manqué sans événement visible ? »",
        },
        "onboarding": {
            "headline_fr": "Accueillir par infiltration lente, pas par discours.",
            "pour_vous": (
                f"Pour « {short_obj} », {mechanism}. "
                f"Inspiré de {domain}."
            ),
            "actions": [
                "Trouver l'étape où l'utilisateur reste sans comprendre pourquoi il reviendra.",
                "Remplacer un message explicite par un rituel discret (J+2, défaut utile).",
                "Mesurer qui revient à J+7 sans objectif affiché complété.",
            ],
            "test": "Observer 3 nouveaux utilisateurs en silence — où bloquent-ils sans le dire ?",
        },
        "feedback": {
            "headline_fr": "Captez les retours avant de les demander.",
            "pour_vous": (
                f"Pour « {short_obj} », {mechanism}. "
                f"Via {domain}."
            ),
            "actions": [
                "Noter 3 comportements qui signalent satisfaction sans formulaire.",
                "Poser une question ouverte à un moment inattendu (fin de session).",
                "Classer : mécanisme réel vs métaphore — garder le mécanisme.",
            ],
            "test": "Message à 3 personnes : « Qu'est-ce qui vous a surpris cette semaine ? »",
        },
    }

    block = templates.get(obj_key) or templates["discovery"]
    return _normalize_clarity_block(block, source="demo")


def _fallback_clarity(idea: dict, brief: dict, collision_ctx: dict | None = None) -> dict:
    """Last-resort clarity when LLM parse fails."""
    text = idea.get("text") or ""
    if "simulated demo idea" in text.lower() or "Borrowing from" in text:
        return _demo_clarity_for_idea(idea, brief, collision_ctx)
    objective = brief.get("objective") or brief.get("context") or "votre projet"
    short = objective.split(".")[0][:100]
    hook = re.sub(r"\*\*(.+?)\*\*", r"\1", text.split("\n")[0])[:120]
    domain = _extract_domain_from_text(text) or (collision_ctx or {}).get("domain_name", "")
    return _normalize_clarity_block(
        {
            "headline_fr": f"Tester une piste concrète pour « {short} ».",
            "pour_vous": f"{hook}. Mécanisme : {_mechanism_fr(text)}. Domaine : {domain or 'collision'}.",
            "actions": [
                f"Choisir un geste minimal sur { _brief_product_hint(brief) } cette semaine.",
                "Noter ce qui change pour une vraie personne en 7 jours.",
                "Ajuster ou abandonner selon l'observation — pas selon l'intuition.",
            ],
            "test": "30 min avec une personne du public visé : montrez le geste, notez sa réaction.",
        },
        source="fallback",
    )


def ensure_clarity(
    idea: dict,
    brief: dict,
    llm: Any | None,
    *,
    mode: str = "live",
    collision_ctx: dict | None = None,
) -> dict:
    """Return v2 clarity for one idea; uses demo/fallback without LLM in demo mode."""
    existing = idea.get("clarity") or {}
    if existing.get("version") == CLARITY_VERSION and existing.get("headline_fr"):
        return existing

    if mode == "demo":
        return _demo_clarity_for_idea(idea, brief, collision_ctx)

    # Live: clarity should be attached in batch; single-idea fallback
    return _fallback_clarity(idea, brief, collision_ctx)


async def attach_clarity_batch(
    ideas: list[dict],
    brief: dict,
    llm: Any,
    *,
    mode: str,
    collision_ctx: dict | None = None,
    model: str = "gpt-4o-mini",
) -> list[dict]:
    """Attach clarity v2 to each idea after generation (batch LLM call in live mode)."""
    if not ideas:
        return ideas

    if mode == "demo":
        out = []
        for idea in ideas:
            c = _demo_clarity_for_idea(idea, brief, collision_ctx)
            out.append({**idea, "clarity": c})
        return out

    # Live: one LLM call per combo batch
    import asyncio

    prompt = build_clarity_prompt(ideas, brief, collision_ctx)
    try:
        response = await asyncio.to_thread(
            llm.call,
            model=model,
            prompt=prompt,
            temperature=0.2,
            max_tokens=2500,
        )
        parsed = parse_clarity_response(response)
    except Exception as exc:
        logger.warning("Clarity LLM batch failed: %s", exc)
        parsed = {}

    out = []
    for idea in ideas:
        num = idea.get("idea_num", 0)
        if num in parsed and parsed[num].get("headline_fr"):
            c = parsed[num]
        else:
            c = _fallback_clarity(idea, brief, collision_ctx)
            c["source"] = "fallback"
        out.append({**idea, "clarity": c})
    return out


def needs_clarity_refresh(clarity: dict | None) -> bool:
    if not clarity:
        return True
    return clarity.get("version", 0) < CLARITY_VERSION
