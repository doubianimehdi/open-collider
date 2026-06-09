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

/* full markdown renderer for reports */
function renderMarkdown(md) {
  const lines = md.split("\n");
  let html = "", inList = false, tableBuf = [];

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

  for (const line of lines) {
    if (/^\s*\|.*\|\s*$/.test(line)) { closeList(); tableBuf.push(line); continue; }
    flushTable();
    if (/^---+\s*$/.test(line)) { closeList(); html += "<hr>"; continue; }
    let m;
    if ((m = line.match(/^(#{1,4})\s+(.*)/))) {
      closeList();
      const lvl = Math.min(m[1].length, 3);
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
  flushTable(); closeList();
  return html;
}

/* ================================================================
   Router
================================================================ */

const routes = [
  { re: /^#?\/?$/, view: viewHome },
  { re: /^#\/new$/, view: viewNewProject },
  { re: /^#\/p\/([^/]+)$/, view: viewProject },
  { re: /^#\/p\/([^/]+)\/run\/([^/]+)$/, view: viewRun },
  { re: /^#\/p\/([^/]+)\/b\/([^/]+)\/i\/(\d+)$/, view: viewIteration },
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
        <div class="kicker">Semantic collision engine</div>
        <h1>Escape the<br><span class="accent-a">default</span>-prompt<br><span class="accent-b">basin</span>.</h1>
        <p class="lede">Ask an LLM for ideas and 80% land in the same predictable region.
        Open Collider forces the model through <strong>counter-intuitive principles from
        structurally distant domains</strong> — glass physics, fermentation biology, siegecraft —
        before it generates. The collisions produce ideas that couldn't exist otherwise.</p>
        <div class="hero-actions">
          <a class="btn btn-primary" href="#/new">+ New project</a>
          <a class="btn btn-ghost" href="https://cdriclion.substack.com/p/why-direct-prompting-pushes-llms" target="_blank" rel="noopener">Read the theory ↗</a>
        </div>
      </div>
      <div class="rig" aria-hidden="true">
        <div class="ring"></div><div class="ring r2"></div><div class="ring r3"></div>
        <div class="orbit a"><div class="p"></div></div>
        <div class="orbit b"><div class="p"></div></div>
        <div class="core"></div>
        <div class="spark-label mono">your material × distant domains → non-trivial ideas</div>
      </div>
    </div>

    <div class="pipeline">
      <div class="step"><div class="n">01 / BRIEF</div><h3>Define the problem</h3>
        <p>Your ideation goal, constraints, and raw reference texts — the first beam.</p></div>
      <div class="step"><div class="n">02 / DOMAINS</div><h3>Charge the second beam</h3>
        <p>An LLM generates structurally distant domains, each carrying a counter-intuitive active principle.</p></div>
      <div class="step"><div class="n">03 / COLLIDE</div><h3>Mass generation</h3>
        <p>Every text × domain pair collides in an isolated context. Hundreds of candidate ideas per iteration.</p></div>
      <div class="step"><div class="n">04 / CURATE</div><h3>Extract the gems</h3>
        <p>A 5-axis judge scores everything; you flag love / like / trash. Feedback steers the next iteration.</p></div>
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
    <p class="page-sub">Define your ideation problem and feed the collider raw reference material.
    The richer the material, the better the collisions.</p>

    <div class="fgroup">
      <label>Project name <span class="req">*</span></label>
      <input type="text" id="f-name" placeholder="e.g. discover_weekly_redesign">
    </div>
    <div class="fgroup">
      <label>Objective <span class="req">*</span></label>
      <textarea id="f-objective" rows="3" placeholder="What are you ideating on? e.g. Structural redesigns of Spotify's Discover Weekly that break users out of their taste bubble."></textarea>
    </div>
    <div class="fgroup">
      <label>Context</label>
      <textarea id="f-context" rows="2" placeholder="Where will the ideas be used? Who is the audience?"></textarea>
    </div>
    <div class="fgroup">
      <label>Constraints</label>
      <textarea id="f-constraints" rows="2" placeholder="Hard limits the ideas must respect."></textarea>
    </div>
    <div class="fgroup">
      <label>What makes a good idea</label>
      <textarea id="f-good" rows="2" placeholder="Structural qualities you're looking for — testable mechanisms, in your voice, etc."></textarea>
      <div class="hint">This calibrates the 5-axis judge: originality, resistance, thesis density, grounding, cognitive load.</div>
    </div>
    <div class="fgroup">
      <label>Globally forbidden topics</label>
      <input type="text" id="f-forbidden" placeholder="Comma-separated — themes the collider must avoid entirely">
    </div>

    <div class="sec-head" style="margin-top:44px">
      <h2>Reference texts <span class="req" style="color:var(--spark)">*</span></h2>
      <button class="btn-small btn-ghost" onclick="addText()">+ add text</button>
    </div>
    <p class="page-sub" style="margin-bottom:18px">Beam one of the collider: raw material the model collides against distant domains. At least one text is required.</p>
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

async function viewProject(name) {
  const p = await api(`/api/projects/${encodeURIComponent(name)}`);
  if (runMode === null) runMode = LIVE_AVAILABLE ? "live" : "demo";

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
        <span class="it-stats">${it.generated} generated → ${it.retained} retained → ${it.curated} curated</span>
        <span class="it-stats dim">${it.strategies.join(" + ")}</span>
        <span class="badge ${it.flagged ? "ok" : "todo"}">${it.flagged ? "feedback in" : "awaiting your verdict"}</span>
      </div>`).join("");
    return `
    <div class="session">
      <div class="session-head">
        <span class="sid">${esc(b.brainstorm_id.replace("_", " "))}</span>
        <span class="stats">${b.iterations} iteration${b.iterations === 1 ? "" : "s"} · <b style="color:var(--love)">${b.loved}</b> loved · <b style="color:var(--like)">${b.liked}</b> liked</span>
        <span class="session-actions">
          ${b.iterations > 0 ? `<button class="btn-small btn-ghost" onclick="startRun('${esc(name)}','${b.brainstorm_id}')">▸ next iteration</button>` : ""}
          <button class="btn-small btn-ghost" onclick="closeSession('${esc(name)}','${b.brainstorm_id}')">⬡ report</button>
        </span>
      </div>
      ${iters || `<div class="iter-row dim mono" style="cursor:default">no iterations yet</div>`}
    </div>`;
  }).join("");

  app.innerHTML = `
  <section class="view">
    <div class="crumb"><a href="#/">← projects</a> / ${esc(name)}</div>
    <div class="proj-head">
      <div>
        <h1 class="page-title">${esc(name)}</h1>
        <div class="objective">${esc(p.brief.objective)}</div>
      </div>
    </div>

    <div class="launch-bar">
      <div class="grow">
        <div class="lb-title">Collision chamber</div>
        <div class="lb-sub">${runMode === "demo"
          ? "Demo mode simulates the full pipeline instantly with placeholder ideas — perfect for exploring the workflow."
          : "Live mode calls the Anthropic API: Opus for domains, Sonnet for mass generation and scoring. ~$2–3 and ~10 min per iteration."}</div>
      </div>
      <div class="mode-toggle">
        <button class="${runMode === "live" ? "active" : ""}" ${LIVE_AVAILABLE ? "" : "disabled title='Add ANTHROPIC_API_KEY to .env to enable'"}
          onclick="runMode='live'; viewProject('${esc(name)}')">LIVE API</button>
        <button class="${runMode === "demo" ? "active" : ""}" onclick="runMode='demo'; viewProject('${esc(name)}')">DEMO</button>
      </div>
      <button class="btn-primary" onclick="startRun('${esc(name)}', null)">⚛ Start new session</button>
    </div>

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

window.closeSession = async (name, bid) => {
  try {
    await api(`/api/projects/${encodeURIComponent(name)}/brainstorms/${bid}/report`, { method: "POST" });
    location.hash = `#/p/${encodeURIComponent(name)}/b/${bid}/report`;
  } catch (e) { toast(e.message, true); }
};

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
      <div class="axis"><span class="ax-k">${AXIS_LABELS[k] || k}</span>
        <span class="ax-bar"><i style="width:${(v / 5) * 100}%"></i></span></div>`).join("");
    return `
    <div class="idea-card ${curFlags[idea.idea_id] ? "flag-" + curFlags[idea.idea_id] : ""}" id="idea-${idea.idea_id}">
      <div class="idea-top">
        <span class="idea-rank">#${String(idea.rank).padStart(2, "0")}</span>
        <span class="idea-score">${Number(idea.score).toFixed(2)}</span>
        <span class="idea-source">${esc(idea.source_note)}</span>
      </div>
      <div class="idea-text">${mdInline(idea.text)}</div>
      ${idea.why_selected ? `<div class="idea-why">${esc(idea.why_selected)}</div>` : ""}
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

  app.innerHTML = `
  <section class="view">
    <div class="crumb"><a href="#/">← projects</a> / <a href="#/p/${encodeURIComponent(name)}">${esc(name)}</a> / ${esc(bid)} / iteration ${n}</div>
    <div class="cur-head">
      <div>
        <h1 class="page-title">Iteration ${n} — your verdict</h1>
        <p class="page-sub" style="margin-bottom:0">${it.config.ideas_generated ?? "?"} ideas collided ·
          ${it.stats.retained} survived the judge (threshold ${it.stats.threshold ?? "—"}) ·
          ${it.curated.length} curated below. Your love / like / trash steers the next iteration.</p>
      </div>
      <div>
        <div class="histo">${histo}</div>
        <div class="mono dim" style="margin-top:6px;text-align:right">score distribution 1→5</div>
      </div>
    </div>

    ${ideaCards || `<div class="empty" style="margin-top:24px">No curated ideas in this iteration.</div>`}

    <div class="cur-submit">
      <span class="counts" id="flag-counts"></span>
      <input type="text" id="f-feedback" placeholder="Optional steering note for the next iteration…" value="${esc(it.feedback)}">
      <button class="btn-primary" onclick="submitFlags('${esc(name)}','${bid}',${n})">Lock in feedback</button>
    </div>

    <div class="panel">
      <h3>Beam two — the distant domains used in this iteration</h3>
      ${domains || `<span class="mono dim">no domain data</span>`}
    </div>
  </section>`;
  updateCounts();
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
    toast("Feedback locked in — loved ideas will steer the next iteration");
    location.hash = `#/p/${encodeURIComponent(name)}`;
  } catch (e) { toast(e.message, true); }
};

/* ================================================================
   VIEW: Report
================================================================ */

async function viewReport(name, bid) {
  let rep;
  try {
    rep = await api(`/api/projects/${encodeURIComponent(name)}/brainstorms/${bid}/report`);
  } catch (_) {
    rep = await api(`/api/projects/${encodeURIComponent(name)}/brainstorms/${bid}/report`, { method: "POST" });
  }
  app.innerHTML = `
  <section class="view">
    <div class="crumb"><a href="#/">← projects</a> / <a href="#/p/${encodeURIComponent(name)}">${esc(name)}</a> / ${esc(bid)} / report</div>
    <div class="sec-head" style="margin-top:20px">
      <h2>Session report</h2>
      <button class="btn-small btn-ghost" onclick="navigator.clipboard.writeText(REPORT_MD).then(()=>toast('Markdown copied'))">copy markdown</button>
    </div>
    <div class="report-body">${renderMarkdown(rep.markdown)}</div>
  </section>`;
  window.REPORT_MD = rep.markdown;
}

/* ================================================================
   Boot
================================================================ */

(async function boot() {
  try {
    const st = await api("/api/status");
    LIVE_AVAILABLE = st.live_available;
    const pill = document.getElementById("mode-pill");
    pill.textContent = st.live_available ? "● API connected" : "○ demo mode (no API key)";
    pill.classList.add(st.live_available ? "live" : "demo");
  } catch (_) {}
  route();
})();
