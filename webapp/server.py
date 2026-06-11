"""Open Collider web UI — FastAPI backend.

Run from the repo root:
    uvicorn webapp.server:app --reload --port 8714
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from open_collider.skill_interface import (
    list_brainstorms,
    start_new_brainstorm,
    apply_flags,
    generate_brainstorm_report,
    _load_state,
)
from webapp import settings as app_settings
from webapp.orchestrator import RUNS, OpenAICompatLLM, start_run

WEBAPP_DIR = Path(__file__).resolve().parent
REPO_ROOT = WEBAPP_DIR.parent
PROJECTS_DIR = REPO_ROOT / "projects"
TEMPLATE_DIR = PROJECTS_DIR / "_template"
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Open Collider UI")


# ======================================================================
# Helpers
# ======================================================================

def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not slug:
        raise HTTPException(400, "Invalid project name")
    return slug


def _project_dir(name: str) -> Path:
    path = (PROJECTS_DIR / name).resolve()
    if not path.is_relative_to(PROJECTS_DIR) or path.name.startswith("_"):
        raise HTTPException(404, "Project not found")
    if not path.is_dir():
        raise HTTPException(404, f"Project '{name}' not found")
    return path


def _read_json(path: Path, default=None):
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


# ======================================================================
# Schemas
# ======================================================================

class TextInput(BaseModel):
    title: str
    content: str
    forbidden_topics: list[str] = Field(default_factory=list)


class ProjectCreate(BaseModel):
    name: str
    objective: str
    context: str = ""
    constraints: str = ""
    what_makes_good_ideas: str = ""
    forbidden_topics: list[str] = Field(default_factory=list)
    output_format: str = "Each idea: 2-4 sentences. Free format."
    texts: list[TextInput]


class RunRequest(BaseModel):
    brainstorm_id: str | None = None   # None -> start a new session
    mode: str = "demo"                 # demo | live


class FlagsRequest(BaseModel):
    flags: dict[str, str]              # idea_id -> loved | liked | trashed
    feedback: str = ""


# ======================================================================
# Status & settings
# ======================================================================

@app.get("/api/status")
def status():
    s = app_settings.load_settings()
    return {
        "provider": s["provider"],
        "live_available": app_settings.live_available(s),
    }


class SettingsUpdate(BaseModel):
    provider: str | None = None
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    models: dict | None = None
    pipeline: dict | None = None


@app.get("/api/settings")
def get_settings():
    return app_settings.public_settings()


@app.post("/api/settings")
def post_settings(body: SettingsUpdate):
    update = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        app_settings.save_settings(update)
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, f"Invalid settings value: {exc}")
    return app_settings.public_settings()


@app.post("/api/settings/test")
def test_settings():
    """One tiny LLM call with the saved settings to verify connectivity."""
    s = app_settings.load_settings()
    if s["provider"] == "demo":
        return {"ok": True, "message": "Demo mode needs no connection — it always works."}

    if s["provider"] == "anthropic":
        if not s["anthropic_api_key"]:
            return {"ok": False, "message": "No Anthropic API key saved yet."}
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return {"ok": False, "message":
                    "The 'anthropic' package is not installed. Run: pip install -e \".[api]\""}
        from open_collider.llm.client import LLMClient, LLMError
        try:
            model = app_settings.effective_models(s)["scoring_model"]
            LLMClient().call(model=model, prompt="Reply with the single word: ok",
                             temperature=0, max_tokens=10)
            return {"ok": True, "message": f"Connected — {model} responded."}
        except (LLMError, Exception) as exc:
            return {"ok": False, "message": f"Connection failed: {exc}"}

    # OpenAI-compatible
    try:
        model = app_settings.effective_models(s)["scoring_model"]
        client = OpenAICompatLLM(s["openai_base_url"], s["openai_api_key"], retries=1)
        client.call(model=model, prompt="Reply with the single word: ok",
                    temperature=0, max_tokens=10)
        return {"ok": True, "message": f"Connected — {model} responded at {s['openai_base_url']}."}
    except Exception as exc:
        return {"ok": False, "message": f"Connection failed: {exc}"}


# ======================================================================
# Projects
# ======================================================================

@app.get("/api/projects")
def get_projects():
    results = []
    if PROJECTS_DIR.is_dir():
        for entry in sorted(PROJECTS_DIR.iterdir()):
            if not entry.is_dir() or entry.name.startswith("_") or entry.name.startswith("."):
                continue
            brief = _read_json(entry / "brief_validated.json", {})
            bank = {}
            bank_path = entry / "input_bank.yaml"
            if bank_path.is_file():
                bank = yaml.safe_load(bank_path.read_text(encoding="utf-8")) or {}
            brainstorms = list_brainstorms(str(entry))
            state = _load_state(entry)
            results.append({
                "name": entry.name,
                "objective": brief.get("objective", ""),
                "n_texts": len(bank.get("text_inputs", {})),
                "n_brainstorms": len(brainstorms),
                "total_ideas": state.get("total_ideas_generated", 0),
                "total_loved": state.get("total_loved", 0),
            })
    return results


@app.post("/api/projects")
def create_project(body: ProjectCreate):
    if not body.texts or not any(t.content.strip() for t in body.texts):
        raise HTTPException(400, "At least one reference text with content is required")
    slug = _slugify(body.name)
    path = PROJECTS_DIR / slug
    if path.exists():
        raise HTTPException(409, f"Project '{slug}' already exists")

    (path / "texts").mkdir(parents=True)
    if (TEMPLATE_DIR / "prompts").is_dir():
        shutil.copytree(TEMPLATE_DIR / "prompts", path / "prompts")

    brief = {
        "objective": body.objective,
        "context": body.context,
        "constraints": body.constraints,
        "what_makes_good_ideas": body.what_makes_good_ideas,
        "forbidden_topics": body.forbidden_topics,
    }
    (path / "brief_validated.json").write_text(
        json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")

    text_inputs = {}
    for i, t in enumerate([t for t in body.texts if t.content.strip()], 1):
        tid = f"T{i:02d}"
        (path / "texts" / f"{tid}.txt").write_text(t.content, encoding="utf-8")
        text_inputs[tid] = {
            "title": t.title or tid,
            "file_path": f"texts/{tid}.txt",
            "forbidden_topics": t.forbidden_topics,
        }
    (path / "input_bank.yaml").write_text(
        yaml.dump({"text_inputs": text_inputs}, allow_unicode=True, sort_keys=False),
        encoding="utf-8")

    (path / "project_config.yaml").write_text(
        yaml.dump({"output_format": body.output_format}, allow_unicode=True),
        encoding="utf-8")

    return {"name": slug}


@app.get("/api/projects/{name}")
def get_project(name: str):
    path = _project_dir(name)
    brief = _read_json(path / "brief_validated.json", {})
    bank_path = path / "input_bank.yaml"
    bank = yaml.safe_load(bank_path.read_text(encoding="utf-8")) if bank_path.is_file() else {}
    texts = []
    for tid, meta in (bank or {}).get("text_inputs", {}).items():
        file_path = path / meta.get("file_path", "")
        content = file_path.read_text(encoding="utf-8") if file_path.is_file() else ""
        texts.append({
            "id": tid,
            "title": meta.get("title", tid),
            "chars": len(content),
            "preview": content[:240],
            "forbidden_topics": meta.get("forbidden_topics", []),
        })
    state = _load_state(path)

    brainstorms = []
    for b in list_brainstorms(str(path)):
        bdir = path / "brainstorms" / b["brainstorm_id"]
        iters = []
        for idir in sorted(bdir.iterdir()):
            if not idir.is_dir() or not idir.name.startswith("iter_"):
                continue
            cfg = _read_json(idir / "config.json", {})
            flags = _read_json(idir / "flags.json")
            curated = _read_json(idir / "curated_ideas.json", [])
            iters.append({
                "iteration": cfg.get("iteration") or int(idir.name.split("_")[1]),
                "generated": cfg.get("ideas_generated", 0),
                "retained": cfg.get("ideas_retained", 0),
                "curated": len(curated),
                "flagged": flags is not None,
                "strategies": cfg.get("strategies_used", []),
            })
        has_report = (bdir / "REPORT.md").is_file()
        has_html_report = (bdir / "REPORT.html").is_file()
        brainstorms.append({
            **b,
            "iterations_detail": iters,
            "has_report": has_report,
            "has_html_report": has_html_report,
        })

    return {
        "name": name,
        "brief": brief,
        "texts": texts,
        "state": {
            "brainstorm_id": state.get("brainstorm_id", ""),
            "status": state.get("status", "new"),
            "current_iteration": state.get("current_iteration", 0),
        },
        "brainstorms": brainstorms,
    }


# ======================================================================
# Runs
# ======================================================================

@app.post("/api/projects/{name}/run")
def run_iteration(name: str, body: RunRequest):
    path = _project_dir(name)
    if body.mode not in ("demo", "live"):
        raise HTTPException(400, "mode must be 'demo' or 'live'")
    if body.mode == "live" and not app_settings.live_available():
        raise HTTPException(400, "Live mode is not configured — open Settings to add a provider and API key")
    # Refuse parallel runs on the same project
    for run in RUNS.values():
        if run.project == name and run.status == "running":
            raise HTTPException(409, "A run is already in progress for this project")
    brainstorm_id = body.brainstorm_id or start_new_brainstorm(str(path))
    run = start_run(path, brainstorm_id, body.mode)
    return {"run_id": run.run_id, "brainstorm_id": brainstorm_id}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, since: int = 0):
    run = RUNS.get(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run.snapshot(since)


# ======================================================================
# Iterations / curation
# ======================================================================

@app.get("/api/projects/{name}/brainstorms/{bid}/iterations/{n}")
def get_iteration(name: str, bid: str, n: int):
    path = _project_dir(name)
    iter_dir = path / "brainstorms" / bid / f"iter_{n:03d}"
    if not iter_dir.is_dir():
        raise HTTPException(404, "Iteration not found")
    cfg = _read_json(iter_dir / "config.json", {})
    curated = _read_json(iter_dir / "curated_ideas.json", [])
    flags = _read_json(iter_dir / "flags.json", {})
    scored = _read_json(iter_dir / "scored_ideas.json", [])
    feedback_path = iter_dir / "feedback.txt"
    feedback = feedback_path.read_text(encoding="utf-8") if feedback_path.is_file() else ""

    domains = {}
    domains_dir = iter_dir / "domains"
    if domains_dir.is_dir():
        for f in sorted(domains_dir.glob("*.yaml")):
            bank = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            domains[f.stem] = [
                {"id": sid, "name": s.get("name", sid),
                 "domains": [
                     {"name": d.get("name", ""), "active_principle": d.get("active_principle", "")}
                     for d in (s.get("domains") or [])
                 ]}
                for sid, s in (bank.get("sets") or {}).items()
            ]

    score_values = [i.get("score_aggregate", 0) for i in scored]
    return {
        "config": cfg,
        "curated": curated,
        "flags": flags,
        "feedback": feedback,
        "domains": domains,
        "has_html_report": (iter_dir / "ITER_REPORT.html").is_file(),
        "stats": {
            "scored": len(scored),
            "retained": sum(1 for i in scored if i.get("retained")),
            "score_min": min(score_values) if score_values else 0,
            "score_max": max(score_values) if score_values else 0,
            "threshold": scored[0].get("threshold_used") if scored else None,
            "histogram": _histogram(score_values),
        },
    }


def _histogram(values: list[float], bins: int = 16, lo: float = 1.0, hi: float = 5.0):
    counts = [0] * bins
    for v in values:
        idx = min(int((v - lo) / (hi - lo) * bins), bins - 1)
        counts[max(idx, 0)] += 1
    return counts


@app.post("/api/projects/{name}/brainstorms/{bid}/iterations/{n}/flags")
def post_flags(name: str, bid: str, n: int, body: FlagsRequest):
    path = _project_dir(name)
    iter_dir = path / "brainstorms" / bid / f"iter_{n:03d}"
    if not iter_dir.is_dir():
        raise HTTPException(404, "Iteration not found")
    # Make sure global state points at this brainstorm before applying
    state = _load_state(path)
    if state.get("brainstorm_id") != bid:
        from open_collider.skill_interface import _save_state
        state["brainstorm_id"] = bid
        _save_state(path, state)
    if body.feedback.strip():
        (iter_dir / "feedback.txt").write_text(body.feedback.strip(), encoding="utf-8")
    apply_flags(str(path), n, body.flags)
    return {"ok": True}


# ======================================================================
# Reports
# ======================================================================

@app.post("/api/projects/{name}/brainstorms/{bid}/report")
def make_report(name: str, bid: str):
    path = _project_dir(name)
    state = _load_state(path)
    if state.get("brainstorm_id") != bid:
        from open_collider.skill_interface import _save_state
        state["brainstorm_id"] = bid
        _save_state(path, state)
    report = generate_brainstorm_report(str(path))
    return {"markdown": report}


@app.get("/api/projects/{name}/brainstorms/{bid}/report")
def get_report(name: str, bid: str):
    path = _project_dir(name)
    report_path = path / "brainstorms" / bid / "REPORT.md"
    if not report_path.is_file():
        raise HTTPException(404, "No report yet")
    html_path = path / "brainstorms" / bid / "REPORT.html"
    return {
        "markdown": report_path.read_text(encoding="utf-8"),
        "has_html": html_path.is_file(),
    }


@app.get("/api/projects/{name}/brainstorms/{bid}/report.html")
def get_report_html(name: str, bid: str):
    path = _project_dir(name)
    html_path = path / "brainstorms" / bid / "REPORT.html"
    if not html_path.is_file():
        raise HTTPException(404, "No HTML report yet — generate the session report first")
    return FileResponse(str(html_path), media_type="text/html; charset=utf-8")


@app.get("/api/projects/{name}/brainstorms/{bid}/iterations/{n}/report.html")
def get_iter_report_html(name: str, bid: str, n: int):
    path = _project_dir(name)
    html_path = path / "brainstorms" / bid / f"iter_{n:03d}" / "ITER_REPORT.html"
    if not html_path.is_file():
        raise HTTPException(404, "No iteration HTML report yet — submit curation flags first")
    return FileResponse(str(html_path), media_type="text/html; charset=utf-8")


# ======================================================================
# Static frontend
# ======================================================================

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/manuel")
def manuel():
    path = WEBAPP_DIR / "MANUEL.md"
    if not path.is_file():
        raise HTTPException(404, "Manual not found")
    return FileResponse(str(path), media_type="text/markdown; charset=utf-8")


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))
