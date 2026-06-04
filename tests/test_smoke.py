"""Smoke tests for Open Collider v2."""

import shutil
from pathlib import Path


def _create_minimal_project(tmp_path: Path) -> Path:
    project = tmp_path / "test_project"
    template = Path(__file__).resolve().parent.parent / "projects" / "_template"
    shutil.copytree(template, project)
    (project / "texts").mkdir(exist_ok=True)
    (project / "texts" / "T01.txt").write_text("This is a test reference text about innovation.")
    (project / "material").mkdir(exist_ok=True)
    return project


def test_all_imports():
    from open_collider.skill_interface import (
        list_brainstorms, start_new_brainstorm, init_iteration,
        prepare_domain_prompt, parse_domain_response_text,
        prepare_idea_prompts, parse_idea_response,
        prepare_scoring_prompts, parse_scoring_response,
        finalize_iteration, apply_flags, mark_curated, generate_report,
    )
    from open_collider.config import load_config, load_project_config
    from open_collider.scoring.data_loader import DataLoader
    from open_collider.scoring.score_parser import parse_scoring_table, extract_judge_notes
    from open_collider.prompt_resolver import PromptResolver
    from open_collider.phases.idea_generator import IdeaGenerator, sample_combos
    from open_collider.phases.idea_scorer import IdeaScorer, apply_threshold, DEFAULT_WEIGHTS
    from open_collider.strategies.fresh import FreshStrategy
    from open_collider.strategies.deepen import DeepenStrategy
    from open_collider.strategies.refresh import RefreshStrategy

    imported = (
        list_brainstorms, start_new_brainstorm, init_iteration,
        prepare_domain_prompt, parse_domain_response_text,
        prepare_idea_prompts, parse_idea_response,
        prepare_scoring_prompts, parse_scoring_response,
        finalize_iteration, apply_flags, mark_curated, generate_report,
        load_config, load_project_config, DataLoader,
        parse_scoring_table, extract_judge_notes, PromptResolver,
        IdeaGenerator, sample_combos, IdeaScorer, apply_threshold, DEFAULT_WEIGHTS,
        FreshStrategy, DeepenStrategy, RefreshStrategy,
    )
    assert all(imported)


def test_load_config():
    from open_collider.config import load_config
    config = load_config()
    assert "score_threshold" in config
    assert config["score_threshold"] == 4.2


def test_hardcoded_weights():
    from open_collider.phases.idea_scorer import DEFAULT_WEIGHTS
    assert DEFAULT_WEIGHTS["originality"] == 0.25
    assert DEFAULT_WEIGHTS["resistance"] == 0.20
    assert DEFAULT_WEIGHTS["thesis_density"] == 0.20
    assert DEFAULT_WEIGHTS["concrete_grounding"] == 0.20
    assert DEFAULT_WEIGHTS["cognitive_load"] == 0.15
    assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 0.001


def test_init_iteration(tmp_path):
    from open_collider.skill_interface import init_iteration
    project = _create_minimal_project(tmp_path)
    state = init_iteration(str(project))
    assert state["iteration"] == 1
    assert state["has_loved"] is False
    assert state["has_liked"] is False
    assert "brief" in state
    assert "config" in state


def test_list_brainstorms_empty(tmp_path):
    from open_collider.skill_interface import list_brainstorms
    project = _create_minimal_project(tmp_path)
    assert list_brainstorms(str(project)) == []


def test_start_new_brainstorm(tmp_path):
    from open_collider.skill_interface import start_new_brainstorm, list_brainstorms
    project = _create_minimal_project(tmp_path)
    bid = start_new_brainstorm(str(project))
    assert bid == "brainstorm_001"
    brainstorms = list_brainstorms(str(project))
    assert len(brainstorms) == 1


def test_prepare_domain_prompt(tmp_path):
    from open_collider.skill_interface import init_iteration, prepare_domain_prompt
    project = _create_minimal_project(tmp_path)
    state = init_iteration(str(project))
    result = prepare_domain_prompt("fresh", str(project), state)
    assert result is not None
    assert "prompt" in result
    assert "model" in result
    assert len(result["prompt"]) > 100


def test_parse_domain_response():
    from open_collider.skill_interface import parse_domain_response_text
    response = """```yaml
sets:
  DS1:
    name: "Test family"
    domains:
      - name: "Test domain"
        active_principle: "A specialist who studies X"
```"""
    yaml_str = parse_domain_response_text(response)
    assert "DS1" in yaml_str
    assert "Test family" in yaml_str


def test_score_parser():
    from open_collider.scoring.score_parser import parse_scoring_table
    content = "| 1 | 4 | 5 | 3 | 4 | 5 | **4.25** |"
    results = parse_scoring_table(content)
    assert len(results) == 1
    assert results[0].idea_num == 1
    assert results[0].originality == 4.0
    assert results[0].resistance == 5.0
    assert results[0].thesis_density == 3.0
    assert results[0].concrete_grounding == 4.0
    assert results[0].cognitive_load == 5.0
    assert results[0].score_aggregate == 4.25


def test_score_parser_accepts_bold_score_with_denominator():
    from open_collider.scoring.score_parser import parse_scoring_table
    content = "| 1 | 4/5 | 5/5 | 3/5 | 4/5 | 5/5 | **4.25 / 5** |"
    results = parse_scoring_table(content)
    assert len(results) == 1
    assert results[0].score_aggregate == 4.25


def test_judge_notes_bilingual():
    from open_collider.scoring.score_parser import extract_judge_notes
    content = """
> ✓ Idea #3 — Score 4.60 — Strong structural insight
> ✓ Idée #7 — Score 4.20 — Bonne densité de thèse
"""
    notes = extract_judge_notes(content)
    assert 3 in notes
    assert 7 in notes
    assert "Strong structural insight" in notes[3]


def test_apply_threshold():
    from open_collider.phases.idea_scorer import apply_threshold
    ideas = [
        {"idea_num": 1, "score_aggregate": 4.5},
        {"idea_num": 2, "score_aggregate": 3.8},
        {"idea_num": 3, "score_aggregate": 4.1},
    ]
    config = {"score_threshold": 4.2, "drift_threshold": 4.0, "min_ideas_before_drift": 2, "drift_step": 0.1}
    result = apply_threshold(ideas, config)
    retained = [i for i in result if i["retained"]]
    assert len(retained) >= 2


def test_idea_parser():
    from open_collider.phases.idea_generator import IdeaGenerator
    gen = IdeaGenerator({}, None)
    content = """## Idea 1
First idea text here.

## Idea 2
Second idea text here."""
    ideas = gen.parse_response(content, "T01_fresh_DS1")
    assert len(ideas) == 2
    assert ideas[0]["idea_num"] == 1
    assert ideas[1]["idea_num"] == 2


def test_judge_template_exists():
    template = Path(__file__).resolve().parent.parent / "projects" / "_template" / "prompts" / "judge.md"
    assert template.is_file()
    content = template.read_text()
    assert "Structural originality" in content
    assert "Resistance" in content
    assert "Thesis density" in content
    assert "Concrete grounding" in content
    assert "Cognitive load" in content
    assert "{ideas}" in content


def test_no_french():
    """Ensure no French terms in source code."""
    import os
    src_dir = Path(__file__).resolve().parent.parent / "src"
    french_terms = ["mouvement_cognitif", "principe_actif", "rendement", "score_agrege",
                    "originalite", "densite_these", "ancrage_concret", "charge_cognitive"]
    for root, _, files in os.walk(src_dir):
        for f in files:
            if f.endswith(".py") or f.endswith(".yaml"):
                content = (Path(root) / f).read_text(encoding="utf-8")
                for term in french_terms:
                    assert term not in content, f"French term '{term}' found in {f}"
