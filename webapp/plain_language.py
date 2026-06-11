"""Plain-language summaries — keep original idea text, add readable French gloss."""

from __future__ import annotations

import re

# Demo-mode boilerplate → French (orchestrator.py patterns)
_MECH_PLAIN = {
    "shows that transformation happens invisibly for days before any surface change is detectable": (
        "les changements se produisent d'abord invisibles, longtemps avant qu'on puisse les voir en surface"
    ),
    "inverts the usual relationship between strength and fragility: the most resistant structure fails catastrophically at its least-watched edge": (
        "la solidité apparente peut cacher un point faible qui fait tout s'effondrer d'un coup"
    ),
    "relies on decay as the carrier of information, not the loss of it": (
        "c'est la dégradation lente qui porte l'information, pas sa disparition"
    ),
    "allocates work without any central planner, purely through local response thresholds": (
        "le travail se répartit tout seul, sans chef, via des seuils locaux"
    ),
    "turns waiting into the primary instrument of control": (
        "l'attente devient le principal levier de contrôle"
    ),
    "uses the boundary layer, not the core, as the site where all the real exchange happens": (
        "l'échange réel se passe en surface, pas au cœur du système"
    ),
    "demonstrates that the timing of arrival encodes more information than the arrival itself": (
        "c'est surtout le moment d'arrivée qui informe, pas l'arrivée elle-même"
    ),
    "shapes outcomes by removing energy at precise moments rather than adding it": (
        "on oriente le résultat en retirant de l'énergie au bon moment, plutôt qu'en en ajoutant"
    ),
}

_OBJECT_FR = {
    "the retention mechanism": "garder vos utilisateurs / clients",
    "the onboarding funnel": "l'accueil des nouveaux",
    "the feedback loop": "la boucle de retour",
    "the discovery surface": "comment on découvre l'offre",
    "the trust boundary": "la frontière de confiance",
    "the pricing ladder": "la grille tarifaire",
    "the content pipeline": "la production de contenu",
    "the recommendation engine": "les recommandations",
    "the community layer": "la couche communautaire",
}

_VERB_FR = {
    "quarantine": "isoler",
    "re-architect": "repenser la structure de",
    "invert": "inverser",
    "stage": "mettre en scène",
    "instrument": "équiper / mesurer",
    "decay-weight": "pondérer avec la dégradation de",
    "stratify": "stratifier",
    "seed": "amorcer",
    "triangulate": "trianguler",
    "anneal": "recuire / stabiliser",
}


def _strip_md(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"\[simulated demo idea\]", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _first_line(text: str) -> str:
    for line in text.splitlines():
        line = _strip_md(line.strip())
        line = re.sub(r"^\d+\.\s*", "", line)
        if line:
            return line
    return ""


def _title_from_demo(text: str) -> str:
    """Extract 'Verb object via domain' from demo idea pattern."""
    m = re.match(
        r"^(.+?)\s+via\s+(.+?)\.\s*Borrowing",
        _first_line(text),
        re.I,
    )
    if not m:
        return _first_line(text).split(".")[0]
    verb_obj = m.group(1).strip()
    domain = m.group(2).strip()
    vo = verb_obj.lower()
    for en, fr in _OBJECT_FR.items():
        if en in vo:
            verb = vo.replace(en, "").strip()
            vfr = _VERB_FR.get(verb, verb)
            return f"{vfr} {fr} en s'inspirant de {domain.lower()}"
    return f"{verb_obj} via {domain}"


def _mechanism_plain(text: str) -> str:
    for en, fr in _MECH_PLAIN.items():
        if en in text:
            return fr
    m = re.search(r"Borrowing from .+?, which (.+?), this idea", text, re.I | re.DOTALL)
    if m:
        raw = m.group(1).strip().rstrip(".")
        if len(raw) > 120:
            raw = raw[:119].rsplit(" ", 1)[0] + "…"
        return raw
    return ""


def _inspiration_label(collision: dict) -> str:
    name = (
        collision.get("inspiration")
        or collision.get("domain_name")
        or collision.get("domain_set")
        or "cette inspiration"
    )
    name = re.split(r"[,(]", name)[0].strip()
    # Friendly gloss for common demo domains
    gloss = {
        "whispering gallery modes": "galeries murmurantes (le son longe les murs)",
        "choir screen diffusion": "écrans de chœur des cathédrales (diffusion du son)",
        "tempered glass stress fields": "verre trempé (contraintes internes invisibles)",
        "koji mold enzymatic infiltration": "koji (infiltration lente des enzymes)",
    }
    low = name.lower()
    for k, v in gloss.items():
        if k in low:
            return v
    if len(name) > 52:
        name = name[:51].rsplit(" ", 1)[0] + "…"
    return name


def plain_summary(idea: dict) -> str:
    """French gloss — original text stays in idea.text for the UI."""
    text = idea.get("text") or ""
    collision = idea.get("collision") or {}
    why = (idea.get("why_selected") or idea.get("why_kept") or "").strip()

    if "simulated demo idea" in text.lower() or "Borrowing from" in text:
        title_action = _title_from_demo(text)
        mech = _mechanism_plain(text)
        inspiration = _inspiration_label(collision)
        why_plain = ""
        if why and "structural transfer" in why.lower():
            why_plain = "Le mécanisme se transfère de façon concrète et vérifiable."
        elif why:
            why_plain = why.rstrip(".") + "."
        parts = [
            f"On s'inspire de « {inspiration} » : {mech or 'un processus invisible avant les effets visibles'}.",
            f"Appliqué à votre sujet : {title_action.rstrip('.')}.",
        ]
        if why_plain:
            parts.append(why_plain)
        return "En clair : " + " ".join(parts)

    inspiration = _inspiration_label(collision)
    hook = _strip_md(_first_line(text))
    if len(hook) > 100:
        hook = hook[:99].rsplit(" ", 1)[0] + "…"

    if why:
        return f"En clair : croiser votre texte avec « {inspiration} » — {why.rstrip('.')}."

    return f"En clair : partir de « {inspiration} » pour explorer l'idée suivante — {hook.lower().rstrip('.')}."


def plain_hook(idea: dict, max_len: int = 48) -> str:
    """Short label for next-step suggestions — no markdown, no jargon."""
    summary = idea.get("plain_summary") or plain_summary(idea)
    body = summary
    if body.lower().startswith("en clair :"):
        body = body[10:].strip()
    # First sentence only
    sentence = body.split(".")[0].strip()
    sentence = re.sub(r"[«»\"']", "", sentence)
    if len(sentence) > max_len:
        sentence = sentence[: max_len - 1].rsplit(" ", 1)[0] + "…"
    return sentence or "cette idée"
