"""Load text inputs and domain banks from project files."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class DataLoadError(Exception):
    """Data loading error."""


@dataclass
class TextInputMeta:
    id: str
    title: str
    file_path: str
    forbidden_topics: list[str] = field(default_factory=list)


@dataclass
class DomainEntry:
    name: str
    active_principle: str


@dataclass
class DomainSetMeta:
    id: str
    name: str
    domains: list[DomainEntry] = field(default_factory=list)


class DataLoader:
    """Loads text inputs and domain banks from project files."""

    def __init__(
        self,
        base_dir: str | Path = ".",
        project_dir: str | Path | None = None,
        domain_bank_data: dict | None = None,
    ) -> None:
        self._base_dir = Path(base_dir)
        self._project_dir = Path(project_dir) if project_dir else self._base_dir
        self._domain_bank_override = domain_bank_data
        self._text_inputs: dict[str, TextInputMeta] | None = None
        self._domain_sets: dict[str, DomainSetMeta] | None = None

    def load_text_input(self, text_id: str) -> tuple[TextInputMeta, str]:
        """Load text input metadata and content."""
        text_inputs = self._load_text_inputs()
        meta = text_inputs.get(text_id)
        if not meta:
            raise DataLoadError(f"Unknown text input: {text_id}")
        file_path = self._project_dir / meta.file_path
        if not file_path.is_file():
            raise DataLoadError(f"Text input file not found: {file_path}")
        content = file_path.read_text(encoding="utf-8")
        return meta, content

    def load_domain_set(self, domain_id: str) -> DomainSetMeta:
        """Load a domain set by ID."""
        domain_sets = self._load_domain_sets()
        ds = domain_sets.get(domain_id)
        if not ds:
            raise DataLoadError(f"Unknown domain set: {domain_id}")
        return ds

    def format_domain_list(self, domain_set: DomainSetMeta) -> str:
        """Format domains as markdown list for prompt injection."""
        lines = []
        for i, d in enumerate(domain_set.domains, 1):
            lines.append(f"{i}. **{d.name}** — {d.active_principle}")
        return "\n".join(lines)

    def format_forbidden_topics(self, meta: TextInputMeta) -> str:
        """Format forbidden topics as markdown bullet list."""
        if not meta.forbidden_topics:
            return "(none)"
        return "\n".join(f"- {t}" for t in meta.forbidden_topics)

    def _load_text_inputs(self) -> dict[str, TextInputMeta]:
        if self._text_inputs is not None:
            return self._text_inputs
        bank_path = self._project_dir / "input_bank.yaml"
        if not bank_path.is_file():
            raise DataLoadError(f"input_bank.yaml not found in {self._project_dir}")
        raw = yaml.safe_load(bank_path.read_text(encoding="utf-8")) or {}
        entries = raw.get("text_inputs") or {}
        text_inputs = {}
        for tid, data in entries.items():
            text_inputs[tid] = TextInputMeta(
                id=tid,
                title=data.get("title", tid),
                file_path=data.get("file_path", f"{tid}.txt"),
                forbidden_topics=data.get("forbidden_topics", []),
            )
        self._text_inputs = text_inputs
        return text_inputs

    def _load_domain_sets(self) -> dict[str, DomainSetMeta]:
        if self._domain_sets is not None:
            return self._domain_sets
        if self._domain_bank_override:
            raw = self._domain_bank_override
        else:
            bank_path = self._project_dir / "domain_bank.yaml"
            if not bank_path.is_file():
                raise DataLoadError("domain_bank.yaml not found")
            raw = yaml.safe_load(bank_path.read_text(encoding="utf-8")) or {}
        domain_sets = {}
        for sid, sdata in (raw.get("sets") or {}).items():
            domains = [
                DomainEntry(
                    name=d.get("name", ""),
                    active_principle=d.get("active_principle", ""),
                )
                for d in (sdata.get("domains") or [])
            ]
            domain_sets[sid] = DomainSetMeta(
                id=sid,
                name=sdata.get("name", sid),
                domains=domains,
            )
        self._domain_sets = domain_sets
        return domain_sets
