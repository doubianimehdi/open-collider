# Open Collider — Web UI

A visual interface for the Open Collider semantic collision engine. Create projects,
launch brainstorm iterations, watch collisions happen live, curate ideas with
love / like / trash, and read session reports — all from the browser.

**User manual (French):** [`MANUEL.md`](MANUEL.md) — installation, every screen, demo vs live, reports, troubleshooting.

**Fork changelog (PR #1–#3 + Web UI):** [`../CHANGELOG-FORK.md`](../CHANGELOG-FORK.md)

## Quick start

From the repo root:

```bash
pip install -e .                       # install the open_collider package
pip install -r webapp/requirements.txt # install the web UI deps
uvicorn webapp.server:app --port 8714
```

Open http://localhost:8714

## Modes & providers

- **Demo mode** (default, no setup): simulates the full pipeline instantly with
  clearly labeled placeholder ideas. Perfect for exploring the workflow.
- **Live mode**: real LLM calls through the provider you configure in the
  **Settings** page (gear icon in the top bar):
  - **Anthropic** — what the engine was designed and benchmarked on. Requires
    `pip install -e ".[api]"` and an API key (saved to `.env` automatically).
  - **Any OpenAI-compatible API** — OpenAI, OpenRouter, Groq, Mistral, or local
    servers like Ollama / LM Studio. Just set the base URL, key, and model names.

Settings also let you override models per pipeline stage (domains / generation /
scoring) and tune the pipeline (score threshold, collisions per round,
parallelism). Everything is stored locally in `webapp/settings.json` (gitignored).
The per-project DEMO / LIVE toggle appears on each project's collision chamber bar.

## What it does

1. **New project** — define your brief (objective, context, constraints, what makes
   a good idea) and paste reference texts (beam one of the collider).
2. **Start a session** — the engine generates structurally distant domains (beam two),
   collides every text × domain pair in isolated contexts, and scores every idea on
   the 5-axis judge. Progress streams live into the collision chamber view.
3. **Curate** — the top retained ideas are presented as cards with per-axis score
   bars. Flag them love / like / trash and add a steering note.
4. **Iterate** — loved ideas steer the next iteration (deepen + refresh strategies
   activate automatically). Sessions typically exhaust after 3–5 iterations.
5. **Report** — close the session to get an aggregated REPORT.md (and REPORT.html), viewable in the
   UI and saved in `projects/<name>/brainstorms/<session>/`. Per-iteration ITER_REPORT.html
   is generated when you lock in curation feedback.

All artifacts stay on disk in the same structure the CLI/skill flow uses, so the
web UI and Claude Code workflows are interchangeable.
