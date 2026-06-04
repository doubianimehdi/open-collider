"""Tests for API mode — LLM client and orchestrator with mocked Anthropic calls."""

import json
import subprocess
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


def test_llm_client_resolves_provider_prefix():
    """Model names can select a provider without changing project-wide config."""
    from open_collider.llm.client import LLMError, resolve_provider_and_model

    assert resolve_provider_and_model("openai:gpt-4.1", "anthropic") == ("openai", "gpt-4.1")
    assert resolve_provider_and_model("codex:gpt-5-codex", "anthropic") == (
        "codex",
        "gpt-5-codex",
    )
    assert resolve_provider_and_model("anthropic:claude-sonnet-4", "openai") == (
        "anthropic",
        "claude-sonnet-4",
    )
    assert resolve_provider_and_model("claude-sonnet-4", "anthropic") == (
        "anthropic",
        "claude-sonnet-4",
    )
    with pytest.raises(LLMError, match="Unsupported LLM provider prefix"):
        resolve_provider_and_model("opena:gpt-4.1", "anthropic")
    with pytest.raises(LLMError, match="Missing model name"):
        resolve_provider_and_model("openai:", "anthropic")


def test_openai_response_text_extraction():
    """OpenAI Responses API payloads are converted to the plain text contract."""
    from open_collider.llm.client import OpenAIProvider

    payload = {
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "First"},
                    {"type": "output_text", "text": " second"},
                ],
            }
        ]
    }

    assert OpenAIProvider.extract_text(payload) == "First second"


def test_openai_provider_uses_env_base_url(monkeypatch):
    """Responses-compatible local servers can be selected with OPENAI_BASE_URL."""
    from open_collider.llm.client import OpenAIProvider

    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:8000/v1/")

    provider = OpenAIProvider()

    assert provider.base_url == "http://127.0.0.1:8000/v1"


def test_openai_provider_uses_configurable_timeout(monkeypatch):
    """Responses-compatible local servers can use shorter request timeouts."""
    from open_collider.llm.client import LLMClient, OpenAIProvider

    monkeypatch.setenv("OPENAI_TIMEOUT", "42")

    assert OpenAIProvider().timeout == 42
    provider = LLMClient(provider="openai", timeout=7)._get_provider("openai")
    assert isinstance(provider, OpenAIProvider)
    assert provider.timeout == 7


def test_openai_provider_always_uses_responses_api(monkeypatch):
    """OpenAI calls use the Responses API shape."""
    from open_collider.llm.client import OpenAIProvider

    captured = {}

    def fake_post(url, headers, payload, timeout):
        captured["url"] = url
        captured["payload"] = payload
        return {"output_text": "ok"}

    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(OpenAIProvider, "_post_json_urllib", staticmethod(fake_post))

    provider = OpenAIProvider(base_url="http://localhost:8000/v1")

    assert provider.call("test-model", "Prompt", max_tokens=123) == "ok"
    assert captured["url"] == "http://localhost:8000/v1/responses"
    assert captured["payload"]["input"] == "Prompt"
    assert captured["payload"]["max_output_tokens"] == 123
    assert "messages" not in captured["payload"]


def test_openai_urllib_timeout_is_wrapped(monkeypatch):
    """The stdlib fallback reports timeouts through the LLM error contract."""
    from open_collider.llm.client import LLMError, OpenAIProvider

    def timeout(*args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", timeout)

    with pytest.raises(LLMError, match="timed out after 3s"):
        OpenAIProvider._post_json_urllib(
            "http://127.0.0.1:8000/v1/responses",
            {"Content-Type": "application/json"},
            {"model": "test"},
            3,
        )


def test_codex_exec_provider_uses_output_last_message(monkeypatch):
    """Codex CLI provider returns the captured final agent message."""
    from open_collider.llm.client import CodexExecProvider

    captured = {}

    def fake_run(cmd, input, text, capture_output, timeout, check):
        captured["cmd"] = cmd
        captured["input"] = input
        out_path = Path(cmd[cmd.index("--output-last-message") + 1])
        out_path.write_text("Codex answer", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("open_collider.llm.client.shutil.which", lambda name: "/usr/bin/codex")
    monkeypatch.setattr("open_collider.llm.client.subprocess.run", fake_run)

    provider = CodexExecProvider()

    assert provider.call("gpt-5-codex", "Generate YAML") == "Codex answer"
    assert captured["input"] == "Generate YAML"
    assert captured["cmd"][:2] == ["codex", "exec"]
    assert "--ephemeral" in captured["cmd"]
    assert "--ask-for-approval" not in captured["cmd"]
    assert "--output-last-message" in captured["cmd"]
    assert captured["cmd"][-1] == "-"


def test_codex_exec_provider_default_model_omits_model_flag(monkeypatch):
    """Codex-only configs can defer model choice to the local Codex account."""
    from open_collider.llm.client import CodexExecProvider

    captured = {}

    def fake_run(cmd, input, text, capture_output, timeout, check):
        captured["cmd"] = cmd
        out_path = Path(cmd[cmd.index("--output-last-message") + 1])
        out_path.write_text("Codex answer", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("open_collider.llm.client.shutil.which", lambda name: "/usr/bin/codex")
    monkeypatch.setattr("open_collider.llm.client.subprocess.run", fake_run)

    provider = CodexExecProvider()

    assert provider.call("default", "Generate YAML") == "Codex answer"
    assert "--model" not in captured["cmd"]


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


def test_orchestrator_uses_configured_llm_provider(tmp_path):
    """Project config can switch API mode from Anthropic to OpenAI."""
    from open_collider.brainstorm import BrainstormOrchestrator

    project = _create_project(tmp_path)
    with open(project / "project_config.yaml", "a") as f:
        f.write(
            '\nllm_provider: "openai"\n'
            'domain_model: "gpt-4.1"\n'
            'generation_model: "gpt-4.1"\n'
            'scoring_model: "gpt-4.1"\n'
        )

    orch = BrainstormOrchestrator(project)

    assert orch.llm.default_provider == "openai"


def test_orchestrator_supports_codex_only_config_without_api_keys(tmp_path):
    """Codex-only API mode does not require Anthropic or OpenAI credentials at init."""
    from open_collider.brainstorm import BrainstormOrchestrator

    project = _create_project(tmp_path)
    with open(project / "project_config.yaml", "a") as f:
        f.write(
            '\nllm_provider: "codex"\n'
            'domain_model: "default"\n'
            'generation_model: "default"\n'
            'scoring_model: "default"\n'
        )

    with patch.dict("os.environ", {}, clear=True):
        orch = BrainstormOrchestrator(project)

    assert orch.llm.default_provider == "codex"


def test_orchestrator_rejects_unprefixed_claude_models_for_non_anthropic_provider(tmp_path):
    """Switching provider without switching Claude defaults fails early and clearly."""
    from open_collider.brainstorm import BrainstormOrchestrator
    from open_collider.llm.client import LLMError

    project = _create_project(tmp_path)
    with open(project / "project_config.yaml", "a") as f:
        f.write('\nllm_provider: "openai"\n')

    with pytest.raises(LLMError, match="domain_model.*claude-opus"):
        BrainstormOrchestrator(project)


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

    # Verify scored ideas have the right structure
    scored = json.loads((iter_dir / "scored_ideas.json").read_text())
    assert len(scored) > 0
    for idea in scored:
        assert "idea_id" in idea
        assert "text" in idea
        assert "retained" in idea


def test_full_iteration_uses_configured_token_caps(tmp_path):
    """Local model configs can cap each API phase independently."""
    from open_collider.brainstorm import BrainstormOrchestrator

    project = _create_project(tmp_path)
    with open(project / "project_config.yaml", "a") as f:
        f.write(
            "\n"
            "domain_max_tokens: 123\n"
            "generation_max_tokens: 45\n"
            "scoring_max_tokens: 67\n"
        )

    seen = []

    def mock_llm_call(model, prompt, temperature=0.7, max_tokens=8000):
        seen.append((temperature, max_tokens))
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

    assert (0.5, 123) in seen
    assert (0.9, 45) in seen
    assert (0.1, 67) in seen


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
