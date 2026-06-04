"""Tests for API mode — LLM client and orchestrator with mocked Anthropic calls."""

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _create_project(tmp_path: Path) -> Path:
    """Create a minimal project for testing."""
    project = tmp_path / "test_project"
    template = Path(__file__).resolve().parent.parent / "projects" / "_template"
    shutil.copytree(template, project)
    (project / "texts").mkdir(exist_ok=True)
    (project / "texts" / "T01.txt").write_text("Reference text about innovation and disruption.")
    (project / "material").mkdir(exist_ok=True)
    # Set API mode
    with open(project / "project_config.yaml", "a") as f:
        f.write('\nllm_backend: "api"\n')
    return project


# ---- LLM Client tests ----

def test_llm_client_import():
    """LLMClient imports without anthropic installed."""
    from open_collider.llm.client import LLMClient
    client = LLMClient()
    assert client._client is None


def test_llm_client_missing_key():
    """LLMClient raises on missing API key."""
    from open_collider.llm.client import LLMClient, LLMError
    client = LLMClient()
    # Patch both env AND dotenv to ensure no key is found
    with patch.dict("os.environ", {}, clear=True), \
         patch("open_collider.llm.client.os.environ.get", return_value=None):
        with pytest.raises(LLMError, match="Missing ANTHROPIC_API_KEY"):
            client._get_client()


# ---- Orchestrator tests ----

def test_orchestrator_import():
    """BrainstormOrchestrator imports cleanly."""
    from open_collider.brainstorm import BrainstormOrchestrator
    assert BrainstormOrchestrator is not None


def test_orchestrator_init(tmp_path):
    """BrainstormOrchestrator initializes with a project dir."""
    from open_collider.brainstorm import BrainstormOrchestrator
    project = _create_project(tmp_path)
    orch = BrainstormOrchestrator(project)
    assert orch.project_dir == project
    assert orch.config is not None


def test_orchestrator_with_brainstorm_id(tmp_path):
    """BrainstormOrchestrator accepts a brainstorm_id."""
    from open_collider.brainstorm import BrainstormOrchestrator
    project = _create_project(tmp_path)
    orch = BrainstormOrchestrator(project, brainstorm_id="brainstorm_001")
    assert orch.brainstorm_id == "brainstorm_001"


def test_check_condition():
    """_check_condition evaluates strategy conditions."""
    from open_collider.brainstorm import BrainstormOrchestrator
    state_loved = {"has_loved": True, "has_liked": False}
    state_empty = {"has_loved": False, "has_liked": False}

    assert BrainstormOrchestrator._check_condition("always", state_empty) is True
    assert BrainstormOrchestrator._check_condition("has_loved", state_loved) is True
    assert BrainstormOrchestrator._check_condition("has_loved", state_empty) is False
    assert BrainstormOrchestrator._check_condition("has_loved_or_liked", state_loved) is True
    assert BrainstormOrchestrator._check_condition("has_loved_or_liked", state_empty) is False


MOCK_DOMAIN_YAML = """sets:
  DS1:
    name: "Test Domain Family"
    domains:
      - name: "Test Specialty"
        active_principle: "A specialist whose work reveals something counter-intuitive."
  DS2:
    name: "Another Family"
    domains:
      - name: "Another Specialty"
        active_principle: "Another mechanism."
"""

MOCK_IDEAS_RESPONSE = """## Idea 1
**Hook:** Test hook one
**Angle:** Test angle one about legal mechanisms.

---

## Idea 2
**Hook:** Test hook two
**Angle:** Test angle two about different mechanisms.
"""

def _make_scoring_response(n_ideas: int) -> str:
    """Generate a scoring table for n ideas."""
    lines = ["| # | Orig. | Resist. | Thesis | Ground. | Cogn. | SCORE |",
             "|---|-------|---------|--------|---------|-------|-------|"]
    for i in range(1, n_ideas + 1):
        score = round(4.0 + (i % 5) * 0.2, 2)
        lines.append(f"| {i} | 4 | 4 | 4 | 4 | 4 | **{score}** |")
    lines.append("")
    for i in range(1, min(n_ideas + 1, 6)):
        lines.append(f"> ✓ Idea #{i} — Score 4.20 — Good idea")
    return "\n".join(lines)



def test_full_iteration_mocked(tmp_path):
    """Full run_iteration with mocked LLM calls."""
    from open_collider.brainstorm import BrainstormOrchestrator

    project = _create_project(tmp_path)

    def mock_llm_call(model, prompt, temperature=0.7, max_tokens=8000):
        if temperature == 0.5:
            return f"```yaml\n{MOCK_DOMAIN_YAML}```"
        if temperature == 0.1:
            # Count ideas in the scoring prompt (numbered lines like "1. ")
            import re
            idea_nums = re.findall(r"^(\d+)\. ", prompt, re.MULTILINE)
            n = len(idea_nums) if idea_nums else 25
            return _make_scoring_response(n)
        return MOCK_IDEAS_RESPONSE

    orch = BrainstormOrchestrator(project)
    orch.llm = MagicMock()
    orch.llm.call = mock_llm_call

    result = orch.run_iteration()

    assert result["iteration"] == 1
    assert result["ideas_generated"] > 0
    assert "strategies_detail" in result

    # Verify files were created
    brainstorm_dir = project / "brainstorms" / "brainstorm_001"
    assert brainstorm_dir.is_dir()
    iter_dir = brainstorm_dir / "iter_001"
    assert iter_dir.is_dir()
    assert (iter_dir / "scored_ideas.json").is_file()
    assert (iter_dir / "config.json").is_file()
    assert (iter_dir / "ITER_REPORT.html").is_file()
    assert (brainstorm_dir / "REPORT.html").is_file()

    html = (brainstorm_dir / "REPORT.html").read_text(encoding="utf-8")
    assert "Raw Retained Pool" in html
    assert "Test hook one" in html

    # Verify scored ideas have the right structure
    scored = json.loads((iter_dir / "scored_ideas.json").read_text())
    assert len(scored) > 0
    for idea in scored:
        assert "idea_id" in idea
        assert "text" in idea
        assert "retained" in idea


def test_iter_html_prioritizes_curation_without_repeating_card_title(tmp_path):
    """HTML reports show curated output first and do not repeat titles in card bodies."""
    from open_collider.skill_interface import generate_iter_html_report, start_new_brainstorm

    project = _create_project(tmp_path)
    brainstorm_id = start_new_brainstorm(str(project))
    brainstorm_dir = project / "brainstorms" / brainstorm_id
    iter_dir = brainstorm_dir / "iter_001"
    iter_dir.mkdir()

    (iter_dir / "config.json").write_text(json.dumps({
        "iteration": 1,
        "ideas_generated": 3,
        "ideas_retained": 1,
    }))
    (iter_dir / "scored_ideas.json").write_text(json.dumps([{
        "idea_id": "raw_1",
        "text": "Raw Retained Title\n\nProblem targeted: raw body",
        "retained": True,
        "score_aggregate": 4.2,
        "combo": "T01_raw",
    }]))
    (iter_dir / "curated_ideas.json").write_text(json.dumps([{
        "rank": 1,
        "idea_id": "curated_1",
        "text": "Curated Title\n\nProblem targeted: curated body",
        "score": 4.6,
        "combo": "T01_curated",
        "why_selected": "Strong curated mechanism.",
    }]))
    (iter_dir / "insights_without_collision.json").write_text(json.dumps([{
        "rank": 1,
        "idea_id": "insight_1",
        "text": "Insight Title\n\nProblem targeted: insight body",
        "score": 4.1,
        "combo": "T01_insight",
        "why_kept": "Useful standalone insight.",
    }]))
    (iter_dir / "numbering_map.json").write_text(json.dumps([
        {"number": 1, "idea_id": "curated_1", "kind": "curated"},
        {"number": 2, "idea_id": "insight_1", "kind": "insight"},
    ]))

    html = generate_iter_html_report(str(project), 1)

    assert html.index("Curated Ideas") < html.index("Insights Without Collision")
    assert html.index("Insights Without Collision") < html.index("Raw Retained Pool")
    assert 'class="comparison-grid"' not in html
    assert 'class="idea-section curated-priority"' in html
    assert 'class="idea-section insights-compact"' in html
    assert 'class="idea-section raw-pool"' in html
    assert "repeat(2, minmax(0, 1fr))" in html
    assert ".raw-pool .idea-grid" in html
    assert "top: 0;" in html
    assert "bottom: 0;" in html
    assert html.count("Curated Title") == 1
    assert html.count("Insight Title") == 1
    assert html.count("Raw Retained Title") == 1


def test_apply_flags_mocked(tmp_path):
    """Flags work after a mocked iteration."""
    from open_collider.brainstorm import BrainstormOrchestrator

    project = _create_project(tmp_path)

    def mock_llm_call(model, prompt, temperature=0.7, max_tokens=8000):
        if temperature == 0.5:
            return f"```yaml\n{MOCK_DOMAIN_YAML}```"
        if temperature == 0.1:
            import re
            idea_nums = re.findall(r"^(\d+)\. ", prompt, re.MULTILINE)
            n = len(idea_nums) if idea_nums else 25
            return _make_scoring_response(n)
        return MOCK_IDEAS_RESPONSE

    orch = BrainstormOrchestrator(project)
    orch.llm = MagicMock()
    orch.llm.call = mock_llm_call

    orch.run_iteration()

    # Get idea IDs from scored_ideas.json
    brainstorm_dir = project / "brainstorms" / "brainstorm_001"
    iter_dir = brainstorm_dir / "iter_001"
    scored = json.loads((iter_dir / "scored_ideas.json").read_text())

    if scored:
        first_id = scored[0]["idea_id"]
        flags = {first_id: "loved"}
        orch.apply_flags(1, flags)

        # Verify flags were saved
        flags_file = iter_dir / "flags.json"
        assert flags_file.is_file()
        saved_flags = json.loads(flags_file.read_text())
        assert saved_flags[first_id] == "loved"

        # Verify loved_ideas.json was created
        loved_file = brainstorm_dir / "loved_ideas.json"
        assert loved_file.is_file()

        # Verify ITER_REPORT.md was generated
        assert (iter_dir / "ITER_REPORT.md").is_file()


def test_close_session(tmp_path):
    """close_session generates REPORT.md."""
    from open_collider.brainstorm import BrainstormOrchestrator

    project = _create_project(tmp_path)

    def mock_llm_call(model, prompt, temperature=0.7, max_tokens=8000):
        if temperature == 0.5:
            return f"```yaml\n{MOCK_DOMAIN_YAML}```"
        if temperature == 0.1:
            import re
            idea_nums = re.findall(r"^(\d+)\. ", prompt, re.MULTILINE)
            n = len(idea_nums) if idea_nums else 25
            return _make_scoring_response(n)
        return MOCK_IDEAS_RESPONSE

    orch = BrainstormOrchestrator(project)
    orch.llm = MagicMock()
    orch.llm.call = mock_llm_call

    orch.run_iteration()
    report = orch.close_session()

    assert "brainstorm_001" in report
    brainstorm_dir = project / "brainstorms" / "brainstorm_001"
    assert (brainstorm_dir / "REPORT.md").is_file()
    assert (brainstorm_dir / "REPORT.html").is_file()
