"""Tests for LLM clarity generation (v2) and demo fixture #07."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from webapp.clarity_llm import (
    CLARITY_VERSION,
    _demo_clarity_for_idea,
    parse_clarity_response,
    needs_clarity_refresh,
    build_clarity_prompt,
)
from webapp.idea_clarity import build_clarity


SPOTIFY_BRIEF = {
    "objective": (
        "Structural redesigns of Spotify Discover Weekly that break users out of their taste bubble"
    ),
    "context": "Music streaming, weekly personalized playlist, filter bubble",
}

IDEA_07_TEXT = (
    "7. **Invert the pricing ladder via raid front turbulence.** "
    "Borrowing from raid front turbulence, which shows that transformation happens "
    "invisibly for days before any surface change is detectable, this idea applies the same "
    "structural mechanism to the brief. The transfer is concrete and testable: "
    "the mechanism, not the metaphor, is what crosses over. "
    "*[simulated demo idea]*"
)


def _make_project():
    project = Path(tempfile.mkdtemp()) / "spotify_test"
    project.mkdir()
    (project / "brief_validated.json").write_text(json.dumps(SPOTIFY_BRIEF), encoding="utf-8")
    return project


def test_clarity_version_constant():
    assert CLARITY_VERSION == 2


def test_needs_clarity_refresh():
    assert needs_clarity_refresh(None) is True
    assert needs_clarity_refresh({}) is True
    assert needs_clarity_refresh({"version": 1, "headline_fr": "x"}) is True
    assert needs_clarity_refresh({"version": 2, "headline_fr": "ok"}) is False


def test_demo_clarity_fixture_07():
    tmp_project = _make_project()
    idea = {
        "idea_num": 7,
        "text": IDEA_07_TEXT,
        "idea_id": "test_7",
    }
    collision = {"domain_name": "Queen pheromone gradients", "inspiration": "Queen pheromone gradients"}
    c = _demo_clarity_for_idea(idea, SPOTIFY_BRIEF, collision)

    assert c["version"] == CLARITY_VERSION
    assert c["source"] == "demo"
    blob = " ".join([c["headline_fr"], c["pour_vous"], *c["actions"], c["test"]]).lower()
    assert "un domaine lointain" not in blob
    assert "monétiser sans braquer" not in blob
    assert "écrire en une phrase" not in blob
    assert "trouvez un exemple" not in blob
    assert any(k in blob for k in ("discover weekly", "playlist", "bulle", "recommand"))


def test_build_clarity_regenerates_stale_v1():
    tmp_project = _make_project()
    idea = {
        "text": IDEA_07_TEXT,
        "clarity": {"version": 1, "headline_fr": "Copier un mécanisme concret"},
    }
    c = build_clarity(idea, tmp_project, mode="demo")
    assert c["version"] == CLARITY_VERSION
    assert "Copier un mécanisme concret" not in c["headline_fr"]


def test_parse_clarity_response_yaml_blocks():
    raw = """
### En clair — Idea 1
headline_fr: Faire évoluer Discover Weekly discrètement.
pour_vous: Les changements commencent invisibles. Pour la bulle de goût Spotify.
actions:
- Repérer 3 signaux d'écoute faibles.
- Insérer un titre hors bulle sans annonce.
- Mesurer la ré-ouverture à J+7.
test: Montrer la playlist à quelqu'un — noter s'il voit un changement.
"""
    parsed = parse_clarity_response(raw)
    assert 1 in parsed
    c = parsed[1]
    assert c["version"] == CLARITY_VERSION
    assert "Discover Weekly" in c["headline_fr"]
    assert len(c["actions"]) == 3
    assert "30" not in c["test"] or "playlist" in c["test"].lower()


def test_build_clarity_prompt_includes_brief():
    ideas = [{"idea_num": 1, "text": "Test idea about recommendations."}]
    prompt = build_clarity_prompt(ideas, SPOTIFY_BRIEF, {"text_id": "T01"})
    assert "Discover Weekly" in prompt
    assert "Test idea" in prompt
    assert "meta-instructions" in prompt.lower() or "Forbidden" in prompt
