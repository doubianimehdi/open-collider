"""LLM client facade for API mode."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
import json
from typing import Any

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """LLM call failed."""


SUPPORTED_PROVIDERS = {"anthropic", "openai", "codex"}
MODEL_CONFIG_KEYS = ("domain_model", "generation_model", "scoring_model")


def resolve_provider_and_model(model: str, default_provider: str) -> tuple[str, str]:
    """Resolve optional provider-prefixed model names.

    Examples:
    - ``openai:gpt-4.1`` -> ("openai", "gpt-4.1")
    - ``codex:gpt-5-codex`` -> ("codex", "gpt-5-codex")
    - ``claude-sonnet-4`` with default ``anthropic`` -> ("anthropic", "claude-sonnet-4")
    """
    default = default_provider.strip().lower()
    if default not in SUPPORTED_PROVIDERS:
        raise LLMError(f"Unsupported LLM provider: {default_provider}")

    model_name = model.strip()
    if ":" in model_name:
        prefix, _, prefixed_model = model_name.partition(":")
        provider = prefix.strip().lower()
        if provider not in SUPPORTED_PROVIDERS:
            raise LLMError(f"Unsupported LLM provider prefix: {prefix}")
        if not prefixed_model.strip():
            raise LLMError(f"Missing model name for provider prefix: {provider}")
        return provider, prefixed_model.strip()

    return default, model_name


def validate_provider_model_config(config: dict[str, Any]) -> None:
    """Fail early on provider/model combinations that would hit the wrong API."""
    provider = str(config.get("llm_provider", "anthropic")).strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise LLMError(f"Unsupported LLM provider: {provider}")

    invalid_models = []
    for key in MODEL_CONFIG_KEYS:
        model = str(config.get(key, "")).strip()
        if not model:
            continue
        resolved_provider, resolved_model = resolve_provider_and_model(model, provider)
        if (
            provider != "anthropic"
            and resolved_provider == provider
            and _looks_like_anthropic_model(resolved_model)
        ):
            invalid_models.append(f"{key}={model!r}")

    if invalid_models:
        details = ", ".join(invalid_models)
        raise LLMError(
            f"llm_provider {provider!r} cannot use unprefixed Anthropic model(s): {details}. "
            "Prefix those models with 'anthropic:' to mix providers, or configure models for "
            f"the {provider!r} provider."
        )


def _looks_like_anthropic_model(model: str) -> bool:
    """Return true for the Claude model names used by Anthropic."""
    normalized = model.strip().lower()
    return normalized.startswith(("claude-", "claude_"))


class AnthropicProvider:
    """Anthropic API client with retry on overload."""

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from dotenv import load_dotenv
                load_dotenv()
            except ImportError:
                pass
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise LLMError("Missing ANTHROPIC_API_KEY in environment")
            try:
                import anthropic
            except ImportError:
                raise LLMError(
                    "Package 'anthropic' not installed. Run: pip install open-collider[api]"
                )
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    def call(
        self,
        model: str,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 8000,
    ) -> str:
        """Single Anthropic API call with retry on overload.

        - Up to 5 total attempts on overloaded (4 retries, 3 min backoff each)
        - No retry on rate limit (raises immediately)
        - Streams for opus models (required by API for long requests)
        """
        client = self._get_client()
        import anthropic as anthropic_lib

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }

        max_retries = 5
        retry_wait = 180

        for attempt in range(1, max_retries + 1):
            try:
                if "opus" in model:
                    collected = []
                    with client.messages.stream(**kwargs) as stream:
                        for text in stream.text_stream:
                            collected.append(text)
                    return "".join(collected)
                response = client.messages.create(**kwargs)
                return response.content[0].text or ""
            except anthropic_lib.RateLimitError as e:
                raise LLMError(f"Rate limit: {e}")
            except anthropic_lib.APIStatusError as e:
                if "overloaded" in str(e).lower() and attempt < max_retries:
                    logger.warning(
                        "Overloaded (attempt %d/%d), retry in %ds",
                        attempt, max_retries, retry_wait,
                    )
                    time.sleep(retry_wait)
                    continue
                raise LLMError(f"API error: {e}")

        raise LLMError(f"Failed after {max_retries} attempts")


class OpenAIProvider:
    """OpenAI Responses-compatible API client.

    The endpoint can point at OpenAI or a local server exposing the Responses API via
    ``OPENAI_BASE_URL``. Local servers usually still expect an Authorization
    header, so set ``OPENAI_API_KEY`` to any accepted local token.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: int | None = None,
    ) -> None:
        if base_url is None:
            base_url = (
                os.environ.get("OPENAI_BASE_URL")
                or os.environ.get("OPENAI_API_BASE")
                or "https://api.openai.com/v1"
            )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout or int(os.environ.get("OPENAI_TIMEOUT", "300"))

    def call(
        self,
        model: str,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 8000,
    ) -> str:
        """Single OpenAI Responses-compatible API call."""
        api_key = self._get_api_key()
        payload = {
            "model": model,
            "input": prompt,
            "temperature": temperature,
            "max_output_tokens": max_tokens,
            "store": False,
        }
        url = f"{self.base_url}/responses"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            import httpx
        except ImportError:
            response_payload = self._post_json_urllib(
                url,
                headers,
                payload,
                self.timeout,
            )
        else:
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status == 429:
                    raise LLMError(f"Rate limit: {exc}")
                raise LLMError(f"API error: {exc}")
            except httpx.HTTPError as exc:
                raise LLMError(f"API error: {exc}")
            response_payload = response.json()

        return self.extract_text(response_payload)

    @staticmethod
    def _post_json_urllib(
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout: int,
    ) -> dict[str, Any]:
        """POST JSON with the standard library when optional httpx is absent."""
        import urllib.error
        import urllib.request

        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise LLMError(f"Rate limit: {exc}") from exc
            body = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"API error: HTTP {exc.code}: {body}") from exc
        except TimeoutError as exc:
            raise LLMError(f"API error: timed out after {timeout}s") from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"API error: {exc}") from exc
        return json.loads(raw)

    @staticmethod
    def extract_text(payload: dict[str, Any]) -> str:
        """Extract assistant text from an OpenAI Responses API payload."""
        direct = payload.get("output_text")
        if isinstance(direct, str):
            return direct

        texts: list[str] = []
        for item in payload.get("output", []) or []:
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []) or []:
                if not isinstance(content, dict):
                    continue
                if content.get("type") in {"output_text", "text"}:
                    text = content.get("text")
                    if isinstance(text, str):
                        texts.append(text)

        if texts:
            return "".join(texts)
        raise LLMError("OpenAI response did not contain output text")

    @staticmethod
    def _get_api_key() -> str:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise LLMError("Missing OPENAI_API_KEY in environment")
        return api_key


class CodexExecProvider:
    """Codex CLI non-interactive runner.

    This is intentionally an experimental provider: each call starts a Codex
    agent process and returns its final message.
    """

    def __init__(self, timeout: int | None = None) -> None:
        self.timeout = timeout or int(os.environ.get("CODEX_EXEC_TIMEOUT", "900"))

    def call(
        self,
        model: str,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 8000,
    ) -> str:
        """Run ``codex exec`` and return the captured final message."""
        del temperature, max_tokens  # Codex CLI owns sampling/runtime options.
        if shutil.which("codex") is None:
            raise LLMError("Codex CLI not found in PATH")

        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=True) as output:
            cmd = [
                "codex",
                "exec",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--color",
                "never",
                "--output-last-message",
                output.name,
            ]
            if model and model.strip().lower() != "default":
                cmd.extend(["--model", model])
            cmd.append("-")

            try:
                result = subprocess.run(
                    cmd,
                    input=prompt,
                    text=True,
                    capture_output=True,
                    timeout=self.timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise LLMError(f"Codex exec timed out after {self.timeout}s") from exc

            output.seek(0)
            final_message = output.read().strip()
            if result.returncode != 0:
                stderr = (result.stderr or "").strip()
                raise LLMError(f"Codex exec failed: {stderr or result.returncode}")
            if final_message:
                return final_message
            stdout = (result.stdout or "").strip()
            if stdout:
                return stdout
            raise LLMError("Codex exec produced no output")


class LLMClient:
    """Provider-dispatching API client used by the Python orchestrator."""

    def __init__(
        self,
        provider: str = "anthropic",
        timeout: int | None = None,
    ) -> None:
        provider_name = provider.strip().lower()
        if provider_name not in SUPPORTED_PROVIDERS:
            raise LLMError(f"Unsupported LLM provider: {provider}")
        self.default_provider = provider_name
        self.timeout = timeout
        self._providers: dict[str, AnthropicProvider | OpenAIProvider | CodexExecProvider] = {}
        # Backwards-compatible attribute for older tests and callers.
        self._client = None

    def _get_client(self):
        """Return the Anthropic SDK client for backwards compatibility."""
        provider = self._get_provider("anthropic")
        if not isinstance(provider, AnthropicProvider):
            raise LLMError("Anthropic provider unavailable")
        self._client = provider._get_client()
        return self._client

    def call(
        self,
        model: str,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 8000,
    ) -> str:
        provider_name, resolved_model = resolve_provider_and_model(
            model,
            self.default_provider,
        )
        provider = self._get_provider(provider_name)
        return provider.call(
            model=resolved_model,
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _get_provider(self, provider_name: str) -> AnthropicProvider | OpenAIProvider | CodexExecProvider:
        if provider_name not in self._providers:
            if provider_name == "anthropic":
                self._providers[provider_name] = AnthropicProvider()
            elif provider_name == "openai":
                self._providers[provider_name] = OpenAIProvider(
                    timeout=self.timeout,
                )
            elif provider_name == "codex":
                self._providers[provider_name] = CodexExecProvider(timeout=self.timeout)
            else:
                raise LLMError(f"Unsupported LLM provider: {provider_name}")
        return self._providers[provider_name]
