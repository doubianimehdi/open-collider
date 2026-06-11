---
name: open-collider-brainstorm
description: "Codex equivalent of Open Collider's Claude Code /brainstorm command. Use when the user asks to run, continue, resume, curate, flag, inspect, or close an Open Collider brainstorm; when migrating Claude Code brainstorm workflows to Codex; or when a configured project uses llm_provider: codex/openai/anthropic and needs the complete domains, ideas, scoring, curation, and love/like/trash loop. For project creation or /collider_setup, use $open-collider-setup instead."
---

# Open Collider Brainstorm

## Command Equivalent

This is the Codex equivalent of Claude Code's `/brainstorm` command.

If the user asks to create or configure a project, use `$open-collider-setup`
first. Do not run brainstorm until setup is complete and the user asks to
continue.

## Core rule

Do not stop after `BrainstormOrchestrator.run_iteration()`. A complete Open Collider brainstorm includes:

1. domain generation,
2. idea generation,
3. scoring and thresholding,
4. Codex curation into `curated_ideas.json` and `insights_without_collision.json`,
5. user flags `love / like / trash`,
6. `apply_flags()` and regenerated reports.

If the user only asks for a raw API smoke test, say explicitly that curation is skipped.

## Repository context

Run commands from the Open Collider repository root. Prefer `.venv/bin/python` when it exists. Always insert the repo `src/` path before importing local modules.

Helpful scripts bundled with this skill:

- `scripts/run_iteration.py`: run one API-mode iteration and print JSON.
- `scripts/apply_flags_from_text.py`: parse `love 1,3 — like 2 — trash the rest`, map display numbers to idea IDs, call `apply_flags()`, and regenerate reports.

Use reference details only when needed:

- `references/curation.md`: exact curation criteria and file shapes.
- `references/terminal-usage.md`: terminal commands for installing and exercising the skill.

## Workflow

If the user asks to create a new Open Collider project, hand off to
`$open-collider-setup` first.

### 1. Orient

List `projects/` excluding `_template`. If there is one project, use it. If there are several and the user did not specify one, ask which project to run.

Inspect `project_config.yaml`. For Codex-only runs, the project should contain:

```yaml
llm_backend: api
llm_provider: codex
domain_model: default
generation_model: default
scoring_model: default
max_concurrent: 1
max_concurrent_scoring: 1
```

If the config is not Codex-ready and the user asked for Codex-only, edit the project config before running.

### 2. Run one iteration

Use the bundled script or equivalent Python:

```bash
python /path/to/open-collider-brainstorm/scripts/run_iteration.py projects/my_project
```

If resuming a specific brainstorm:

```bash
python /path/to/open-collider-brainstorm/scripts/run_iteration.py projects/my_project --brainstorm-id brainstorm_001
```

If network or home-directory access is required for `codex exec`, request escalation. Do not work around a rejected escalation.

### 2b. Curate an existing raw iteration

If the user asks to curate an existing run, or if `iter_NNN/scored_ideas.json` exists but `curated_ideas.json` is missing, do not rerun generation. Start at step 3 using that existing iteration.

Useful prompt:

```text
Use $open-collider-brainstorm to curate existing brainstorm_001 iteration 1 for projects/my_project. Do not rerun generation.
```

### 3. Curate immediately

Read all ideas from `iter_NNN/scored_ideas.json`, both retained and non-retained. Read `brief_validated.json` from the project root.

Select the best 10-20 ideas with the criteria in `references/curation.md`. Be selective: a smaller strong set is better than a long mediocre set.

Write:

- `iter_NNN/curated_ideas.json`
- `iter_NNN/insights_without_collision.json`

Then call:

```python
from open_collider.skill_interface import mark_curated, generate_report

mark_curated(project_dir)
generate_report(project_dir)
```

### 4. Display and ask for flags

Display every curated idea and every insight without rewriting the `text` field. Use continuous numbering across both lists, then save the same mapping to:

```text
iter_NNN/numbering_map.json
```

Mapping shape:

```json
[
  {"number": 1, "idea_id": "...", "kind": "curated"},
  {"number": 2, "idea_id": "...", "kind": "insight"}
]
```

Ask the user:

```text
Flag each idea: love (want more like this), like (interesting), or trash (not useful).
Format: love 1,3,7 - like 2,5 - trash the rest
```

Stop and wait for the user's flags.

### 5. Apply flags

When the user provides flags, parse them with:

```bash
python /path/to/open-collider-brainstorm/scripts/apply_flags_from_text.py projects/my_project 1 "love 1,3 - like 2 - trash the rest"
```

This calls `apply_flags(project_dir, iteration, flags)` and regenerates reports.

### 6. Continue or close

Ask whether the user wants:

- next iteration,
- brief revision,
- done.

If done, call `generate_brainstorm_report(project_dir)` and point the user to `REPORT.md`.

## Codex-specific behavior

For Codex-only projects, treat `default` as the safest model value. It lets the local Codex CLI choose the model supported by the user's account.

Do not use Anthropic or OpenAI API keys unless the user explicitly asks. If the config says `llm_provider: codex`, all unprefixed model names must be Codex-compatible.

`projects/*` may be gitignored in this repository. Mention that outputs can exist without appearing in `git status`.
