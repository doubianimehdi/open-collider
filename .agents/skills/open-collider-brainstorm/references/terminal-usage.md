# Terminal usage

Install the skill for Codex discovery:

```bash
mkdir -p ~/.codex/skills
cp -R .agents/skills/open-collider-setup ~/.codex/skills/
cp -R .agents/skills/open-collider-brainstorm ~/.codex/skills/
```

Run the Codex equivalent of `/collider_setup` from the Open Collider repo:

```bash
codex "Use $open-collider-setup to create a new Open Collider project configured for Codex-only API mode."
```

Run the Codex equivalent of `/brainstorm`:

```bash
codex "Use $open-collider-brainstorm to run a complete brainstorm for projects/namerkit_pulsed_naming with Codex-only API mode. Do the post-run curation and ask me for love/like/trash flags."
```

Smoke-test the Python provider without a project brief:

```bash
.venv/bin/python - <<'PY'
from open_collider.llm.client import LLMClient
print(LLMClient(provider="codex").call("default", "Reply exactly: codex provider ok"))
PY
```

Run a raw iteration manually:

```bash
python ~/.codex/skills/open-collider-brainstorm/scripts/run_iteration.py projects/namerkit_pulsed_naming
```

Apply flags after Codex has displayed curated ideas and written `numbering_map.json`:

```bash
python ~/.codex/skills/open-collider-brainstorm/scripts/apply_flags_from_text.py projects/namerkit_pulsed_naming 1 "love 1,3 - like 2,5 - trash the rest"
```
