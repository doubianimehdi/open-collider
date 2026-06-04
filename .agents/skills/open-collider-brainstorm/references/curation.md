# Open Collider curation

Use this after `run_iteration()` creates `scored_ideas.json`.

## Inputs

- `projects/<name>/brief_validated.json`
- `projects/<name>/brainstorms/<brainstorm_id>/iter_NNN/scored_ideas.json`

Read all scored ideas, including non-retained ideas. Do not trust score alone.

## Pass 1: collision ideas

For each idea, keep it only if all filters pass:

1. Real collision: the distant domain mechanism changes the idea structurally.
2. Verifiable: factual claims are named or checkable; if the idea makes important external claims, verify them.
3. Non-trivial: the idea would not appear from a vanilla prompt.
4. Project voice: the idea fits the brief, audience, taste, and constraints.

Deduplicate aggressively. If two ideas express the same mechanism, keep the stronger one.

Write `curated_ideas.json`:

```json
[
  {
    "rank": 1,
    "idea_id": "...",
    "text": "full original idea text",
    "combo": "...",
    "score": 4.65,
    "has_collision": true,
    "why_selected": "One sentence.",
    "source_note": "What is verifiable, or why no external claim needs verification.",
    "challenge": "Strongest objection."
  }
]
```

## Pass 2: insights without collision

Keep ideas that fail only the real-collision test but are still strong, non-trivial, and on-brief.

Write `insights_without_collision.json`:

```json
[
  {
    "rank": 1,
    "idea_id": "...",
    "text": "full original idea text",
    "combo": "...",
    "score": 4.35,
    "has_collision": false,
    "why_kept": "One sentence."
  }
]
```

## Display requirements

After writing curation files, display all curated items with exact `text`. Do not summarize candidate names or rewrite territory text.

Use continuous display numbers across both files and save `numbering_map.json` so flags can be applied deterministically later.
