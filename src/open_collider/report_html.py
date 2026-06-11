"""Standalone HTML reports — clear, visual, brainstorm-friendly exports."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path

import yaml

_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Unbounded:wght@300;400;500&family=Newsreader:ital,opsz,wght@0,6..72,300;0,6..72,400;1,6..72,300&family=Fragment+Mono:ital@0;1&display=swap');

:root {
  --bg: #05070c;
  --panel: #0c111c;
  --panel-2: #101725;
  --line: rgba(160, 190, 255, 0.12);
  --text: #e9edf6;
  --muted: #8b96ad;
  --dim: #5a6478;
  --love: #ff4f6e;
  --like: #ffb454;
  --beam-a: #4fe3c1;
  --spark: #ffb454;
  --display: "Unbounded", system-ui, sans-serif;
  --serif: "Newsreader", Georgia, serif;
  --mono: "Fragment Mono", ui-monospace, monospace;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--bg);
  background-image:
    radial-gradient(ellipse 90% 55% at 50% -10%, rgba(79, 227, 193, 0.08), transparent 60%),
    radial-gradient(ellipse 70% 45% at 90% 100%, rgba(255, 79, 154, 0.06), transparent 55%);
  color: var(--text);
  font-family: var(--serif);
  font-size: 18px;
  line-height: 1.6;
  font-weight: 300;
}

.wrap {
  max-width: 880px;
  margin: 0 auto;
  padding: 48px 28px 80px;
}

.brand {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--beam-a);
  margin-bottom: 20px;
}

h1 {
  font-family: var(--display);
  font-weight: 400;
  font-size: clamp(28px, 5vw, 42px);
  line-height: 1.15;
  margin-bottom: 12px;
  letter-spacing: -0.02em;
}

.dek {
  color: var(--muted);
  font-size: 17px;
  max-width: 640px;
  margin-bottom: 28px;
}

.stats {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 28px 0 40px;
}

.pill {
  font-family: var(--mono);
  font-size: 12px;
  padding: 10px 16px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--panel);
}
.pill.loved { border-color: rgba(255, 79, 110, 0.45); color: var(--love); }
.pill.liked { border-color: rgba(255, 180, 84, 0.4); color: var(--like); }
.pill.neutral { color: var(--muted); }

.howto {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
  margin: 36px 0 48px;
}

.howto-card {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 22px 20px;
  background: var(--panel);
}

.howto-n {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--spark);
  letter-spacing: 0.1em;
  margin-bottom: 8px;
}

.howto-card h3 {
  font-family: var(--display);
  font-size: 14px;
  font-weight: 400;
  margin-bottom: 8px;
}

.howto-card p {
  font-size: 14px;
  color: var(--muted);
  line-height: 1.55;
}

.section {
  margin: 48px 0;
}

.sec-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 10px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--line);
}

.section h2 {
  font-family: var(--display);
  font-weight: 400;
  font-size: 22px;
}

.section.loved h2 { color: var(--love); }
.section.explore h2 { color: var(--like); }

.sec-count {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--dim);
  letter-spacing: 0.08em;
}

.sec-lead {
  color: var(--muted);
  font-size: 15px;
  margin-bottom: 24px;
  max-width: 620px;
}

.ideas { display: flex; flex-direction: column; gap: 20px; }

.idea {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 26px 28px;
  background: var(--panel);
}

.idea.loved {
  border-left: 4px solid var(--love);
  background: rgba(255, 79, 110, 0.04);
}

.idea.liked { border-left: 4px solid var(--like); }

.idea-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.idea-score {
  font-family: var(--display);
  font-size: 24px;
  color: var(--spark);
}

.idea-meta {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--dim);
  letter-spacing: 0.04em;
}

.flag {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 4px 10px;
  border-radius: 4px;
}
.flag.love { background: rgba(255, 79, 110, 0.15); color: var(--love); }
.flag.like { background: rgba(255, 180, 84, 0.12); color: var(--like); }
.flag.trash { background: rgba(90, 100, 120, 0.2); color: var(--dim); }

.idea-body {
  font-size: 17px;
  line-height: 1.65;
  color: var(--text);
}

.idea-body p { margin: 10px 0; }
.idea-body strong { font-weight: 500; color: var(--text); }

.idea-note {
  margin-top: 16px;
  padding: 14px 16px;
  border-left: 2px solid var(--beam-a);
  background: rgba(79, 227, 193, 0.05);
  font-size: 14px;
  font-style: italic;
  color: var(--muted);
  border-radius: 0 8px 8px 0;
}

.idea-prompt {
  margin-top: 14px;
  font-size: 13px;
  color: var(--beam-a);
  font-style: italic;
}

.collision {
  margin: 14px 0;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: rgba(79, 227, 193, 0.04);
  font-size: 14px;
}
.beams {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.beam { flex: 1; min-width: 140px; padding: 8px 12px; border-radius: 6px; background: var(--panel-2); border: 1px solid var(--line); }
.bk { display: block; font-family: var(--mono); font-size: 9px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--dim); margin-bottom: 4px; }
.cross { font-family: var(--mono); color: var(--spark); }
.mechanism { font-size: 14px; color: var(--muted); margin: 6px 0; }
.action-box {
  margin: 14px 0 0;
  padding: 14px 16px;
  border-left: 3px solid var(--spark);
  background: rgba(255, 180, 84, 0.06);
  border-radius: 0 8px 8px 0;
}
.ab-k { display: block; font-family: var(--mono); font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--spark); margin-bottom: 6px; }
.action-box p { font-size: 15px; margin: 0; line-height: 1.5; }

.timeline { display: flex; flex-direction: column; gap: 10px; }

.tl-row {
  display: grid;
  grid-template-columns: 80px 1fr auto;
  gap: 16px;
  align-items: center;
  padding: 14px 18px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel-2);
  font-size: 14px;
}

.tl-n { font-family: var(--mono); color: var(--beam-a); font-size: 12px; }
.tl-flow { color: var(--muted); }

.feedback {
  margin: 14px 0;
  padding: 18px 22px;
  border-left: 3px solid var(--spark);
  background: var(--panel-2);
  border-radius: 0 8px 8px 0;
  font-size: 16px;
}

details.archive {
  margin-top: 32px;
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 8px 20px 16px;
  background: var(--panel-2);
}

details.archive summary {
  font-family: var(--display);
  font-size: 15px;
  color: var(--muted);
  cursor: pointer;
  padding: 12px 0;
}

.discarded-list {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
}

.discarded-list li {
  padding: 10px 0;
  border-bottom: 1px solid var(--line);
  font-size: 14px;
  color: var(--dim);
}

.footer {
  margin-top: 56px;
  padding-top: 24px;
  border-top: 1px solid var(--line);
  font-family: var(--mono);
  font-size: 11px;
  color: var(--dim);
  letter-spacing: 0.06em;
}

@media print {
  body { background: #fff; color: #111; font-size: 12pt; }
  .wrap { max-width: 100%; padding: 0; }
  .idea { break-inside: avoid; border-color: #ccc; background: #fafafa; }
  .pill, .flag { border: 1px solid #999; }
  details.archive { display: none; }
}

@media (max-width: 640px) {
  .wrap { padding: 32px 18px 60px; }
  .howto { grid-template-columns: 1fr; }
  .tl-row { grid-template-columns: 1fr; gap: 6px; }
}
"""


def _e(value) -> str:
    return html.escape(str(value), quote=True)


def _normalize_flag(flag: str) -> str:
    if flag in ("loved", "love"):
        return "loved"
    if flag in ("liked", "like"):
        return "liked"
    return "trashed"


def _load_json(path: Path, default=None):
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return default if default is not None else []


def _brief_objective(project_path: Path) -> str:
    brief_path = project_path / "brief.yaml"
    if brief_path.is_file():
        brief = yaml.safe_load(brief_path.read_text(encoding="utf-8")) or {}
        return brief.get("objective", "") or project_path.name
    return project_path.name


def _format_body(text: str) -> str:
    parts = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        label, sep, value = line.partition(":")
        if sep and len(label) <= 32:
            parts.append(f"<p><strong>{_e(label)}:</strong> {_e(value.strip())}</p>")
        else:
            parts.append(f"<p>{_e(line)}</p>")
    return "\n".join(parts)


def _parse_source_note(note: str) -> dict:
    m = re.match(r"(?P<strategy>\w+)\s+strategy\s·\s*(?P<text_id>\S+)\s×\s*(?P<set>.+)", note or "")
    if m:
        return m.groupdict()
    return {"strategy": "", "text_id": "", "set": note}


def _load_text_meta(project_path: Path) -> dict[str, dict]:
    texts_dir = project_path / "texts"
    meta = {}
    if not texts_dir.is_dir():
        return meta
    for f in sorted(texts_dir.glob("*.md")):
        content = f.read_text(encoding="utf-8")
        title = content.split("\n")[0].strip("# ").strip()[:80] if content else f.stem
        meta[f.stem] = {"id": f.stem, "title": title, "preview": content[:200].strip()}
        meta[f.stem.upper()] = meta[f.stem]
    return meta


def _domain_for_set(iter_dir: Path, set_id: str) -> dict:
    domains_dir = iter_dir / "domains"
    if not domains_dir.is_dir():
        return {"set_name": set_id, "domain_name": "", "active_principle": ""}
    for yf in domains_dir.glob("*.yaml"):
        bank = yaml.safe_load(yf.read_text(encoding="utf-8")) or {}
        for sid, s in (bank.get("sets") or {}).items():
            if sid == set_id or s.get("name", "") == set_id:
                domains = s.get("domains") or []
                d0 = domains[0] if domains else {}
                return {
                    "set_name": s.get("name", sid),
                    "domain_name": d0.get("name", ""),
                    "active_principle": d0.get("active_principle", ""),
                    "strategy": yf.stem,
                }
    return {"set_name": set_id, "domain_name": "", "active_principle": ""}


def _action_for(flag: str, domain: str) -> str:
    if flag == "loved":
        return (
            f"Action prioritaire : tester une micro-expérience autour de « {domain} » "
            f"cette semaine (interview, prototype, contenu). Puis relancer une itération — "
            f"le moteur approfondira ce domaine."
        )
    if flag == "liked":
        return (
            f"Garder en vue : combiner avec une pépite ♥ ou revisiter après la synthèse. "
            f"Domaine source : {domain}."
        )
    return ""


def _collision_html(idea: dict, iter_dir: Path, text_meta: dict) -> str:
    parsed = _parse_source_note(idea.get("source_note", ""))
    text_id = idea.get("text_id") or parsed.get("text_id", "")
    set_id = idea.get("set_id") or parsed.get("set", "")
    dom = _domain_for_set(iter_dir, set_id) if iter_dir.is_dir() else {}
    tm = text_meta.get(text_id, text_meta.get(text_id.lower(), {}))
    domain = dom.get("domain_name") or dom.get("set_name") or set_id
    strategy = idea.get("strategy") or dom.get("strategy") or parsed.get("strategy", "")
    principle = dom.get("active_principle", "")
    iter_n = idea.get("iteration", "?")
    return f"""
<div class="collision">
  <div class="beams">
    <span class="beam a"><span class="bk">Votre matière</span>{_e(tm.get("title", text_id or "?"))}</span>
    <span class="cross">×</span>
    <span class="beam b"><span class="bk">Champ lointain</span>{_e(domain)}</span>
  </div>
  {f'<p class="mechanism"><strong>Principe actif :</strong> {_e(principle)}</p>' if principle else ""}
  <p class="meta dim">{_e(strategy + " strategy" if strategy else "")} · iter {iter_n}</p>
</div>"""


def _action_html(flag: str, idea: dict, iter_dir: Path | None, text_meta: dict | None) -> str:
    if not iter_dir or text_meta is None:
        return ""
    try:
        import sys
        root = Path(__file__).resolve().parents[2]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from webapp.recommendations import suggest_next_step
        from webapp.session_context import _normalize_flag, _parse_source_note, _domain_for_set

        parsed = _parse_source_note(idea.get("source_note", ""))
        text_id = idea.get("text_id") or parsed.get("text_id", "")
        set_id = idea.get("set_id") or parsed.get("set", "")
        dom = _domain_for_set(iter_dir, set_id)
        tm = text_meta.get(text_id, text_meta.get(text_id.lower(), {}))
        collision = {
            "domain_name": dom.get("domain_name", ""),
            "domain_set": dom.get("set_name", set_id),
            "text_title": tm.get("title", text_id),
        }
        f = _normalize_flag(idea.get("flag", idea.get("_flag", "trashed")))
        text = suggest_next_step(f, {**idea, "collision": collision, "idea_id": idea.get("idea_id", "")})
    except ImportError:
        text = ""
    if not text:
        return ""
    return f'<div class="action-box"><span class="ab-k">Prochaine étape</span><p>{_e(text)}</p></div>'


def _idea_card(idea: dict, *, variant: str, iteration: int | None = None, iter_dir: Path | None = None, text_meta: dict | None = None) -> str:
    flag = _normalize_flag(idea.get("flag", idea.get("_flag", "trashed")))
    score = idea.get("score") or idea.get("score_aggregate") or "—"
    if isinstance(score, (int, float)):
        score = f"{score:.2f}"

    flag_html = ""
    if flag == "loved":
        flag_html = '<span class="flag love">♥ Pépite</span>'
    elif flag == "liked":
        flag_html = '<span class="flag like">↑ À explorer</span>'
    else:
        flag_html = '<span class="flag trash">✕ Écartée</span>'

    iter_n = iteration or idea.get("iteration", "?")
    source = idea.get("source_note") or idea.get("combo") or ""
    why = idea.get("why_selected") or idea.get("why_kept") or idea.get("judge_note") or ""

    collision = ""
    plain = ""
    action = ""
    if iter_dir and text_meta is not None:
        parsed = _parse_source_note(idea.get("source_note", ""))
        text_id = idea.get("text_id") or parsed.get("text_id", "")
        set_id = idea.get("set_id") or parsed.get("set", "")
        dom = _domain_for_set(iter_dir, set_id)
        tm = text_meta.get(text_id, text_meta.get(text_id.lower(), {}))
        collision = _collision_html(idea, iter_dir, text_meta)
        try:
            import sys
            root = Path(__file__).resolve().parents[2]
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            from webapp.clarity_llm import needs_clarity_refresh
            from webapp.idea_clarity import build_clarity
            from webapp.recommendations import suggest_next_step

            text = idea.get("text") or ""
            domain_from_text = ""
            m = re.search(r"Borrowing from ([^,]+),", text, re.I)
            if m:
                domain_from_text = m.group(1).strip()
            inspiration = domain_from_text or dom.get("domain_name") or dom.get("set_name", set_id)

            enriched = {
                **idea,
                "clarity": idea.get("clarity"),
                "collision": {
                    "domain_name": domain_from_text or dom.get("domain_name", ""),
                    "domain_set": dom.get("set_name", set_id),
                    "inspiration": inspiration,
                },
            }
            if needs_clarity_refresh(enriched.get("clarity")):
                enriched["clarity"] = build_clarity(enriched, root, enriched["collision"], mode="demo")
            c = enriched["clarity"]
            actions = "".join(f"<li>{_e(a)}</li>" for a in c.get("actions", []))
            plain = f"""
<div class="idea-clarity">
  <span class="plain-k">En clair</span>
  <p class="clarity-head">{_e(c.get('headline_fr', ''))}</p>
  <p class="clarity-link"><strong>Pour votre sujet :</strong> {_e(c.get('pour_vous', ''))}</p>
  <div class="clarity-actions"><span class="ca-k">À appliquer</span><ol>{actions}</ol></div>
  <p class="clarity-test"><strong>Cette semaine :</strong> {_e(c.get('test', ''))}</p>
</div>"""
            f = _normalize_flag(idea.get("flag", idea.get("_flag", "trashed")))
            action = f'<div class="action-box"><span class="ab-k">Prochaine étape</span><p>{_e(suggest_next_step(f, enriched))}</p></div>'
        except ImportError:
            f = _normalize_flag(idea.get("flag", idea.get("_flag", "trashed")))
            action = _action_html(f, idea, iter_dir, text_meta)

    original = (
        f'<details class="idea-original"><summary>Texte original</summary>'
        f'<div class="idea-original-body">{_format_body(idea.get("text", ""))}</div></details>'
    )

    return f"""
<article class="idea {variant}">
  <header class="idea-head">
    <span class="idea-score">{_e(score)}</span>
    {flag_html}
    <span class="idea-meta">session {iter_n}</span>
  </header>
  {collision}
  {plain}
  {original}
  {f'<p class="idea-note"><strong>Pourquoi retenue :</strong> {_e(why)}</p>' if why else ""}
  {action}
</article>"""


def _howto_block() -> str:
    return """
<section class="howto" aria-label="Comment lire ce rapport">
  <div class="howto-card">
    <div class="howto-n">1</div>
    <h3>Contexte de collision</h3>
    <p>Chaque carte montre <em>votre texte × le domaine distant</em> — la source de l'idée, sans remonter ailleurs.</p>
  </div>
  <div class="howto-card">
    <div class="howto-n">2</div>
    <h3>Actions concrètes</h3>
    <p>L'encadré « Action concrète » propose une piste testable cette semaine, pas un plan abstrait.</p>
  </div>
  <div class="howto-card">
    <div class="howto-n">3</div>
    <h3>Décidez la suite</h3>
    <p>Assez de matière ? Partagez ce fichier. Encore de l'énergie ? Relancez une itération en approfondissant vos ♥.</p>
  </div>
</section>"""


def _html_shell(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_e(title)}</title>
  <style>{_CSS}</style>
</head>
<body>
<div class="wrap">
{body}
<p class="footer">Open Collider · rapport de brainstorm · bisociation at scale</p>
</div>
</body>
</html>"""


def _collect_session(brainstorm_dir: Path, project_path: Path | None = None) -> dict:
    loved, liked, trashed, insights, feedback, timeline = [], [], [], [], [], []
    text_meta = _load_text_meta(project_path) if project_path else {}

    for idir in sorted(brainstorm_dir.iterdir()):
        if not idir.is_dir() or not idir.name.startswith("iter_"):
            continue
        cfg = _load_json(idir / "config.json", {})
        if not cfg:
            continue
        iteration = cfg.get("iteration") or int(idir.name.split("_")[1])

        curated = _load_json(idir / "curated_ideas.json", [])
        flags = _load_json(idir / "flags.json", {})
        raw_insights = _load_json(idir / "insights_without_collision.json", [])

        n_loved = sum(1 for v in flags.values() if _normalize_flag(v) == "loved")
        n_liked = sum(1 for v in flags.values() if _normalize_flag(v) == "liked")

        timeline.append({
            "iteration": iteration,
            "generated": cfg.get("ideas_generated", 0),
            "retained": cfg.get("ideas_retained", 0),
            "curated": len(curated),
            "loved": n_loved,
            "liked": n_liked,
            "trashed": len(flags) - n_loved - n_liked,
        })

        for c in curated:
            idea_id = c.get("idea_id", "")
            flag = _normalize_flag(flags.get(idea_id, "trashed"))
            entry = {**c, "flag": flag, "iteration": iteration, "_iter_dir": idir}
            if flag == "loved":
                loved.append(entry)
            elif flag == "liked":
                liked.append(entry)
            else:
                trashed.append({**entry, "summary": c.get("text", "").split("\n")[0][:160]})

        for c in raw_insights:
            insights.append({**c, "iteration": iteration, "flag": flags.get(c.get("idea_id", ""), "")})

        fb_path = idir / "feedback.txt"
        if fb_path.is_file():
            fb = fb_path.read_text(encoding="utf-8").strip()
            if fb:
                feedback.append({"iteration": iteration, "text": fb})

    loved.sort(key=lambda x: (-float(x.get("score") or 0), x.get("iteration", 0)))
    liked.sort(key=lambda x: (-float(x.get("score") or 0), x.get("iteration", 0)))

    return {
        "loved": loved,
        "liked": liked,
        "trashed": trashed,
        "insights": insights,
        "feedback": feedback,
        "timeline": timeline,
    }


def write_brainstorm_html(project_path: Path, brainstorm_dir: Path, iter_summaries: list[dict]) -> str:
    """Write REPORT.html — synthesis-style, brainstorm-friendly."""
    data = _collect_session(brainstorm_dir, project_path)
    objective = _brief_objective(project_path)
    title = f"Synthèse · {project_path.name}"
    text_meta = _load_text_meta(project_path)

    stats = f"""
<div class="stats">
  <span class="pill loved"><b>{len(data['loved'])}</b> pépites ♥</span>
  <span class="pill liked"><b>{len(data['liked'])}</b> à explorer ↑</span>
  <span class="pill neutral"><b>{len(data['trashed'])}</b> écartées</span>
  <span class="pill neutral">{len(data['timeline'])} itération(s)</span>
</div>"""

    body = f"""
<p class="brand">Open Collider · synthèse d'idéation</p>
<h1>{_e(objective)}</h1>
<p class="dek">Session {_e(brainstorm_dir.name.replace('_', ' '))} · généré le {_e(datetime.now().strftime('%d/%m/%Y à %H:%M'))}</p>
{stats}
{_howto_block()}"""

    if data["loved"]:
        cards = "".join(
            _idea_card(i, variant="loved", iter_dir=i.get("_iter_dir"), text_meta=text_meta)
            for i in data["loved"]
        )
        body += f"""
<section class="section loved">
  <div class="sec-head"><h2>◈ Vos pépites</h2><span class="sec-count">{len(data['loved'])} idée(s)</span></div>
  <p class="sec-lead">Priorité absolue — directions que vous avez validées pour approfondir.</p>
  <div class="ideas">{cards}</div>
</section>"""

    if data["liked"]:
        cards = "".join(
            _idea_card(i, variant="liked", iter_dir=i.get("_iter_dir"), text_meta=text_meta)
            for i in data["liked"]
        )
        body += f"""
<section class="section explore">
  <div class="sec-head"><h2>↑ À approfondir</h2><span class="sec-count">{len(data['liked'])} idée(s)</span></div>
  <p class="sec-lead">Bonnes pistes — signal plus faible, utiles en combinaison.</p>
  <div class="ideas">{cards}</div>
</section>"""

    if data["feedback"]:
        fb_html = "".join(
            f'<blockquote class="feedback"><span class="idea-meta">Iter {f["iteration"]}</span> — {_e(f["text"])}</blockquote>'
            for f in data["feedback"]
        )
        body += f"""
<section class="section">
  <div class="sec-head"><h2>Notes de pilotage</h2></div>
  <p class="sec-lead">Ce que vous avez demandé au moteur entre les itérations.</p>
  {fb_html}
</section>"""

    if data["timeline"]:
        rows = "".join(
            f'<div class="tl-row"><span class="tl-n">Iter {t["iteration"]:02d}</span>'
            f'<span class="tl-flow">{t["generated"]} générées → {t["retained"]} retenues → {t["curated"]} curatées</span>'
            f'<span class="idea-meta"><b style="color:var(--love)">{t["loved"]}</b> ♥ · <b style="color:var(--like)">{t["liked"]}</b> ↑</span></div>'
            for t in data["timeline"]
        )
        body += f"""
<section class="section">
  <div class="sec-head"><h2>Parcours de la session</h2></div>
  <p class="sec-lead">La plupart des idées brutes sont filtrées avant d'arriver jusqu'à vous.</p>
  <div class="timeline">{rows}</div>
</section>"""

    if data["insights"]:
        items = "".join(
            f'<li><span class="idea-meta">[{_e(i.get("score", "—"))}] iter {i["iteration"]}</span> '
            f'{_e(i.get("text", "").split(chr(10))[0][:140])}</li>'
            for i in data["insights"]
        )
        body += f"""
<details class="archive">
  <summary>Insights sans collision ({len(data['insights'])})</summary>
  <ul class="discarded-list">{items}</ul>
</details>"""

    if data["trashed"]:
        items = "".join(
            f'<li><span class="idea-meta">[{_e(t.get("score", "—"))}] iter {t["iteration"]}</span> '
            f'{_e(t.get("summary", ""))}</li>'
            for t in data["trashed"]
        )
        body += f"""
<details class="archive">
  <summary>Réserve — idées écartées ({len(data['trashed'])})</summary>
  <ul class="discarded-list">{items}</ul>
</details>"""

    html_out = _html_shell(title, body)
    (brainstorm_dir / "REPORT.html").write_text(html_out, encoding="utf-8")
    return html_out


def write_iteration_html(project_path: Path, brainstorm_dir: Path, iteration: int) -> str:
    """Write ITER_REPORT.html for a single iteration — verdict-focused."""
    iter_dir = brainstorm_dir / f"iter_{iteration:03d}"
    cfg = _load_json(iter_dir / "config.json", {})
    curated = _load_json(iter_dir / "curated_ideas.json", [])
    flags = _load_json(iter_dir / "flags.json", {})
    insights = _load_json(iter_dir / "insights_without_collision.json", [])

    objective = _brief_objective(project_path)
    title = f"Iteration {iteration} · {project_path.name}"

    n_loved = sum(1 for v in flags.values() if _normalize_flag(v) == "loved")
    n_liked = sum(1 for v in flags.values() if _normalize_flag(v) == "liked")

    body = f"""
<p class="brand">Open Collider · verdict iteration {iteration}</p>
<h1>Votre verdict — itération {iteration}</h1>
<p class="dek">{_e(objective)}</p>
<div class="stats">
  <span class="pill loved"><b>{n_loved}</b> ♥ love</span>
  <span class="pill liked"><b>{n_liked}</b> ↑ like</span>
  <span class="pill neutral">{len(curated)} curatées</span>
</div>
<section class="howto" aria-label="Rappel des flags">
  <div class="howto-card">
    <div class="howto-n">♥</div>
    <h3>Love</h3>
    <p>Creuser ce domaine à la prochaine itération.</p>
  </div>
  <div class="howto-card">
    <div class="howto-n">↑</div>
    <h3>Like</h3>
    <p>Signal positif faible — garder en réserve.</p>
  </div>
  <div class="howto-card">
    <div class="howto-n">✕</div>
    <h3>Trash</h3>
    <p>Écarter. Non flaggé = trash dans la synthèse.</p>
  </div>
</section>"""

    if curated:
        cards = []
        for c in curated:
            idea_id = c.get("idea_id", "")
            flag = _normalize_flag(flags.get(idea_id, "trashed"))
            variant = "loved" if flag == "loved" else "liked" if flag == "liked" else "trashed"
            cards.append(_idea_card({**c, "flag": flag, "iteration": iteration}, variant=variant))
        body += f"""
<section class="section loved">
  <div class="sec-head"><h2>Idées curatées</h2><span class="sec-count">{len(curated)}</span></div>
  <p class="sec-lead">Les ~12 meilleures idées de cette itération — jugez-les ci-dessous dans l'app.</p>
  <div class="ideas">{"".join(cards)}</div>
</section>"""

    if insights:
        items = "".join(
            f'<li>{_e(i.get("text", "").split(chr(10))[0][:160])}</li>' for i in insights
        )
        body += f"""
<details class="archive">
  <summary>Insights sans collision ({len(insights)})</summary>
  <ul class="discarded-list">{items}</ul>
</details>"""

    html_out = _html_shell(title, body)
    (iter_dir / "ITER_REPORT.html").write_text(html_out, encoding="utf-8")
    return html_out
