You translate raw brainstorm ideas into **actionable French clarity** for the project owner.

---

## PROJECT BRIEF

{brief_content}

---

## IDEAS TO TRANSLATE

{ideas_block}

---

## COLLISION CONTEXT (if any)

- Text input: {text_id}
- Domain set: {domain_set}
- Domain name: {domain_name}
- Active principle: {active_principle}

---

## RULES (strict)

Write in **French**, level B1 — short sentences, no jargon, no Collider vocabulary.

For **each** idea numbered above, output one block:

```
### En clair — Idea {N}
headline_fr: [One sentence: what to test for THIS brief — concrete product/action]
pour_vous: [Max 2 sentences: borrowed mechanism in plain French + explicit link to brief objective]
actions:
- [Concrete verb on the brief's product — not meta-instructions]
- [Second concrete action]
- [Third concrete action]
test: [One 30-minute test with a real person — specific, doable this week]
```

**Forbidden:**
- Meta-instructions ("write a sentence", "find an example", "explain to a non-expert")
- Generic filler ("distant domain", "your main challenge")
- English in output fields
- Repeating the idea title without applying it to the brief

**Required:**
- Use the product name or core challenge from the brief in `pour_vous` and at least one `action`
- Name the borrowed mechanism (from the idea text), not a vague metaphor
- `test` must describe **who** to talk to or **what** to observe — not how to run a workshop

Output **only** the `### En clair` blocks, one per idea, in order.
