# Open Collider — Web UI

A visual interface for the Open Collider semantic collision engine. Create projects,
launch brainstorm iterations, watch collisions happen live, curate ideas with
love / like / trash, and read session reports — all from the browser.

## Quick start

From the repo root:

```bash
pip install -e .                       # install the open_collider package
pip install -r webapp/requirements.txt # install the web UI deps
uvicorn webapp.server:app --port 8714
```

Open http://localhost:8714

## Modes

- **Demo mode** (default, no setup): simulates the full pipeline instantly with
  clearly labeled placeholder ideas. Perfect for exploring the workflow.
- **Live API mode**: real Anthropic calls (Opus for domains, Sonnet for generation
  and scoring). Enable it by installing the API extras and adding your key:

```bash
pip install -e ".[api]"
cp .env.example .env   # then put your ANTHROPIC_API_KEY in .env
```

The mode toggle appears on each project's collision chamber bar.

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
5. **Report** — close the session to get an aggregated REPORT.md, viewable in the
   UI and saved in `projects/<name>/brainstorms/<session>/`.

All artifacts stay on disk in the same structure the CLI/skill flow uses, so the
web UI and Claude Code workflows are interchangeable.
