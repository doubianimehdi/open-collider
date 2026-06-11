# Journal des changements — fork `doubianimehdi/open-collider`

Ce dépôt part de [CL-ML/open-collider](https://github.com/CL-ML/open-collider) et ajoute
une interface web plus l'intégration locale de trois pull requests upstream encore ouvertes
chez l'auteur original.

**Branche principale :** `main`  
**Derniers merges intégrés :** juin 2026

---

## Clarté actionnable v2 (juin 2026)

Génération du bloc **En clair** (français) **à la création** de chaque idée, ancrée au brief utilisateur.

### Pipeline

| Étape | Détail |
|-------|--------|
| Génération | Après chaque collision, appel LLM par lot (live) ou templates demo FR |
| Schéma | `clarity` v2 : `headline_fr`, `pour_vous`, `actions[]`, `test`, `version`, `source` |
| Curation | Clarté attachée avant scoring ; backfill auto si `version < 2` au chargement |
| UI | Boussole 5 étapes, bilan validable (`synthesis_done.json`), collision domaine du texte |
| Prochaine étape | Consigne complémentaire au test — pas de recopie |

### Fichiers

- `webapp/clarity_llm.py` — prompt, parse, batch attach
- `webapp/idea_clarity.py` — build/backfill, exports plain_summary
- `webapp/session_context.py` — navigation, enrichissement idées
- `webapp/recommendations.py` — suggestions Prochaine étape
- `webapp/synthesis.py` — agrégation bilan
- `projects/_template/prompts/idea_clarity.md` — consignes LLM clarté
- `tests/test_clarity_llm.py` — fixture Discover Weekly / raid front turbulence

### Documentation

- `webapp/static/manuel.md` — manuel FR (`#/manuel`)
- Guide intégré EN (`#/guide`) — section « How to read En clair »

---

## Web UI (PR #1 du fork)

**Commits :** `40d245d`, `aecda8a`, merge `658edf6`

### Ajouts

| Zone | Détail |
|------|--------|
| `webapp/server.py` | API FastAPI : projets, runs streaming, curation, rapports, settings |
| `webapp/orchestrator.py` | Runner d'itération ; clients Demo + OpenAI-compatible ; overrides settings |
| `webapp/settings.py` | Store local provider / clés / modèles / pipeline |
| `webapp/static/` | SPA sans build (HTML, CSS, JS) |
| `webapp/README.md` | Doc technique EN |
| `webapp/static/manuel.md` | Manuel utilisateur FR |
| `.gitignore` | `webapp/settings.json` |

### Fonctionnalités utilisateur

- Accueil pédagogique (analogie collisionneur, quand utiliser / éviter)
- Assistant projet (brief + textes de référence)
- Chambre de collision avec progression live (domaines → collide → score → curate)
- Curation love / like / trash + note de pilotage
- Mode **demo** (sans clé) et **live** (Anthropic ou API compatible OpenAI)
- Page **Settings** : clés masquées, test de connexion, modèles par étape, tuning pipeline
- Page **Guide** intégrée (EN)
- Rapports session markdown dans l'UI + liens vers rapports HTML

### Tests

- 37 tests pytest passent après intégration (`tests/test_smoke.py`, `tests/test_api_mode.py`)

---

## Upstream PR #1 — Rapports HTML brainstorm

**Auteur :** arsis-dev (`html-reports`)  
**Commit intégré :** `47a01ad` → merge fork `1bda6a1`  
**Statut upstream :** [PR #1 ouverte](https://github.com/CL-ML/open-collider/pull/1) sur CL-ML

### Changements

- `src/open_collider/skill_interface.py` : génération de
  - `brainstorms/<session>/REPORT.html` — rapport agrégé multi-itérations
  - `iter_NNN/ITER_REPORT.html` — rapport par itération après curation
- Styles HTML embarqués, cartes idées, scores, domaines sources
- Tests API mode étendus pour valider la présence des fichiers HTML

### Impact Web UI

- Boutons **open HTML report** sur la page rapport session
- Bouton **iteration HTML report** après curation
- Endpoints `GET .../report.html` et `GET .../iterations/{n}/report.html`

---

## Upstream PR #2 — Sélection de provider API + skills Codex

**Auteur :** arsis-dev (`api-providers`)  
**Commit intégré :** `4c72204` → merge fork `c3e3afe`  
**Statut upstream :** [PR #2 ouverte](https://github.com/CL-ML/open-collider/pull/2) sur CL-ML

### Changements

| Fichier / dossier | Détail |
|-------------------|--------|
| `src/open_collider/llm/client.py` | Clients Anthropic, OpenAI Responses, Codex CLI ; préfixes `openai:` / `codex:` |
| `src/open_collider/brainstorm.py` | Routage provider depuis `project_config.yaml` |
| `src/open_collider/data/config.yaml` | Modèles par défaut multi-provider |
| `projects/_template/project_config.yaml` | Champ `llm_provider` documenté |
| `.agents/skills/open-collider-setup/` | Skill Codex équivalent `/collider_setup` |
| `.agents/skills/open-collider-brainstorm/` | Skill Codex équivalent `/brainstorm` + scripts |
| `.env.example` | Variables OpenAI / Codex |
| `README.md` | Section Codex, tableaux provider, config mixte |
| `tests/test_api_mode.py` | Couverture providers, token caps, HTML reports |

### Providers CLI / API mode

- **anthropic** — défaut historique
- **openai** — OpenAI Responses API
- **codex** — `codex exec` (expérimental, sans clé cloud)

La Web UI utilise sa propre couche settings (`demo` / `anthropic` / `openai-compatible`) ;
elle réutilise le même moteur Python et la même arborescence `projects/`.

---

## Upstream PR #3 — Dépendances PDF / reMarkable

**Auteur :** thomnico (`feat/add-rm-pdf-deps`)  
**Commit intégré :** `e6a6347` → merge fork `a6a118e`  
**Statut upstream :** [PR #3 ouverte](https://github.com/CL-ML/open-collider/pull/3) sur CL-ML

### Changements

- `pyproject.toml` : dépendances optionnelles de base
  - `pymupdf>=1.27.2.3`
  - `reportlab>=4.5.1`
  - `rmscene>=0.8.0`
- `uv.lock` mis à jour

### Usage

Pipeline contenu reMarkable / PDF (ex. projet `sealfie_marketing`) — **hors Web UI**,
mais installées par défaut avec `pip install -e .` sur ce fork.

---

## Ce qui n'a **pas** changé sur le repo original

- `CL-ML/open-collider` **main** : inchangé depuis mai 2026
- Aucun merge exécuté sur upstream (droits en lecture seule)
- PR #4 (Web UI vers upstream) : fermée, jamais mergée

---

## Commits de merge sur `main` (ordre)

```text
658edf6  Merge PR #1 fork — Web UI
1bda6a1  Merge upstream PR #1 — HTML reports
c3e3afe  Merge upstream PR #2 — API providers + Codex skills
a6a118e  Merge upstream PR #3 — PDF/reMarkable deps
```

---

## Prochaines étapes possibles

- Exposer le provider **Codex** dans la Web UI Settings (aujourd'hui CLI-only)
- i18n FR de l'interface (le manuel est déjà en français)
- Synchronisation périodique avec `CL-ML/open-collider` quand les PR upstream seront mergées officiellement
