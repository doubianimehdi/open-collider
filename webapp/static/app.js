/* Open Collider UI — single-file SPA, no build step. */

const app = document.getElementById("app");
let LIVE_AVAILABLE = false;

/* ================================================================
   Utilities
================================================================ */

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let msg = `${res.status}`;
    try { msg = (await res.json()).detail || msg; } catch (_) {}
    throw new Error(msg);
  }
  return res.json();
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

/* minimal inline markdown: **bold**, *italic* */
function mdInline(s) {
  return esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>");
}

let toastTimer = null;
function toast(msg, isError = false) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = "toast" + (isError ? " error" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 4200);
}

/* full markdown renderer for reports and manual */
function renderMarkdown(md) {
  const lines = md.split("\n");
  let html = "", inList = false, tableBuf = [];
  let inCode = false, codeBuf = [];

  const flushTable = () => {
    if (!tableBuf.length) return;
    const rows = tableBuf.filter(r => !/^\s*\|[\s\-|:]+\|\s*$/.test(r));
    html += "<table>";
    rows.forEach((row, i) => {
      const cells = row.split("|").slice(1, -1).map(c => mdInline(c.trim()));
      const tag = i === 0 ? "th" : "td";
      html += "<tr>" + cells.map(c => `<${tag}>${c}</${tag}>`).join("") + "</tr>";
    });
    html += "</table>";
    tableBuf = [];
  };
  const closeList = () => { if (inList) { html += "</ul>"; inList = false; } };
  const closeCode = () => {
    if (!inCode) return;
    html += `<pre class="md-pre"><code>${esc(codeBuf.join("\n"))}</code></pre>`;
    inCode = false;
    codeBuf = [];
  };

  for (const line of lines) {
    if (/^```/.test(line)) {
      flushTable(); closeList();
      if (inCode) closeCode();
      else { inCode = true; codeBuf = []; }
      continue;
    }
    if (inCode) { codeBuf.push(line); continue; }
    if (/^\s*\|.*\|\s*$/.test(line)) { closeList(); tableBuf.push(line); continue; }
    flushTable();
    if (/^---+\s*$/.test(line)) { closeList(); html += "<hr>"; continue; }
    let m;
    if ((m = line.match(/^(#{1,4})\s+(.*)/))) {
      closeList();
      const lvl = Math.min(m[1].length, 4);
      html += `<h${lvl}>${mdInline(m[2])}</h${lvl}>`;
      continue;
    }
    if ((m = line.match(/^\s*[-*]\s+(.*)/))) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${mdInline(m[1])}</li>`;
      continue;
    }
    closeList();
    if (line.trim() === "") continue;
    html += `<p>${mdInline(line)}</p>`;
  }
  flushTable(); closeList(); closeCode();
  return html;
}

/* ================================================================
   Router
================================================================ */

const routes = [
  { re: /^#?\/?$/, view: viewHome },
  { re: /^#\/guide$/, view: viewGuide },
  { re: /^#\/manuel$/, view: viewManuel },
  { re: /^#\/settings$/, view: viewSettings },
  { re: /^#\/new$/, view: viewNewProject },
  { re: /^#\/p\/([^/]+)$/, view: viewProject },
  { re: /^#\/p\/([^/]+)\/run\/([^/]+)$/, view: viewRun },
  { re: /^#\/p\/([^/]+)\/b\/([^/]+)\/i\/(\d+)$/, view: viewIteration },
  { re: /^#\/p\/([^/]+)\/b\/([^/]+)\/synthesis$/, view: viewSynthesis },
  { re: /^#\/p\/([^/]+)\/b\/([^/]+)\/report$/, view: viewReport },
];

let activePoller = null;

async function route() {
  if (activePoller) { clearTimeout(activePoller); activePoller = null; }
  const hash = location.hash || "#/";
  for (const r of routes) {
    const m = hash.match(r.re);
    if (m) {
      try { await r.view(...m.slice(1).map(decodeURIComponent)); }
      catch (e) {
        app.innerHTML = `<section class="view"><div class="crumb"><a href="#/">← home</a></div>
          <div class="empty">Something went wrong: ${esc(e.message)}</div></section>`;
      }
      window.scrollTo(0, 0);
      return;
    }
  }
  location.hash = "#/";
}

window.addEventListener("hashchange", route);

/* ================================================================
   VIEW: Home
================================================================ */

async function viewHome() {
  const projects = await api("/api/projects");

  const cards = projects.map(p => `
    <div class="card" onclick="location.hash='#/p/${encodeURIComponent(p.name)}'">
      <h3>${esc(p.name)}</h3>
      <div class="obj">${esc(p.objective) || "<span class='dim'>no objective set</span>"}</div>
      <div class="meta">
        <span><b>${p.n_texts}</b> texts</span>
        <span><b>${p.n_brainstorms}</b> sessions</span>
        <span><b>${p.total_ideas}</b> ideas collided</span>
        ${p.total_loved ? `<span style="color:var(--love)"><b>${p.total_loved}</b> loved</span>` : ""}
      </div>
    </div>`).join("");

  app.innerHTML = `
  <section class="view">
    <div class="hero">
      <div>
        <div class="kicker">An idea machine that avoids the obvious</div>
        <h1>Get the ideas<br>AI <span class="accent-b">never</span><br>gives <span class="accent-a">anyone</span>.</h1>
        <p class="lede">Ask any AI to brainstorm and you get the same safe suggestions everyone
        else gets. Open Collider fixes that: it makes the AI <strong>study an unrelated field
        first</strong> — glass physics, fermentation, ant colonies — then forces a collision with
        your problem. What comes out is genuinely unexpected, and still useful.</p>
        <div class="hero-actions">
          <a class="btn btn-primary" href="#/new">+ New project</a>
          <a class="btn btn-ghost" href="#/guide">How to use it</a>
        </div>
      </div>
      <div class="rig" aria-hidden="true">
        <div class="ring"></div><div class="ring r2"></div><div class="ring r3"></div>
        <div class="orbit a"><div class="p"></div></div>
        <div class="orbit b"><div class="p"></div></div>
        <div class="core"></div>
        <div class="spark-label mono">your problem × a distant field → ideas nobody else has</div>
      </div>
    </div>

    <div class="explainer">
      <div class="ex-cell">
        <h3>What is this, really?</h3>
        <p>AI models are trained to give the <strong>most likely</strong> answer — which for
        brainstorming means the most average one. Ask twice, and 80% of the ideas overlap.
        More instructions ("be original!") don't help; the AI just digs deeper into the same hole.</p>
        <div class="analogy">It's like asking a chef to invent a new dish: you'll get variations
        of what they already cook. But make them study how glassblowers handle heat first, and
        suddenly the dishes get interesting.</div>
      </div>
      <div class="ex-cell">
        <h3>How the trick works</h3>
        <p><strong>1.</strong> You describe your problem and paste in your raw material (notes, memos, drafts).</p>
        <p><strong>2.</strong> The machine picks fields that have <strong>nothing to do</strong> with your problem
        and extracts one surprising mechanism from each.</p>
        <p><strong>3.</strong> It forces the AI to reason through that mechanism <strong>before</strong> generating —
        hundreds of times in parallel — then scores everything and shows you only the best ~12.</p>
        <p>You judge those, and your taste steers the next round. Backed by a 12-project benchmark —
        <a href="https://cdriclion.substack.com/p/why-direct-prompting-pushes-llms" target="_blank" rel="noopener" style="color:var(--beam-a)">read the research ↗</a></p>
      </div>
    </div>

    <div class="usecases">
      <div class="usecase good">
        <h4>✓ Use it when…</h4>
        <ul>
          <li>You need <b>product, feature, or business ideas</b> beyond the obvious</li>
          <li>You want <b>marketing angles or content ideas</b> that don't sound like everyone's</li>
          <li>You're exploring <b>strategy options or research directions</b></li>
          <li>Brainstorming feels stuck — every session lands on the same 5 ideas</li>
        </ul>
      </div>
      <div class="usecase bad">
        <h4>✗ Skip it when…</h4>
        <ul>
          <li>You need a <b>factual answer</b> — this generates options, not facts</li>
          <li>The task has <b>one correct solution</b> (a bug fix, a calculation)</li>
          <li>You can't judge the results yourself — your taste is half the engine</li>
          <li>You need one quick idea right now — a session surfaces ~12 per round</li>
        </ul>
      </div>
    </div>

    <div class="guide-hint">
      <span class="hn-icon" style="color:var(--beam-a)">◍</span>
      <span class="gh-text"><strong>New here?</strong> The 3-minute guide walks you through your first
      session — and demo mode lets you try the whole flow for free, no API key needed.</span>
      <a class="btn btn-small btn-ghost" href="#/guide">Open the guide</a>
    </div>

    <div class="sec-head">
      <h2>Projects</h2>
      <span class="mono">${projects.length} project${projects.length === 1 ? "" : "s"}</span>
    </div>
    ${projects.length
      ? `<div class="cards">${cards}</div>`
      : `<div class="empty">No projects yet. Create one to start colliding ideas —
         it takes two minutes and works in demo mode without an API key.</div>`}
  </section>`;
}

/* ================================================================
   VIEW: Guide
================================================================ */

async function viewGuide() {
  app.innerHTML = `
  <section class="view guide">
    <div class="crumb"><a href="#/">← home</a> / guide</div>
    <h1 class="page-title">How to use Open Collider</h1>
    <p class="page-sub">Three minutes, no jargon. What it's for, how a session works, and how to read the results.</p>

    <h2>When should I use it?</h2>
    <p>Use it whenever you need <strong>many candidate ideas for an open-ended problem</strong> and
    the usual AI brainstorm keeps giving you safe, samey answers. Typical wins: product and feature
    concepts, campaign and content angles, naming directions, research questions, strategic options.</p>
    <p>Don't use it for questions with a single right answer, for facts, or when you won't be able
    to tell a good idea from a bad one — <strong>your judgment is half of the machine</strong>.
    The engine produces volume; you provide taste.</p>

    <h2>What do I need?</h2>
    <p><strong>Nothing, to try it.</strong> Demo mode simulates the whole pipeline with clearly
    labeled placeholder ideas, so you can learn the workflow for free.</p>
    <p><strong>For real ideas</strong>, connect an AI provider in <a href="#/settings" style="color:var(--beam-a)">Settings</a> —
    an Anthropic API key, or any OpenAI-compatible service (OpenAI, OpenRouter, Groq, a local Ollama…).
    A real round takes roughly 5–15 minutes and costs a few dollars, depending on your provider and models.</p>

    <h2>A session, step by step</h2>
    <div class="gstep"><span class="gs-n">01</span><div>
      <h5>Create a project</h5>
      <p>Describe what you need ideas for, and paste in <strong>raw material</strong>: memos, notes,
      drafts, anything that captures your problem and your voice. The richer the material, the
      better the collisions. List "forbidden topics" — themes the machine must not just recycle.</p>
    </div></div>
    <div class="gstep"><span class="gs-n">02</span><div>
      <h5>Start a session and run an iteration</h5>
      <p>Hit <strong>Start new session</strong>. The machine invents distant fields (each with one
      counter-intuitive mechanism), collides every text × field pair, generates hundreds of raw
      ideas, and scores them all. You watch it happen live.</p>
    </div></div>
    <div class="gstep"><span class="gs-n">03</span><div>
      <h5>Judge the curated ideas</h5>
      <p>You get the top ~12 ideas as cards. Flag each one: <strong style="color:var(--love)">♥ love</strong>
      (dig deeper here), <strong style="color:var(--like)">↑ like</strong> (decent), or
      <strong>✕ trash</strong>. Add an optional steering note ("more ideas about timing").</p>
    </div></div>
    <div class="gstep"><span class="gs-n">04</span><div>
      <h5>Run the next iteration</h5>
      <p>Your flags change what happens next: loved ideas make the machine <strong>deepen</strong> the
      fields that produced them and <strong>transfer</strong> the mechanisms that worked, while still
      exploring fresh territory. Most sessions are exhausted after 3–5 rounds.</p>
    </div></div>
    <div class="gstep"><span class="gs-n">05</span><div>
      <h5>Session synthesis (Bilan)</h5>
      <p>Click <strong>◈ Bilan</strong> for a structured read: favorites ♥ first, ideas to
      explore, steering notes, session timeline. Validate when you're done — the compass shows
      « Bilan validé ». Full French walkthrough: <a href="#/manuel" style="color:var(--beam-a)">manuel</a>.</p>
    </div></div>

    <h2>How to read En clair</h2>
    <p>Every idea card includes a French block <strong>En clair</strong> — read it <em>before</em> the
    English original. It is generated <strong>at idea creation</strong> (LLM in live mode, simulated
    templates in demo). Older iterations refresh automatically on first load if clarity was outdated.</p>
    <table class="axis-table">
      <tr><td>Headline</td><td>One sentence: what to test for <strong>your</strong> brief</td></tr>
      <tr><td>Pour votre sujet</td><td>Borrowed mechanism in plain French, tied to your product or challenge</td></tr>
      <tr><td>À appliquer</td><td>Three concrete actions on the product — not meta-instructions</td></tr>
      <tr><td>Cette semaine</td><td>One 30-minute test with a real person</td></tr>
      <tr><td>Prochaine étape</td><td>Follow-up after the test (e.g. note a simpler variant) — not a copy of the test</td></tr>
    </table>
    <p>The collision line (<em>De T01 + inspired by …</em>) uses the domain named <strong>in the idea text</strong>,
    not just the generic domain-set label.</p>

    <h2>How to read an idea card</h2>
    <p>Every idea carries a <strong>score out of 5</strong>, computed by an AI judge across five questions:</p>
    <table class="axis-table">
      <tr><td>originality</td><td>Is the underlying idea genuinely new, or repackaged standard advice?</td></tr>
      <tr><td>resistance</td><td>Does it survive pushback, or does one objection collapse it?</td></tr>
      <tr><td>thesis</td><td>Can it be stated as one clear, testable claim?</td></tr>
      <tr><td>grounding</td><td>Could real facts or examples back it up?</td></tr>
      <tr><td>cognitive load</td><td>Does it make you stop and think, or is it instantly forgettable?</td></tr>
    </table>
    <p>The small source line (e.g. <em>"fresh strategy · T01 × Glass physics"</em>) tells you which of
    your texts collided with which distant field to produce the idea. Expect noise — most raw ideas
    are discarded before you see anything. That's the design: <strong>volume first, then ruthless filtering</strong>.</p>

    <div class="hero-actions" style="margin-top:44px">
      <a class="btn btn-primary" href="#/new">+ Create your first project</a>
      <a class="btn btn-ghost" href="#/settings">⚙ Connect a provider</a>
    </div>
  </section>`;
}

/* ================================================================
   VIEW: Manuel (FR)
================================================================ */

async function viewManuel() {
  const res = await fetch("/static/manuel.md");
  if (!res.ok) throw new Error("Manuel introuvable — vérifiez que le serveur est à jour");
  const markdown = await res.text();
  app.innerHTML = `
  <section class="view guide">
    <div class="crumb"><a href="#/">← accueil</a> / manuel</div>
    <div class="report-body manual-body">${renderMarkdown(markdown)}</div>
    <div class="hero-actions" style="margin-top:36px">
      <a class="btn btn-primary" href="#/new">+ Créer un projet</a>
      <a class="btn btn-ghost" href="#/guide">Guide (EN)</a>
      <a class="btn btn-ghost" href="#/settings">⚙ Réglages</a>
    </div>
  </section>`;
}

/* ================================================================
   VIEW: Settings
================================================================ */

let setProvider = "demo";

window.pickProvider = (p) => {
  setProvider = p;
  document.querySelectorAll(".provider-card").forEach(el =>
    el.classList.toggle("selected", el.dataset.p === p));
  document.getElementById("anthropic-fields").classList.toggle("hidden", p !== "anthropic");
  document.getElementById("openai-fields").classList.toggle("hidden", p !== "openai");
  document.getElementById("models-panel").classList.toggle("hidden", p === "demo");
};

async function viewSettings() {
  const s = await api("/api/settings");
  setProvider = s.provider;
  const mdl = (k) => esc(s.models[k] || "");
  const ph = (prov, k) => esc(s.default_models[prov][k]);
  const pipe = (k) => s.pipeline[k] ?? "";

  app.innerHTML = `
  <section class="view settings">
    <div class="crumb"><a href="#/">← home</a> / settings</div>
    <h1 class="page-title">Settings</h1>
    <p class="page-sub">Connect an AI provider to generate real ideas. Everything is stored locally
    on your machine — keys never leave it except to call the provider you choose.</p>

    <div class="fgroup">
      <label>AI provider</label>
      <div class="provider-cards">
        <div class="provider-card ${s.provider === "demo" ? "selected" : ""}" data-p="demo" onclick="pickProvider('demo')">
          <h4>Demo only</h4>
          <p>No key, no cost. Simulates the pipeline with placeholder ideas so you can learn the workflow.</p>
        </div>
        <div class="provider-card ${s.provider === "anthropic" ? "selected" : ""}" data-p="anthropic" onclick="pickProvider('anthropic')">
          <h4>Anthropic</h4>
          <p>Claude models — what Open Collider was designed and benchmarked on. Recommended.</p>
        </div>
        <div class="provider-card ${s.provider === "openai" ? "selected" : ""}" data-p="openai" onclick="pickProvider('openai')">
          <h4>OpenAI-compatible</h4>
          <p>OpenAI, OpenRouter, Groq, Mistral, local Ollama / LM Studio — anything with a /chat/completions API.</p>
        </div>
      </div>
    </div>

    <div id="anthropic-fields" class="${s.provider === "anthropic" ? "" : "hidden"}">
      <div class="fgroup">
        <label>Anthropic API key</label>
        <div class="key-row">
          <input type="password" id="f-anthropic-key" placeholder="${s.anthropic_key_set ? "•••• key saved — type to replace" : "sk-ant-…"}">
        </div>
        ${s.anthropic_key_set ? `<div class="key-set-note">✓ key saved (${esc(s.anthropic_key_masked)}) — leave blank to keep it</div>` : ""}
        <div class="hint">Get one at console.anthropic.com → API keys. Also saved to the repo's .env so the Claude Code workflow uses it too.</div>
      </div>
    </div>

    <div id="openai-fields" class="${s.provider === "openai" ? "" : "hidden"}">
      <div class="fgroup">
        <label>Base URL</label>
        <input type="text" id="f-openai-url" value="${esc(s.openai_base_url)}" placeholder="https://api.openai.com/v1">
        <div class="hint">Examples — OpenAI: https://api.openai.com/v1 · OpenRouter: https://openrouter.ai/api/v1 · Groq: https://api.groq.com/openai/v1 · local Ollama: http://localhost:11434/v1</div>
      </div>
      <div class="fgroup">
        <label>API key</label>
        <div class="key-row">
          <input type="password" id="f-openai-key" placeholder="${s.openai_key_set ? "•••• key saved — type to replace" : "sk-… (leave empty for local servers like Ollama)"}">
        </div>
        ${s.openai_key_set ? `<div class="key-set-note">✓ key saved (${esc(s.openai_key_masked)}) — leave blank to keep it</div>` : ""}
      </div>
    </div>

    <div id="models-panel" class="panel ${s.provider === "demo" ? "hidden" : ""}" style="margin-top:8px">
      <h3>Models <span class="dim" style="text-transform:none;letter-spacing:0">— leave blank for sensible defaults</span></h3>
      <div class="grid-3">
        <div class="fgroup" style="margin-bottom:0">
          <label data-tip="Invents the distant fields. Use your most creative model.">Domain model</label>
          <input type="text" id="f-m-domain" value="${mdl("domain_model")}" placeholder="${ph(s.provider === "openai" ? "openai" : "anthropic", "domain_model")}">
        </div>
        <div class="fgroup" style="margin-bottom:0">
          <label data-tip="Mass-generates ideas in parallel. A fast, cheaper model works well.">Generation model</label>
          <input type="text" id="f-m-gen" value="${mdl("generation_model")}" placeholder="${ph(s.provider === "openai" ? "openai" : "anthropic", "generation_model")}">
        </div>
        <div class="fgroup" style="margin-bottom:0">
          <label data-tip="Scores every idea on the 5 axes. Needs to follow a strict table format.">Scoring model</label>
          <input type="text" id="f-m-score" value="${mdl("scoring_model")}" placeholder="${ph(s.provider === "openai" ? "openai" : "anthropic", "scoring_model")}">
        </div>
      </div>
    </div>

    <details class="adv-details">
      <summary>▸ Advanced pipeline tuning</summary>
      <div class="panel" style="margin-top:6px">
        <div class="grid-2">
          <div class="fgroup" style="margin-bottom:0">
            <label data-tip="Ideas scoring below this are discarded before curation. Default 4.2 of 5.">Score threshold</label>
            <input type="text" id="f-p-threshold" value="${pipe("score_threshold")}" placeholder="4.2 (default)">
          </div>
          <div class="fgroup" style="margin-bottom:0">
            <label data-tip="How many text × field collisions in the very first round. More = more ideas, more cost. Default 24.">Collisions, first round</label>
            <input type="text" id="f-p-first" value="${pipe("combos_first_iteration")}" placeholder="24 (default)">
          </div>
          <div class="fgroup" style="margin-bottom:0">
            <label data-tip="Collisions per strategy in later rounds (3 strategies run in parallel). Default 12 each.">Collisions per strategy</label>
            <input type="text" id="f-p-per" value="${pipe("combos_per_strategy")}" placeholder="12 (default)">
          </div>
          <div class="fgroup" style="margin-bottom:0">
            <label data-tip="Parallel API calls during generation. Lower this if you hit rate limits.">Max parallel calls</label>
            <input type="text" id="f-p-conc" value="${pipe("max_concurrent")}" placeholder="4 (default)">
          </div>
        </div>
      </div>
    </details>

    <div id="test-result"></div>

    <div class="form-actions">
      <button class="btn-primary" id="f-save" onclick="saveSettings()">Save settings</button>
      <button class="btn-ghost" id="f-test" onclick="testSettings()">Test connection</button>
      <span class="mono dim" id="settings-note"></span>
    </div>
  </section>`;
}

window.saveSettings = async (silent = false) => {
  const btn = document.getElementById("f-save");
  btn.disabled = true;
  const keyVal = (id) => {
    const v = document.getElementById(id).value.trim();
    return v === "" ? "__KEEP__" : v;
  };
  const body = {
    provider: setProvider,
    anthropic_api_key: keyVal("f-anthropic-key"),
    openai_api_key: keyVal("f-openai-key"),
    openai_base_url: document.getElementById("f-openai-url").value.trim(),
    models: {
      domain_model: document.getElementById("f-m-domain").value.trim(),
      generation_model: document.getElementById("f-m-gen").value.trim(),
      scoring_model: document.getElementById("f-m-score").value.trim(),
    },
    pipeline: {
      score_threshold: document.getElementById("f-p-threshold").value.trim(),
      combos_first_iteration: document.getElementById("f-p-first").value.trim(),
      combos_per_strategy: document.getElementById("f-p-per").value.trim(),
      max_concurrent: document.getElementById("f-p-conc").value.trim(),
    },
  };
  try {
    const res = await api("/api/settings", { method: "POST", body: JSON.stringify(body) });
    LIVE_AVAILABLE = res.live_available;
    runMode = null; // re-derive on next project view
    updatePill(res.provider, res.live_available);
    if (!silent) {
      toast("Settings saved");
      viewSettings();
    }
    return true;
  } catch (e) {
    toast(e.message, true);
    return false;
  } finally {
    btn.disabled = false;
  }
};

window.testSettings = async () => {
  const btn = document.getElementById("f-test");
  const box = document.getElementById("test-result");
  // Save first so the test uses what's on screen
  if (!(await saveSettings(true))) return;
  btn.disabled = true;
  box.innerHTML = `<div class="test-result"><span class="spinner"></span>Testing connection…</div>`;
  try {
    const res = await api("/api/settings/test", { method: "POST" });
    box.innerHTML = `<div class="test-result ${res.ok ? "ok" : "fail"}">${res.ok ? "✓" : "✕"} ${esc(res.message)}</div>`;
  } catch (e) {
    box.innerHTML = `<div class="test-result fail">✕ ${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false;
  }
};

/* ================================================================
   VIEW: New project wizard
================================================================ */

let wizardTexts = [];

function textBlockHtml(i) {
  const t = wizardTexts[i];
  return `
  <div class="text-block" data-i="${i}">
    <div class="tb-head">
      <span class="tb-id">T${String(i + 1).padStart(2, "0")}</span>
      <input type="text" placeholder="Title — e.g. 'Product strategy memo'" value="${esc(t.title)}"
        oninput="wizardTexts[${i}].title = this.value" style="flex:1">
      <button class="tb-remove" onclick="removeText(${i})">remove ✕</button>
    </div>
    <textarea rows="5" placeholder="Paste the raw reference text here — an essay, a memo, research notes, samples of your voice…"
      oninput="wizardTexts[${i}].content = this.value">${esc(t.content)}</textarea>
    <div style="margin-top:10px">
      <input type="text" placeholder="Forbidden topics for this text (comma-separated) — themes the collider must NOT recycle"
        value="${esc(t.forbidden.join(", "))}"
        oninput="wizardTexts[${i}].forbidden = this.value.split(',').map(s=>s.trim()).filter(Boolean)">
    </div>
  </div>`;
}

window.removeText = (i) => {
  wizardTexts.splice(i, 1);
  document.getElementById("texts-list").innerHTML = wizardTexts.map((_, j) => textBlockHtml(j)).join("");
};

window.addText = () => {
  wizardTexts.push({ title: "", content: "", forbidden: [] });
  document.getElementById("texts-list").innerHTML = wizardTexts.map((_, j) => textBlockHtml(j)).join("");
};

async function viewNewProject() {
  wizardTexts = [{ title: "", content: "", forbidden: [] }];
  app.innerHTML = `
  <section class="view wizard">
    <div class="crumb"><a href="#/">← home</a></div>
    <h1 class="page-title">New project</h1>
    <p class="page-sub">Tell the machine what you need ideas for, then feed it raw material.
    The richer the material, the better the collisions. Two minutes, tops.</p>

    <div class="fgroup">
      <label>Project name <span class="req">*</span></label>
      <input type="text" id="f-name" placeholder="e.g. discover_weekly_redesign">
    </div>
    <div class="fgroup">
      <label>What do you need ideas for? <span class="req">*</span></label>
      <textarea id="f-objective" rows="3" placeholder="One or two sentences. e.g. Redesigns of Spotify's Discover Weekly that break users out of their taste bubble."></textarea>
      <div class="hint">Be specific about the problem, not the solution — the machine supplies the unexpected part.</div>
    </div>
    <div class="fgroup">
      <label>Context — where will the ideas be used?</label>
      <textarea id="f-context" rows="2" placeholder="e.g. Feeding a product strategy offsite for the personalization team."></textarea>
    </div>
    <div class="fgroup">
      <label>Hard constraints</label>
      <textarea id="f-constraints" rows="2" placeholder="Non-negotiable limits. e.g. Must work within existing licensing deals."></textarea>
    </div>
    <div class="fgroup">
      <label>What does a good idea look like to you?</label>
      <textarea id="f-good" rows="2" placeholder="e.g. Concrete mechanisms we could prototype, not vague directions."></textarea>
      <div class="hint">This calibrates the judge that scores every idea before you see it.</div>
    </div>
    <div class="fgroup">
      <label>Off-limits topics</label>
      <input type="text" id="f-forbidden" placeholder="Comma-separated themes the machine must avoid entirely, e.g. gamification, NFTs">
    </div>

    <div class="sec-head" style="margin-top:44px">
      <h2>Your raw material <span class="req" style="color:var(--spark)">*</span></h2>
      <button class="btn-small btn-ghost" onclick="addText()">+ add text</button>
    </div>
    <p class="page-sub" style="margin-bottom:18px">Paste memos, notes, drafts, research — anything that captures
    your problem and your voice. This is what gets collided against the distant fields. At least one text is required.</p>
    <div id="texts-list">${textBlockHtml(0)}</div>

    <div class="form-actions">
      <button class="btn-primary" id="f-submit" onclick="submitProject()">Create project</button>
      <a class="btn btn-ghost" href="#/">Cancel</a>
    </div>
  </section>`;
}

window.submitProject = async () => {
  const btn = document.getElementById("f-submit");
  const body = {
    name: document.getElementById("f-name").value.trim(),
    objective: document.getElementById("f-objective").value.trim(),
    context: document.getElementById("f-context").value.trim(),
    constraints: document.getElementById("f-constraints").value.trim(),
    what_makes_good_ideas: document.getElementById("f-good").value.trim(),
    forbidden_topics: document.getElementById("f-forbidden").value.split(",").map(s => s.trim()).filter(Boolean),
    texts: wizardTexts.map(t => ({ title: t.title, content: t.content, forbidden_topics: t.forbidden })),
  };
  if (!body.name) return toast("Project name is required", true);
  if (!body.objective) return toast("Objective is required", true);
  if (!body.texts.some(t => t.content.trim())) return toast("At least one reference text is required", true);
  btn.disabled = true;
  try {
    const res = await api("/api/projects", { method: "POST", body: JSON.stringify(body) });
    toast(`Project '${res.name}' created`);
    location.hash = `#/p/${encodeURIComponent(res.name)}`;
  } catch (e) {
    toast(e.message, true);
    btn.disabled = false;
  }
};

/* ================================================================
   VIEW: Project dashboard
================================================================ */

let runMode = null;

function journeyStep(session) {
  if (!session || !session.iterations_detail?.length) return 2;
  if (session.synthesis_done) return 5;
  const last = session.iterations_detail[session.iterations_detail.length - 1];
  if (!last.flagged) return 3;
  if (session.has_report) return 5;
  return 4;
}

function renderSessionCompass(nav) {
  if (!nav) return "";
  const complete = nav.synthesis_complete;
  const cur = complete ? 99 : (nav.current_step || 1);
  const steps = nav.steps || [];
  return `
  <nav class="session-compass ${complete ? "complete" : ""}" aria-label="Où vous en êtes">
    ${complete ? `<div class="sc-done-banner">✓ Bilan validé${nav.validation?.validated_at ? ` · ${esc(nav.validation.validated_at)}` : ""}</div>` : ""}
    <div class="sc-path">
      ${steps.map((s, i) => `
        <span class="sc-node ${complete || s.n < cur ? "done" : ""} ${!complete && s.n === cur ? "here" : ""}" title="${esc(s.hint)}">
          <span class="sc-num">${complete || s.n < cur ? "✓" : s.n}</span>
          <span class="sc-lbl">${esc(s.label)}</span>
        </span>${i < steps.length - 1 ? '<span class="sc-arrow">→</span>' : ""}`).join("")}
    </div>
    <div class="sc-body">
      <p class="sc-objective">${esc(nav.objective || nav.project || "")}</p>
      ${nav.came_from && !complete ? `<p class="sc-from"><span class="dim">Étape d'avant :</span> <strong>${esc(nav.came_from)}</strong></p>` : ""}
      <p class="sc-now"><span class="dim">${complete ? "Terminé —" : "Maintenant —"}</span> <strong>${esc(nav.now_label || "")}</strong> : ${esc(nav.now_action || nav.now_hint || "")}</p>
      ${nav.next_step && !complete ? `<p class="sc-next"><span class="dim">Ensuite :</span> <strong>${esc(nav.next_step)}</strong></p>` : ""}
      ${complete && nav.validation?.note ? `<p class="sc-note"><span class="dim">Votre prochaine étape :</span> ${esc(nav.validation.note)}</p>` : ""}
    </div>
  </nav>`;
}

function renderCollisionBlock(idea) {
  const c = idea.collision || {};
  const inspiration = c.inspiration || c.domain_name || c.domain_set || "?";
  const textTitle = c.text_title || c.text_id || "votre texte";
  if (!c.text_id && !c.source_note && !idea.source_note) {
    return idea.source_note ? `<p class="collision-strategy dim">${esc(idea.source_note)}</p>` : "";
  }
  return `
  <div class="collision-context">
    <p class="collision-simple">
      <span class="cs-k">De</span> ${esc(textTitle)}
      <span class="cs-plus">+</span>
      <span class="cs-k">inspiré par</span> ${esc(inspiration)}
    </p>
    ${idea.iteration ? `<p class="collision-strategy dim">Session ${idea.iteration}</p>` : ""}
  </div>`;
}

function renderClarity(idea) {
  const c = idea.clarity;
  if (!c) {
    const plain = idea.plain_summary;
    if (!plain) return "";
    return `
    <div class="idea-plain">
      <span class="plain-k">En clair</span>
      <p>${esc(plain.replace(/^En clair\s*:\s*/i, ""))}</p>
    </div>`;
  }
  const actions = (c.actions || []).map(a => `<li>${esc(a)}</li>`).join("");
  return `
  <div class="idea-clarity">
    <span class="plain-k">En clair</span>
    <p class="clarity-head">${esc(c.headline_fr || "")}</p>
    <p class="clarity-link"><strong>Pour votre sujet :</strong> ${esc((c.pour_vous || "").replace(/\*\*/g, ""))}</p>
    ${actions ? `
    <div class="clarity-actions">
      <span class="ca-k">À appliquer concrètement</span>
      <ol>${actions}</ol>
    </div>` : ""}
    ${c.test ? `<p class="clarity-test"><strong>Cette semaine (≈30 min) :</strong> ${esc(c.test)}</p>` : ""}
  </div>`;
}

function renderOriginalIdea(text) {
  if (!text) return "";
  return `
  <details class="idea-original">
    <summary>Texte original (tel que généré)</summary>
    <div class="idea-original-body">${mdInline(text)}</div>
  </details>`;
}

function renderActionBox(text) {
  if (!text) return "";
  return `<div class="action-box"><span class="ab-k">Prochaine étape</span><p>${esc(text)}</p></div>`;
}

function renderJourneyBar(step, name, bid, objective, session) {
  const steps = [
    { n: 1, label: "Préparer", hint: "Brief et textes" },
    { n: 2, label: "Générer", hint: "Lancer une session" },
    { n: 3, label: "Choisir", hint: "♥ / ↑ / ✕" },
    { n: 4, label: "Relancer", hint: "Nouvelle session" },
    { n: 5, label: "Bilan", hint: "Valider" },
  ];
  const complete = session?.synthesis_done;
  const nowActions = {
    1: "Remplir le brief et ajouter au moins un texte.",
    2: "Lancer une session pour obtenir de nouvelles idées.",
    3: "Choisir sur chaque carte : ♥ favorite · ↑ intéressante · ✕ à écarter.",
    4: "Relancer une session ou ouvrir le bilan.",
    5: complete
      ? `Bilan validé${session.synthesis_validated_at ? ` le ${session.synthesis_validated_at}` : ""}.`
      : "Lire vos favorites ♥, cocher celles à retenir, puis valider le bilan.",
  };
  const nav = {
    project: name,
    session_id: bid,
    objective: objective || "",
    steps,
    current_step: complete ? 5 : step,
    synthesis_complete: complete,
    validation: complete ? { validated_at: session.synthesis_validated_at } : null,
    now_label: complete ? "Bilan" : steps.find(s => s.n === step)?.label,
    now_action: nowActions[complete ? 5 : step],
    came_from: step > 1 && !complete ? steps.find(s => s.n === step - 1)?.label : null,
    next_step: complete ? null : (step < 5 ? steps.find(s => s.n === step + 1)?.label : null),
  };
  const compass = renderSessionCompass(nav);
  const cta = bid && step >= 3 ? `
  <div class="journey-cta">
    <span class="dim">Raccourcis :</span>
    ${step <= 4 ? `<button class="btn-small btn-primary" onclick="startRun('${esc(name)}','${esc(bid)}')">▸ Relancer</button>` : ""}
    <button class="btn-small btn-ghost" onclick="openSynthesis('${esc(name)}','${esc(bid)}')">◈ Bilan</button>
  </div>` : "";
  return compass + cta;
}

window.openSynthesis = async (name, bid) => {
  try {
    await api(`/api/projects/${encodeURIComponent(name)}/brainstorms/${encodeURIComponent(bid)}/synthesis`, { method: "POST" });
    location.hash = `#/p/${encodeURIComponent(name)}/b/${bid}/synthesis`;
  } catch (e) { toast(e.message, true); }
};

async function viewProject(name) {
  const p = await api(`/api/projects/${encodeURIComponent(name)}`);
  if (runMode === null) runMode = LIVE_AVAILABLE ? "live" : "demo";

  const latest = p.brainstorms.length ? p.brainstorms[p.brainstorms.length - 1] : null;
  const step = journeyStep(latest);
  const journeyHtml = renderJourneyBar(step, name, latest?.brainstorm_id || null, p.brief.objective, latest);

  const briefItems = [
    ["objective", p.brief.objective],
    ["context", p.brief.context],
    ["constraints", p.brief.constraints],
    ["what makes good ideas", p.brief.what_makes_good_ideas],
  ].filter(([, v]) => v).map(([k, v]) =>
    `<div class="bi"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join("");

  const textChips = p.texts.map(t =>
    `<span class="chip a" title="${esc(t.preview)}">${esc(t.id)} · ${esc(t.title)} · ${(t.chars / 1000).toFixed(1)}k chars</span>`).join("");

  const sessions = p.brainstorms.slice().reverse().map(b => {
    const iters = b.iterations_detail.map(it => `
      <div class="iter-row" onclick="location.hash='#/p/${encodeURIComponent(name)}/b/${b.brainstorm_id}/i/${it.iteration}'">
        <span class="it-n">ITER ${String(it.iteration).padStart(2, "0")}</span>
        <span class="it-stats">${it.generated} générées → ${it.retained} retenues → ${it.curated} curatées</span>
        <span class="it-stats dim">${it.strategies.join(" + ")}</span>
        <span class="badge ${it.flagged ? "ok" : "todo"}">${it.flagged ? "verdict ok" : "à juger"}</span>
      </div>`).join("");
    return `
    <div class="session">
      <div class="session-head">
        <span class="sid">${esc(b.brainstorm_id.replace("_", " "))}</span>
        <span class="stats">${b.iterations} iteration${b.iterations === 1 ? "" : "s"} · <b style="color:var(--love)">${b.loved}</b> loved · <b style="color:var(--like)">${b.liked}</b> liked</span>
        <span class="session-actions">
          ${b.synthesis_done ? `<span class="badge ok">bilan validé</span>` : b.has_report ? `<span class="badge todo">bilan à valider</span>` : ""}
          ${b.iterations > 0 ? `<button class="btn-small btn-primary" onclick="startRun('${esc(name)}','${b.brainstorm_id}')">▸ Relancer</button>` : ""}
          <button class="btn-small btn-ghost" onclick="openSynthesis('${esc(name)}','${b.brainstorm_id}')">◈ Bilan</button>
        </span>
      </div>
      ${iters || `<div class="iter-row dim mono" style="cursor:default">no iterations yet</div>`}
    </div>`;
  }).join("");

  app.innerHTML = `
  <section class="view">
    <div class="crumb"><a href="#/">← projets</a> / ${esc(name)}</div>
    <div class="proj-head">
      <div>
        <h1 class="page-title">${esc(name)}</h1>
        <div class="objective">${esc(p.brief.objective)}</div>
      </div>
    </div>

    <div class="launch-bar">
      <div class="grow">
        <div class="lb-title">Où en êtes-vous ?</div>
        <div class="lb-sub">5 étapes : préparer → générer → choisir → relancer → valider le bilan.
        ${runMode === "demo"
          ? ` Mode démo pour apprendre le parcours sans clé API.${LIVE_AVAILABLE ? "" : " <a href='#/settings' style='color:var(--spark)'>Connecter un provider</a> pour de vraies idées."}`
          : " Mode live : comptez 5–15 min par itération."}</div>
      </div>
      <div class="mode-toggle">
        <button class="${runMode === "live" ? "active" : ""}" ${LIVE_AVAILABLE ? "" : "disabled title='Connect a provider in Settings to enable live runs'"}
          onclick="runMode='live'; viewProject('${esc(name)}')">LIVE API</button>
        <button class="${runMode === "demo" ? "active" : ""}" onclick="runMode='demo'; viewProject('${esc(name)}')">DEMO</button>
      </div>
      <button class="btn-primary" onclick="startRun('${esc(name)}', null)">1 · Lancer une session</button>
    </div>

    ${journeyHtml}

    ${sessions || ""}

    <div class="panel">
      <h3>Brief</h3>
      <div class="brief-grid">${briefItems}</div>
      ${p.brief.forbidden_topics?.length ? `
        <div style="margin-top:18px"><div class="bi"><div class="k" style="font-family:var(--mono);font-size:10.5px;letter-spacing:0.12em;color:var(--love);text-transform:uppercase">forbidden topics</div>
        <div class="chips" style="margin-top:8px">${p.brief.forbidden_topics.map(t => `<span class="chip">${esc(t)}</span>`).join("")}</div></div></div>` : ""}
    </div>

    <div class="panel">
      <h3>Reference texts — beam one</h3>
      <div class="chips">${textChips}</div>
    </div>
  </section>`;
}

window.viewProject = viewProject;

window.startRun = async (name, brainstormId) => {
  try {
    const res = await api(`/api/projects/${encodeURIComponent(name)}/run`, {
      method: "POST",
      body: JSON.stringify({ brainstorm_id: brainstormId, mode: runMode || "demo" }),
    });
    location.hash = `#/p/${encodeURIComponent(name)}/run/${res.run_id}`;
  } catch (e) { toast(e.message, true); }
};

window.closeSession = openSynthesis;

/* ================================================================
   VIEW: Live run
================================================================ */

const PHASES = [
  ["domains", "◍", "Domains"],
  ["collide", "⚛", "Collide"],
  ["score", "▤", "Score"],
  ["curate", "◈", "Curate"],
];

async function viewRun(name, runId) {
  app.innerHTML = `
  <section class="view runview">
    <div class="crumb"><a href="#/">← projects</a> / <a href="#/p/${encodeURIComponent(name)}">${esc(name)}</a> / run</div>
    <h1 class="page-title"><span class="spinner" id="run-spin"></span>Iteration in progress</h1>
    <p class="page-sub" id="run-sub">Charging beams…</p>

    <div class="phase-track">${PHASES.map(([id, icon, label]) =>
      `<div class="phase" id="ph-${id}"><div class="ph-icon">${icon}</div><div class="ph-name">${label}</div></div>`).join("")}
    </div>

    <div class="run-rig" id="run-rig">
      <div class="beamline"></div>
      <div class="pa"></div><div class="pb"></div>
      <div class="flash"></div>
    </div>

    <div class="run-counters">
      <div class="ct"><div class="v" id="ct-domains">0</div><div class="k">domain sets</div></div>
      <div class="ct"><div class="v" id="ct-combos">0/0</div><div class="k">collisions</div></div>
      <div class="ct"><div class="v spark" id="ct-ideas">0</div><div class="k">raw ideas</div></div>
      <div class="ct"><div class="v cyan" id="ct-scored">0</div><div class="k">scored</div></div>
    </div>

    <div class="feed" id="feed"></div>
    <div class="run-done-bar" id="done-bar"></div>
  </section>`;

  let cursor = 0;
  let nDomains = 0, nIdeas = 0, nScored = 0, combosDone = 0, combosTotal = 0;

  const setPhase = (phase) => {
    let reached = false;
    for (const [id] of PHASES) {
      const el = document.getElementById(`ph-${id}`);
      if (!el) return;
      if (id === phase) { el.className = "phase active"; reached = true; }
      else el.className = "phase" + (reached ? "" : " done");
    }
  };

  const feedLine = (txt, cls = "") => {
    const feed = document.getElementById("feed");
    if (!feed) return;
    const time = new Date().toLocaleTimeString([], { hour12: false });
    feed.insertAdjacentHTML("beforeend",
      `<div class="ev ${cls}"><span class="t">${time}</span><span>${esc(txt)}</span></div>`);
    feed.scrollTop = feed.scrollHeight;
  };

  const handle = (ev) => {
    switch (ev.type) {
      case "init":
        document.getElementById("run-sub").textContent =
          `${ev.brainstorm_id} · iteration ${ev.iteration}`;
        feedLine(`iteration ${ev.iteration} initialized`);
        break;
      case "phase":
        setPhase(ev.phase);
        feedLine(`— phase: ${ev.phase} —`, "warn");
        break;
      case "domains_start":
        feedLine(`generating ${ev.strategy} domains (Opus)…`);
        break;
      case "domains_done":
        nDomains += ev.n_sets;
        document.getElementById("ct-domains").textContent = nDomains;
        feedLine(`${ev.strategy}: ${ev.n_sets} sets — ${ev.sets.map(s => s.name).join(" · ")}`, "hl");
        break;
      case "collide_start":
        combosTotal += ev.n_combos;
        document.getElementById("ct-combos").textContent = `${combosDone}/${combosTotal}`;
        feedLine(`${ev.strategy}: ${ev.n_combos} collisions queued`);
        break;
      case "combo_done":
        nIdeas += ev.n_ideas;
        combosDone++;
        document.getElementById("ct-combos").textContent = `${combosDone}/${combosTotal}`;
        document.getElementById("ct-ideas").textContent = nIdeas;
        feedLine(`⚛ ${ev.text_id} × ${ev.set_id} → ${ev.n_ideas} ideas`);
        break;
      case "collide_strategy_done":
        feedLine(`${ev.strategy} complete: ${ev.n_ideas} ideas`, "hl");
        break;
      case "score_start":
        feedLine(`scoring ${ev.n_ideas} ideas in ${ev.n_batches} batches…`);
        break;
      case "batch_scored":
        nScored += ev.n_scored;
        document.getElementById("ct-scored").textContent = nScored;
        feedLine(`▤ batch ${ev.batches_done}/${ev.batches_total}: ${ev.n_scored} scored`);
        break;
      case "done":
        feedLine(`✓ done — ${ev.ideas_generated} generated, ${ev.ideas_retained} retained (threshold ${ev.threshold_used}), ${ev.curated} curated`, "hl");
        break;
      case "error":
        feedLine(`✕ ${ev.message}`, "err");
        break;
    }
  };

  const poll = async () => {
    let snap;
    try { snap = await api(`/api/runs/${runId}?since=${cursor}`); }
    catch (e) {
      feedLine(`connection lost: ${e.message}`, "err");
      activePoller = setTimeout(poll, 2500);
      return;
    }
    snap.events.forEach(handle);
    cursor = snap.next_cursor;

    if (snap.status === "running") {
      activePoller = setTimeout(poll, 700);
      return;
    }

    document.getElementById("run-spin")?.remove();
    document.getElementById("run-rig")?.classList.add("idle");

    if (snap.status === "done") {
      PHASES.forEach(([id]) => document.getElementById(`ph-${id}`).className = "phase done");
      document.querySelector(".page-title").textContent = "Iteration complete";
      const r = snap.result;
      document.getElementById("run-sub").textContent =
        `${r.ideas_generated} ideas collided → ${r.ideas_retained} retained → ${r.curated} curated for your verdict`;
      document.getElementById("done-bar").innerHTML = `
        <a class="btn btn-primary" href="#/p/${encodeURIComponent(name)}/b/${snap.brainstorm_id}/i/${r.iteration}">Review the ${r.curated} curated ideas →</a>
        <a class="btn btn-ghost" href="#/p/${encodeURIComponent(name)}">Back to project</a>`;
    } else {
      document.querySelector(".page-title").textContent = "Run failed";
      document.getElementById("run-sub").textContent = snap.error || "unknown error";
      document.getElementById("done-bar").innerHTML = `
        <a class="btn btn-ghost" href="#/p/${encodeURIComponent(name)}">Back to project</a>`;
    }
  };

  poll();
}

/* ================================================================
   VIEW: Iteration / curation
================================================================ */

let curFlags = {};

const AXIS_LABELS = {
  originality: "orig", resistance: "resist", thesis_density: "thesis",
  concrete_grounding: "ground", cognitive_load: "cogn",
};

const AXIS_TIPS = {
  originality: "Originality — is the underlying idea genuinely new, or repackaged standard advice?",
  resistance: "Resistance — does the idea survive pushback, or does one objection collapse it?",
  thesis_density: "Thesis — can it be stated as one clear, testable claim?",
  concrete_grounding: "Grounding — could real facts, figures or examples back it up?",
  cognitive_load: "Cognitive load — does it make you stop and think, or is it instantly forgettable?",
};

function flagButtons(ideaId) {
  const f = curFlags[ideaId];
  return `
  <div class="flag-row">
    <button class="flag-btn ${f === "loved" ? "on-loved" : ""}" onclick="setFlag('${ideaId}','loved')">♥ love</button>
    <button class="flag-btn ${f === "liked" ? "on-liked" : ""}" onclick="setFlag('${ideaId}','liked')">↑ like</button>
    <button class="flag-btn ${f === "trashed" ? "on-trashed" : ""}" onclick="setFlag('${ideaId}','trashed')">✕ trash</button>
  </div>`;
}

window.setFlag = (ideaId, flag) => {
  curFlags[ideaId] = curFlags[ideaId] === flag ? undefined : flag;
  if (!curFlags[ideaId]) delete curFlags[ideaId];
  const card = document.getElementById(`idea-${ideaId}`);
  if (card) {
    card.className = "idea-card" + (curFlags[ideaId] ? ` flag-${curFlags[ideaId]}` : "");
    card.querySelector(".flag-row").outerHTML = flagButtons(ideaId);
  }
  updateCounts();
};

function updateCounts() {
  const counts = { loved: 0, liked: 0, trashed: 0 };
  Object.values(curFlags).forEach(f => counts[f]++);
  const el = document.getElementById("flag-counts");
  if (el) el.innerHTML =
    `<b class="lv">${counts.loved}</b> loved · <b class="lk">${counts.liked}</b> liked · ${counts.trashed} trashed`;
}

async function viewIteration(name, bid, n) {
  const it = await api(`/api/projects/${encodeURIComponent(name)}/brainstorms/${bid}/iterations/${n}`);
  curFlags = { ...it.flags };

  const maxH = Math.max(...it.stats.histogram, 1);
  const thrIdx = it.stats.threshold ? Math.floor((it.stats.threshold - 1) / 4 * 16) : 99;
  const histo = it.stats.histogram.map((c, i) =>
    `<div class="bar ${i >= thrIdx ? "hot" : ""}" style="height:${Math.max(2, c / maxH * 46)}px" title="${c} ideas"></div>`).join("");

  const ideaCards = it.curated.map(idea => {
    const axes = Object.entries(idea.scores || {}).map(([k, v]) => `
      <div class="axis"><span class="ax-k" data-tip="${esc(AXIS_TIPS[k] || k)}">${AXIS_LABELS[k] || k}</span>
        <span class="ax-bar"><i style="width:${(v / 5) * 100}%"></i></span></div>`).join("");
    return `
    <div class="idea-card ${curFlags[idea.idea_id] ? "flag-" + curFlags[idea.idea_id] : ""}" id="idea-${idea.idea_id}">
      <div class="idea-top">
        <span class="idea-rank">#${String(idea.rank).padStart(2, "0")}</span>
        <span class="idea-score">${Number(idea.score).toFixed(2)}</span>
      </div>
      ${renderCollisionBlock(idea)}
      ${renderClarity(idea)}
      ${renderOriginalIdea(idea.text)}
      ${idea.why_selected && !(idea.text || "").includes("simulated demo") ? `<div class="idea-why">${esc(idea.why_selected)}</div>` : ""}
      ${renderActionBox(idea.action)}
      <div class="axes">${axes}</div>
      ${flagButtons(idea.idea_id)}
    </div>`;
  }).join("");

  const domains = Object.entries(it.domains).map(([strategy, sets]) => `
    <details class="dom-strategy">
      <summary>${esc(strategy)} strategy — ${sets.length} domain sets</summary>
      <div class="dom-sets">${sets.map(s => `
        <div class="dom-set"><div class="ds-name">${esc(s.name)}</div>
          <ul>${s.domains.map(d => `<li title="${esc(d.active_principle)}">${esc(d.name)}</li>`).join("")}</ul>
        </div>`).join("")}</div>
    </details>`).join("");

  const isDemo = it.curated.some(c => (c.text || "").includes("simulated demo idea"));

  app.innerHTML = `
  <section class="view">
    ${renderSessionCompass(it.navigation)}
    <div class="crumb"><a href="#/">← projets</a> / <a href="#/p/${encodeURIComponent(name)}">${esc(name)}</a> / ${esc(bid)} / iteration ${n}</div>
    <div class="cur-head">
      <div>
        <h1 class="page-title">Itération ${n} — votre verdict</h1>
        <p class="page-sub" style="margin-bottom:0">${it.config.ideas_generated ?? "?"} idées en collision ·
          ${it.stats.retained} passent le judge (seuil ${it.stats.threshold ?? "—"}) ·
          ${it.curated.length} curatées ci-dessous. Vos ♥ / ↑ / ✕ orientent la prochaine itération.</p>
      </div>
      <div>
        <div class="histo">${histo}</div>
        <div class="mono dim" style="margin-top:6px;text-align:right" data-tip="Each bar is a score bucket from 1 to 5. Amber bars passed the quality threshold; only those could be curated.">score distribution 1→5 ⓘ</div>
      </div>
    </div>

    ${isDemo ? `
    <div class="help-note demo-banner">
      <span class="hn-icon">⚠</span>
      <span>These are <strong>simulated placeholder ideas</strong> from demo mode — they show you the
      workflow, not real creativity. Connect a provider in <a href="#/settings" style="color:var(--spark)">Settings</a>
      to generate real ideas.</span>
    </div>` : ""}

    <div class="help-note">
      <span class="hn-icon">◍</span>
      <span><strong>Étape 3 — choisir :</strong>
      <strong style="color:var(--love)">♥</strong> favorite ·
      <strong style="color:var(--like)">↑</strong> intéressante ·
      <strong>✕</strong> à écarter. Puis enregistrer en bas de page.</span>
    </div>

    ${ideaCards || `<div class="empty" style="margin-top:24px">No curated ideas in this iteration.</div>`}

    <div class="cur-submit">
      <span class="counts" id="flag-counts"></span>
      ${it.has_html_report ? `<a class="btn-small btn-ghost" href="/api/projects/${encodeURIComponent(name)}/brainstorms/${encodeURIComponent(bid)}/iterations/${n}/report.html" target="_blank" rel="noopener">iteration HTML report ↗</a>` : ""}
      <input type="text" id="f-feedback" placeholder="Note de pilotage pour la prochaine itération (optionnel)…" value="${esc(it.feedback)}">
      <button class="btn-primary" onclick="submitFlags('${esc(name)}','${bid}',${n})">Enregistrer le verdict</button>
    </div>

    <div class="syn-next panel">
      <h3>Et ensuite ?</h3>
      <p class="dim">Après vos choix : <strong>relancer</strong> une session ou ouvrir le <strong>bilan</strong> pour valider vos favorites ♥.</p>
      <div class="hero-actions" style="margin-top:12px">
        <button class="btn btn-small btn-primary" onclick="startRun('${esc(name)}','${bid}')">▸ Relancer</button>
        <button class="btn btn-small btn-ghost" onclick="openSynthesis('${esc(name)}','${bid}')">◈ Voir le bilan</button>
      </div>
    </div>

    <div class="panel">
      <h3>Beam two — domaines distants de cette itération</h3>
      ${domains || `<span class="mono dim">no domain data</span>`}
    </div>
  </section>`;
  updateCounts();
  const anchor = location.hash.includes("#idea-") ? location.hash.split("#").pop() : null;
  if (anchor) {
    requestAnimationFrame(() => document.getElementById(anchor)?.scrollIntoView({ behavior: "smooth", block: "center" }));
  }
}

window.submitFlags = async (name, bid, n) => {
  try {
    await api(`/api/projects/${encodeURIComponent(name)}/brainstorms/${bid}/iterations/${n}/flags`, {
      method: "POST",
      body: JSON.stringify({
        flags: curFlags,
        feedback: document.getElementById("f-feedback").value,
      }),
    });
    toast("Verdict enregistré — vos ♥ love orienteront la prochaine itération");
    location.hash = `#/p/${encodeURIComponent(name)}`;
  } catch (e) { toast(e.message, true); }
};

/* ================================================================
   VIEW: Session synthesis (ideation report)
================================================================ */

function synIdeaCard(idea, variant, validation) {
  const score = idea.score != null ? Number(idea.score).toFixed(2) : "—";
  const link = idea.link ? `<a class="syn-back-link" href="${idea.link}">↩ Voir en session ${idea.iteration}</a>` : "";
  const isDone = validation?.done;
  const retained = idea.retained || (isDone && (validation?.chosen || []).includes(idea.idea_id));
  const chooseBox = variant === "loved" && !isDone ? `
    <label class="syn-choose">
      <input type="checkbox" class="syn-chk" data-id="${esc(idea.idea_id)}" checked>
      Je retiens cette idée
    </label>` : "";
  const retainedBadge = isDone && retained
    ? `<span class="syn-retained">✓ Retenue pour la suite</span>` : "";
  return `
  <article class="syn-idea ${variant}${retained ? " retained" : ""}" id="syn-${esc(idea.idea_id || "")}">
    <header class="syn-idea-head">
      <span class="syn-rank">#${String(idea.rank || "?").padStart(2, "0")}</span>
      <span class="syn-score">${score}</span>
      ${variant === "loved" ? '<span class="flag love">♥ Favorite</span>' : variant === "liked" ? '<span class="flag like">↑ Intéressante</span>' : ""}
      ${retainedBadge}
    </header>
    ${renderCollisionBlock(idea)}
    ${renderClarity(idea)}
    ${renderOriginalIdea(idea.text)}
    ${idea.why_selected && !(idea.text || "").includes("simulated demo") ? `<p class="syn-why"><strong>Pourquoi retenue :</strong> ${esc(idea.why_selected)}</p>` : ""}
    ${idea.challenge ? `<p class="syn-challenge"><strong>Question :</strong> ${esc(idea.challenge)}</p>` : ""}
    ${renderActionBox(idea.action)}
    ${chooseBox}
    ${link}
  </article>`;
}

function synTimelineRow(t) {
  return `
  <div class="syn-tl-row">
    <span class="syn-tl-n">Iter ${String(t.iteration).padStart(2, "0")}</span>
    <span class="syn-tl-flow">${t.generated} générées → ${t.retained} retenues → ${t.curated} curatées</span>
    <span class="syn-tl-flags"><b class="lv">${t.loved}</b> ♥ · <b class="lk">${t.liked}</b> ↑ · ${t.trashed} ✕</span>
    <span class="badge ${t.flagged ? "ok" : "todo"}">${t.flagged ? "choix ok" : "à choisir"}</span>
  </div>`;
}

async function viewSynthesis(name, bid) {
  let syn;
  try {
    syn = await api(`/api/projects/${encodeURIComponent(name)}/brainstorms/${encodeURIComponent(bid)}/synthesis`);
  } catch (_) {
    syn = await api(`/api/projects/${encodeURIComponent(name)}/brainstorms/${encodeURIComponent(bid)}/synthesis`, { method: "POST" });
  }

  const s = syn.stats;
  const v = syn.validation || {};
  const emptyState = !syn.shortlist.length && !syn.explore.length
    ? `<div class="syn-empty">
        <p>Aucune idée choisie pour l'instant. Retournez sur les cartes de session, puis revenez ici.</p>
        <a class="btn btn-primary" href="#/p/${encodeURIComponent(name)}">← Retour au projet</a>
      </div>` : "";

  const validatePanel = !v.done && syn.shortlist.length ? `
    <section class="syn-validate panel">
      <h2>Valider le bilan</h2>
      <p class="dim">Cochez les idées ♥ que vous retenez. Notez ce que vous ferez ensuite, puis validez pour clore la session.</p>
      <textarea id="syn-next-note" class="syn-note-input" placeholder="Ex : en parler à l'équipe lundi, faire un brouillon…">${esc(v.note || "")}</textarea>
      <button class="btn btn-primary" onclick="validateSynthesis('${esc(name)}','${esc(bid)}')">Valider le bilan ✓</button>
    </section>` : "";

  app.innerHTML = `
  <section class="view synthesis">
    ${renderSessionCompass(syn.navigation)}
    <div class="crumb"><a href="#/">← projets</a> / <a href="#/p/${encodeURIComponent(name)}">${esc(name)}</a> / bilan</div>

    <header class="syn-hero">
      <p class="syn-eyebrow">Bilan · ${esc(bid.replace("_", " "))}</p>
      <h1 class="page-title">${esc(syn.objective || name)}</h1>
      <p class="syn-dek">Mis à jour ${esc(syn.updated)} · ${s.iterations} session${s.iterations === 1 ? "" : "s"}</p>
      <div class="syn-stats">
        <span class="syn-pill loved"><b>${s.loved}</b> favorites ♥</span>
        <span class="syn-pill liked"><b>${s.liked}</b> intéressantes ↑</span>
        <span class="syn-pill dim"><b>${s.trashed}</b> écartées</span>
        ${v.done ? `<span class="syn-pill ok">✓ validé</span>` : `<span class="syn-pill todo">à valider</span>`}
      </div>
    </header>

    <section class="syn-howto">
      <h2>Comment lire ce bilan</h2>
      <div class="syn-howto-grid">
        <div class="syn-howto-card">
          <span class="sh-n">1</span>
          <h3>En clair = quoi faire</h3>
          <p>Titre + lien avec votre sujet + 3 actions + un test de 30 min. L'original anglais reste en dessous.</p>
        </div>
        <div class="syn-howto-card">
          <span class="sh-n">2</span>
          <h3>Prochaine étape</h3>
          <p>Suit le test : notez une variante, ou passez à la 2e action — pas une recopie du test.</p>
        </div>
        <div class="syn-howto-card">
          <span class="sh-n">3</span>
          <h3>Clôturer</h3>
          <p>Cochez vos favorites ♥, notez la suite, puis <strong>Valider le bilan</strong> pour marquer la fin.</p>
        </div>
      </div>
    </section>

    ${syn.shortlist.length ? `
    <section class="syn-section loved-section">
      <div class="syn-sec-head">
        <h2>♥ Vos favorites</h2>
        <span class="syn-count">${syn.shortlist.length} idée${syn.shortlist.length === 1 ? "" : "s"}</span>
      </div>
      <p class="syn-sec-lead">Celles que vous avez marquées ♥ — à lire en priorité.</p>
      <div class="syn-ideas">${syn.shortlist.map(i => synIdeaCard(i, "loved", v)).join("")}</div>
    </section>` : ""}

    ${syn.explore.length ? `
    <section class="syn-section explore-section">
      <div class="syn-sec-head">
        <h2>↑ À garder en tête</h2>
        <span class="syn-count">${syn.explore.length} idée${syn.explore.length === 1 ? "" : "s"}</span>
      </div>
      <p class="syn-sec-lead">Intéressantes mais moins urgentes — utiles plus tard ou en combinaison.</p>
      <div class="syn-ideas compact">${syn.explore.map(i => synIdeaCard(i, "liked", v)).join("")}</div>
    </section>` : ""}

    ${syn.feedback.length ? `
    <section class="syn-section feedback-section">
      <h2>Vos notes entre les sessions</h2>
      <p class="syn-sec-lead">Ce que vous aviez demandé pour la suite.</p>
      ${syn.feedback.map(f => `
        <blockquote class="syn-feedback"><span class="mono dim">Session ${f.iteration}</span> — ${esc(f.text)}</blockquote>`).join("")}
    </section>` : ""}

    ${syn.timeline.length ? `
    <section class="syn-section timeline-section">
      <h2>Résumé des sessions</h2>
      <p class="syn-sec-lead">Combien d'idées à chaque tour — la plupart sont filtrées avant d'arriver ici.</p>
      <div class="syn-timeline">${syn.timeline.map(synTimelineRow).join("")}</div>
    </section>` : ""}

    ${syn.insights.length ? `
    <section class="syn-section insights-section">
      <details class="syn-details">
        <summary>Autres idées (${syn.insights.length})</summary>
        <p class="syn-sec-lead dim">Moins liées à vos textes — à lire avec recul.</p>
        ${syn.insights.map(i => `
          <div class="syn-insight"><span class="mono dim">[${i.score ?? "—"}] session ${i.iteration}</span>
          <p>${mdInline(i.text)}</p></div>`).join("")}
      </details>
    </section>` : ""}

    ${syn.discarded.length ? `
    <section class="syn-section discarded-section">
      <details class="syn-details">
        <summary>Écartées (${syn.discarded.length})</summary>
        <ul class="syn-discarded-list">
          ${syn.discarded.map(d => `
            <li><span class="mono dim">[${d.score ?? "—"}] session ${d.iteration}</span> ${esc(d.summary || d.text.slice(0, 120))}</li>`).join("")}
        </ul>
      </details>
    </section>` : ""}

    ${emptyState}
    ${validatePanel}

    <footer class="syn-footer">
      <a class="btn btn-ghost" href="#/p/${encodeURIComponent(name)}">← Retour au projet</a>
      ${syn.has_html ? `<a class="btn btn-ghost" href="/api/projects/${encodeURIComponent(name)}/brainstorms/${encodeURIComponent(bid)}/report.html" target="_blank" rel="noopener">Export HTML ↗</a>` : ""}
      <button class="btn btn-ghost" onclick="viewReport('${esc(name)}','${esc(bid)}')">Vue technique</button>
    </footer>
  </section>`;
}

window.validateSynthesis = async (name, bid) => {
  const chosen = [...document.querySelectorAll(".syn-chk:checked")].map(el => el.dataset.id);
  const note = document.getElementById("syn-next-note")?.value || "";
  if (!chosen.length) {
    toast("Cochez au moins une idée ♥ à retenir", true);
    return;
  }
  try {
    await api(`/api/projects/${encodeURIComponent(name)}/brainstorms/${encodeURIComponent(bid)}/synthesis/validate`, {
      method: "POST",
      body: JSON.stringify({ chosen, note }),
    });
    toast("Bilan validé — session terminée");
    viewSynthesis(name, bid);
  } catch (e) { toast(e.message, true); }
};

async function viewReport(name, bid) {
  let rep;
  try {
    rep = await api(`/api/projects/${encodeURIComponent(name)}/brainstorms/${bid}/report`);
  } catch (_) {
    rep = await api(`/api/projects/${encodeURIComponent(name)}/brainstorms/${bid}/report`, { method: "POST" });
  }
  app.innerHTML = `
  <section class="view">
    <div class="crumb"><a href="#/p/${encodeURIComponent(name)}">← synthèse</a> / vue technique</div>
    <div class="sec-head" style="margin-top:20px">
      <h2>Rapport technique</h2>
      <span class="session-actions">
        <a class="btn-small btn-ghost" href="#/p/${encodeURIComponent(name)}/b/${encodeURIComponent(bid)}/synthesis">◈ Retour à la synthèse</a>
        <button class="btn-small btn-ghost" onclick="navigator.clipboard.writeText(REPORT_MD).then(()=>toast('Markdown copié'))">copier markdown</button>
      </span>
    </div>
    <div class="report-body">${renderMarkdown(rep.markdown)}</div>
  </section>`;
  window.REPORT_MD = rep.markdown;
}

/* ================================================================
   Boot
================================================================ */

function updatePill(provider, liveAvailable) {
  const pill = document.getElementById("mode-pill");
  pill.classList.remove("live", "demo");
  if (liveAvailable) {
    pill.textContent = `● live: ${provider}`;
    pill.classList.add("live");
  } else {
    pill.textContent = "○ demo mode — set up in settings";
    pill.classList.add("demo");
  }
  pill.onclick = () => location.hash = "#/settings";
  pill.style.cursor = "pointer";
}

(async function boot() {
  try {
    const st = await api("/api/status");
    LIVE_AVAILABLE = st.live_available;
    updatePill(st.provider, st.live_available);
  } catch (_) {}
  route();
})();
