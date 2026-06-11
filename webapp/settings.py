"""Web UI settings: provider, API keys, models, pipeline tuning.

Stored in webapp/settings.json (gitignored). The Anthropic key is also
mirrored into the repo .env so the core package / Claude Code flow keeps
working unchanged.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

SETTINGS_PATH = Path(__file__).resolve().parent / "settings.json"
REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"

PROVIDERS = ("demo", "anthropic", "openai")

DEFAULT_MODELS = {
    "anthropic": {
        "domain_model": "claude-opus-4-20250514",
        "generation_model": "claude-sonnet-4-20250514",
        "scoring_model": "claude-sonnet-4-20250514",
    },
    "openai": {
        "domain_model": "gpt-4o",
        "generation_model": "gpt-4o-mini",
        "scoring_model": "gpt-4o-mini",
    },
}

DEFAULTS = {
    "provider": "demo",            # demo | anthropic | openai (OpenAI-compatible)
    "anthropic_api_key": "",
    "openai_api_key": "",
    "openai_base_url": "https://api.openai.com/v1",
    "models": {                    # blank = use provider defaults
        "domain_model": "",
        "generation_model": "",
        "scoring_model": "",
    },
    "pipeline": {                  # blank/None = use engine defaults
        "score_threshold": None,       # default 4.2
        "combos_first_iteration": None,  # default 24
        "combos_per_strategy": None,     # default 12
        "max_concurrent": None,          # default 4
    },
}


def _read_env_key() -> str:
    """Read ANTHROPIC_API_KEY from environment or repo .env."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    if ENV_PATH.is_file():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("ANTHROPIC_API_KEY="):
                value = line.split("=", 1)[1].strip()
                if value and "<" not in value:
                    return value
    return ""


def _write_env_key(key: str) -> None:
    """Mirror the Anthropic key into .env (create or update in place)."""
    lines = []
    if ENV_PATH.is_file():
        lines = [
            ln for ln in ENV_PATH.read_text(encoding="utf-8").splitlines()
            if not ln.strip().startswith("ANTHROPIC_API_KEY=")
        ]
    if key:
        lines.append(f"ANTHROPIC_API_KEY={key}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ["ANTHROPIC_API_KEY"] = key


def load_settings() -> dict:
    settings = json.loads(json.dumps(DEFAULTS))  # deep copy
    if SETTINGS_PATH.is_file():
        try:
            saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            saved = {}
        for key, value in saved.items():
            if isinstance(value, dict) and isinstance(settings.get(key), dict):
                settings[key].update(value)
            else:
                settings[key] = value
    # .env / environment wins as the source of truth for the Anthropic key
    env_key = _read_env_key()
    if env_key:
        settings["anthropic_api_key"] = env_key
    return settings


def save_settings(update: dict) -> dict:
    settings = load_settings()
    for key in ("provider", "openai_base_url"):
        if key in update:
            settings[key] = str(update[key]).strip()
    if settings["provider"] not in PROVIDERS:
        settings["provider"] = "demo"
    for key in ("anthropic_api_key", "openai_api_key"):
        # KEEP sentinel = field untouched (the UI never sees the real key)
        if key in update and update[key] != "__KEEP__":
            settings[key] = str(update[key]).strip()
    if "models" in update:
        for k in settings["models"]:
            if k in update["models"]:
                settings["models"][k] = str(update["models"][k] or "").strip()
    if "pipeline" in update:
        for k in settings["pipeline"]:
            if k in update["pipeline"]:
                v = update["pipeline"][k]
                settings["pipeline"][k] = None if v in (None, "", 0) else float(v) if k == "score_threshold" else int(v)

    SETTINGS_PATH.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_env_key(settings["anthropic_api_key"])
    return settings


def mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}…{key[-4:]}"


def public_settings() -> dict:
    """Settings safe to send to the browser (keys masked)."""
    s = load_settings()
    return {
        "provider": s["provider"],
        "anthropic_key_set": bool(s["anthropic_api_key"]),
        "anthropic_key_masked": mask_key(s["anthropic_api_key"]),
        "openai_key_set": bool(s["openai_api_key"]),
        "openai_key_masked": mask_key(s["openai_api_key"]),
        "openai_base_url": s["openai_base_url"],
        "models": s["models"],
        "pipeline": s["pipeline"],
        "default_models": DEFAULT_MODELS,
        "live_available": live_available(s),
    }


def live_available(settings: dict | None = None) -> bool:
    s = settings or load_settings()
    if s["provider"] == "anthropic":
        if not s["anthropic_api_key"]:
            return False
        try:
            import anthropic  # noqa: F401
            return True
        except ImportError:
            return False
    if s["provider"] == "openai":
        # key may legitimately be empty (e.g. Ollama / LM Studio)
        return bool(s["openai_base_url"])
    return False


def effective_models(settings: dict | None = None) -> dict:
    """Model names to use for a live run: explicit value or provider default."""
    s = settings or load_settings()
    defaults = DEFAULT_MODELS.get(s["provider"], DEFAULT_MODELS["anthropic"])
    return {
        k: (s["models"].get(k) or defaults[k])
        for k in ("domain_model", "generation_model", "scoring_model")
    }


def config_overrides(settings: dict | None = None, mode: str = "live") -> dict:
    """Flat dict to merge into the engine config for a run."""
    s = settings or load_settings()
    overrides: dict = {}
    if mode == "live":
        overrides.update(effective_models(s))
    p = s["pipeline"]
    if p.get("score_threshold") is not None:
        overrides["score_threshold"] = p["score_threshold"]
    if p.get("combos_first_iteration") is not None:
        overrides["combos_first_iteration"] = p["combos_first_iteration"]
    if p.get("max_concurrent") is not None:
        overrides["max_concurrent"] = p["max_concurrent"]
    return overrides
