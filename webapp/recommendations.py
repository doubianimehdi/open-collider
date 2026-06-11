"""Varied, plain-language next-step suggestions for ideas."""

from __future__ import annotations

import re


def _pick(options: list[str], seed: str) -> str:
    if not options:
        return ""
    return options[hash(seed) % len(options)]


def _first_action(idea: dict) -> str:
    c = idea.get("clarity") or {}
    actions = c.get("actions") or []
    return actions[0] if actions else ""


def suggest_next_step(
    flag: str,
    idea: dict,
    *,
    view: str = "synthesis",
) -> str:
    """Action tied to clarity block — complementary to the test, not a duplicate."""
    seed = idea.get("idea_id", "x")
    clarity = idea.get("clarity") or {}
    test = (clarity.get("test") or "").strip()
    first_action = _first_action(idea)

    if view == "iteration" and flag == "trashed":
        return _pick(
            [
                "Lisez « En clair » puis choisissez : ♥ priorité · ↑ plus tard · ✕ pas pour moi.",
                "Demandez-vous : est-ce que le test de 30 min est faisable cette semaine ?",
            ],
            seed,
        )

    if flag == "loved":
        if test:
            return _pick(
                [
                    "Après le test : notez si la personne propose une variante plus simple.",
                    "Si le test fonctionne, passez à la 2e action de « À appliquer ».",
                    "Notez ce qui bloque encore — une seule friction à lever la semaine prochaine.",
                ],
                seed,
            )
        return _pick(
            [
                "Expliquer l'idée à un collègue en 2 minutes — puis noter ce qu'il a compris.",
                "Choisir la première action concrète dans « À appliquer ».",
            ],
            seed,
        )

    if flag == "liked":
        if first_action:
            return f"Garder de côté : {first_action}"
        return "Relire « En clair » dans un mois — l'idée vaut-elle encore un test ?"

    return "Non retenue — voir la réserve en bas si besoin."
