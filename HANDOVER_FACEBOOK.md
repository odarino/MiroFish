# Handover — Add a Facebook platform to MiroFish

Audience: a fresh coding agent (Codex) finishing the Facebook feature. This doc
is self-contained; read it fully before touching code.

## 0. TL;DR

We are adding **Facebook** as a third simulated social platform alongside the
existing Twitter and Reddit. MiroFish simulates platforms via the **OASIS**
library (`camel-oasis`), which we forked to add the Facebook engine. The
**backend is done and Facebook is runnable via the HTTP API**. What remains:
the **frontend 3-platform UI**, a **friend-weighted feed algorithm**, **Facebook
interview over IPC**, and **runtime testing** (none of the backend has been run
with real LLM/Zep keys yet — only `py_compile` + import smoke).

## 1. Repos, branches, working copies

Two forks, both on branch **`feat/facebook`**, checked out side by side under
`~/Documents/projects/MiroFishVie/`:

```
MiroFishVie/
├── MiroFish/   origin=github.com/odarino/MiroFish   upstream=666ghj/MiroFish     [feat/facebook]
└── oasis/      origin=github.com/odarino/oasis        upstream=camel-ai/oasis      [feat/facebook, based on tag v0.2.5 = commit e97a1d8]
```

- MiroFish `backend/pyproject.toml` depends on the OASIS fork by git ref:
  `camel-oasis @ git+https://github.com/odarino/oasis.git@feat/facebook`
  (needs `[tool.hatch.metadata] allow-direct-references = true`).
- The backend venv currently has OASIS installed **editable** from `../../oasis`
  (`uv pip install -e ../../oasis`), so local edits to `oasis/` take effect
  immediately.

### CRITICAL gotchas
1. **`uv run` reverts the editable install** back to the pinned git commit
   (it re-syncs to `uv.lock`). When testing local OASIS edits, invoke
   **`backend/.venv/bin/python`** directly, or `uv run --no-sync`. After any
   `uv run`, re-run `uv pip install -e ../../oasis`.
2. After changing the OASIS fork, either keep the editable install (dev) or
   `cd backend && uv lock && uv sync` to re-pin the new commit (prod/Docker).
3. OASIS `ActionType` / recsys / agent tools are **hardcoded enums + lists**
   (no plugin API) — every new action needs edits in 3 OASIS files (see §3).

## 2. What is DONE (do not redo)

### OASIS fork (`odarino/oasis@feat/facebook`)
- `oasis/social_platform/typing.py`: `ActionType.{SEND_FRIEND_REQUEST,
  ACCEPT_FRIEND_REQUEST, UNFRIEND, REACT_POST}`, `RecsysType.FACEBOOK`,
  `DefaultPlatformType.FACEBOOK`, `ActionType.get_default_facebook_actions()`.
- `oasis/social_platform/schema/{friendship,reaction}.sql` + registered in
  `database.py` (`create_db` + `TABLE_NAMES`).
- `oasis/social_platform/platform.py`: handlers `send_friend_request`,
  `accept_friend_request`, `unfriend`, `react_post`; `FACEBOOK` branch in
  `update_rec_table`.
- `oasis/social_platform/recsys.py`: `rec_sys_facebook()` — **STUB** that
  delegates to trace-based recsys (builds a friend adjacency map but does not
  yet use it). This is remaining task R2.
- `oasis/social_agent/agent_action.py`: `SocialAction` methods + registered in
  `get_openai_function_list()`.
- `oasis/social_agent/agents_generator.py`: `generate_facebook_agent_graph()`
  (reads reddit-style JSON: `username/bio/persona` + optional
  `mbti/gender/age/country`).
- `oasis/social_platform/config/user.py`: `to_facebook_system_message()`.
- Exported from `oasis/social_agent/__init__.py` and top-level `oasis/__init__.py`.
- Verified: import, system-message render, 2-agent graph build, `create_db`
  produces the new tables, `getattr(Platform, action.value)` resolves.

### MiroFish backend (`odarino/MiroFish@feat/facebook`)
- **`backend/app/platform_registry.py`** — single source of truth. `PlatformSpec`
  per platform (`name, label, oasis_platform_type, recsys_type, profile_format,
  profile_filename, db_filename, graph_generator, actions, use_boost,
  enabled_by_default`). Helpers: `all_platforms()`, `platform_names()`,
  `get_platform(name)`, `enabled_platforms()`, `resolve_actions(name)`,
  and module constants `TWITTER_ACTIONS/REDDIT_ACTIONS/FACEBOOK_ACTIONS`.
  **Placed OUTSIDE `services/`** to avoid a circular import
  (`config` → `services/__init__` → `oasis_profile_generator` → `config`).
  Facebook has `enabled_by_default=False`.
- `config.py`: `OASIS_*_ACTIONS` sourced from the registry.
- `services/oasis_profile_generator.py`: `to_facebook_format()` (= reddit JSON);
  `save_profiles()` is now format-driven via the registry.
- `scripts/run_parallel_simulation.py`: the two near-identical runners were
  unified into `run_platform_simulation(platform_name, ...)` (registry-driven);
  `run_reddit_simulation`/`run_facebook_simulation` are thin wrappers;
  `run_twitter_simulation` left as-is on purpose (CSV + bespoke initial-posts).
  Added `--facebook-only` and Facebook env close.
- `scripts/action_logger.py`: `SimulationLogManager.get_facebook_logger()`.
- `services/simulation_runner.py`: `facebook_*` state fields; `add_action`,
  completion, round/hours tracking and `_check_all_platforms_completed`
  generalized to `getattr`/registry iteration; monitor loops
  `platform_names()`; `start(platform="facebook")` launches
  `run_parallel_simulation.py --facebook-only`; `get_actions` reads
  `facebook/actions.jsonl`; cleanup dirs from the registry.
- `services/simulation_config_generator.py`: `enable_facebook` + `facebook_config`.
- `services/simulation_manager.py`: `enable_facebook` through `SimulationState`;
  generates `facebook_profiles.json`; passes `enable_facebook` to config gen.
- `api/simulation.py`: `create` accepts `enable_facebook`; `start` accepts
  `platform="facebook"`; readiness check requires `state.json` +
  `simulation_config.json` + **at least one** registry profile file (no longer
  hardcodes twitter+reddit); profiles endpoint resolves filename/format from
  the registry.
- All backend changes pass `py_compile` and an import smoke test. **Not yet run
  with real keys.**

Relevant commits (MiroFish): `0fb3c58` registry, `caeffb3` runner unify,
`c7bb038` runner monitoring, `155c6e5` API/manager. (OASIS): `2a51c92` platform
scaffold, `26dff12` generator + prompt.

## 3. Mental model you must keep

- **OASIS is a simulator, not a client.** It builds a local SQLite fake network;
  it never calls real X/Reddit/Facebook. "Adding a platform" = modeling its
  mechanics (recsys + action space + schema), not integrating an API.
- **MiroFish ↔ OASIS boundary is a subprocess + files.** `simulation_runner`
  spawns `scripts/run_parallel_simulation.py` and communicates via a config
  JSON in, and `{platform}_simulation.db` + `{platform}/actions.jsonl` + IPC
  files out. The Flask app does NOT import `oasis`; only the scripts do.
- **The registry (`app/platform_registry.py`) is the single source of truth.**
  Prefer iterating it over adding `if facebook` branches.

## 4. REMAINING TASKS

### R1 — Frontend 3-platform UI  (biggest; needs the running app)
Vue 3 + Vite in `frontend/`. The dual-platform (twitter/reddit) layout is
hardcoded, especially side-by-side panels.
- Entry point: `src/components/Step1GraphBuild.vue` sends
  `{ enable_twitter:true, enable_reddit:true }` (~line 226). Add an
  `enable_facebook` toggle (default off).
- Platform panels/tabs: `src/components/Step2EnvSetup.vue`,
  `Step3Simulation.vue` (~49 twitter/reddit refs — the live dual-panel view),
  `Step4Report.vue`, `Step5Interaction.vue`. Generalize the two-panel layout to
  render one panel per **enabled** platform (drive from the registry data the
  API already returns in run-state: `*_running/*_completed/*_actions_count/
  *_current_round`, now including `facebook_*`).
- `src/api/simulation.js`: thread `enable_facebook` and `platform:"facebook"`.
- The run trigger must call start with the right `platform`. Today single vs
  parallel is chosen in the UI; decide how Facebook is launched
  (`platform:"facebook"` single-mode is already supported end-to-end).
- **How to build/verify:** `npm run dev` (frontend :3000, backend :5001). Use a
  browser/Playwright to drive Step1→Step3 with Facebook enabled and confirm the
  Facebook panel renders and updates. Do NOT ship blind — this is why it was
  left for a run-capable session.
- Acceptance: a user can enable Facebook in Step1, prepare, run, and watch the
  Facebook feed/actions update live without breaking the twitter/reddit view.

### R2 — Friend-weighted `rec_sys_facebook`  (OASIS fork)
File `oasis/social_platform/recsys.py`, function `rec_sys_facebook` (currently a
stub). Implement an EdgeRank-like feed: score each candidate post per viewer by
`affinity(viewer, author) × interaction_weight × time_decay`, strongly upranking
posts by/reacted-to-by the viewer's **accepted** friends (adjacency already built
from `friendship_table`). Fall back to trace-based for friendless users. Mirror
the return shape of the other `rec_sys_*` (a `new_rec_matrix: List[List[int]]`).
Also consider maintaining denormalized counters (post reactions) if ranking needs
them — see TODOs in `platform.py` `react_post`/`accept_friend_request`.
- Verify: unit-drive `rec_sys_facebook` with synthetic user/post/trace/friendship
  tables via `backend/.venv/bin/python` (not `uv run`).

### R3 — Facebook interview over IPC  (MiroFish script)
`scripts/run_parallel_simulation.py` `ParallelIPCHandler` only wires
`twitter_env`/`reddit_env`. Add a `facebook_env`/`facebook_agent_graph` slot so
`INTERVIEW` works for Facebook; `_get_interview_result` reads
`facebook_simulation.db`. Then check `services/report_agent.py` /
`services/zep_tools.py` interview paths and `simulation_runner` interview
helpers (they enumerate `["twitter","reddit"]` — generalize to registry).

### R4 — Runtime test the whole Facebook path (do this FIRST)
Nothing backend has run with real keys. Before R1–R3, validate the happy path:
1. `backend/.env` with `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL_NAME`, `ZEP_API_KEY`.
2. Ensure editable OASIS: `cd backend && uv pip install -e ../../oasis`.
3. Build a graph (existing flow) to get a `graph_id`.
4. `POST /api/simulation/create {project_id, graph_id, enable_twitter:false,
   enable_reddit:false, enable_facebook:true}` → prepare (existing prepare flow
   must produce `facebook_profiles.json` + `simulation_config.json`) →
   `POST /api/simulation/<id>/start {platform:"facebook", max_rounds:5}`.
5. Confirm `facebook_simulation.db` + `facebook/actions.jsonl` appear and the
   run-state `facebook_*` fields advance; check agents actually call the new
   actions (react_post / friend requests) in `trace`.
Fix whatever breaks (most likely: profile field mismatches into
`generate_facebook_agent_graph`, or the agent tool schema). Keep changes
additive and registry-driven.

## 5. Conventions
- Follow existing file style (Chinese comments are the norm in this codebase;
  match them). Keep changes additive; prefer registry iteration over new
  `if platform==` branches.
- OASIS edits: keep them localized/appended so upstream rebases stay clean
  (append enum members, add methods, add `elif` branches).
- Commit messages end with the repo's existing trailer style. Push to
  `feat/facebook` on the respective fork. Do not touch `main`.
- Verify with `backend/.venv/bin/python -m py_compile <file>` and targeted
  scripts run via `backend/.venv/bin/python` (never `uv run` while editable).

## 6. Quick file index
- Registry: `backend/app/platform_registry.py`
- Runner (subprocess launcher + monitor + state): `backend/app/services/simulation_runner.py`
- Sim script (the actual OASIS loop): `backend/scripts/run_parallel_simulation.py`
- Profiles: `backend/app/services/oasis_profile_generator.py`
- Config gen: `backend/app/services/simulation_config_generator.py`
- Orchestration: `backend/app/services/simulation_manager.py`
- HTTP API: `backend/app/api/simulation.py`
- OASIS platform core: `oasis/oasis/social_platform/{typing,platform,database,recsys}.py`,
  `schema/*.sql`
- OASIS agent side: `oasis/oasis/social_agent/{agent_action,agents_generator}.py`,
  `social_platform/config/user.py`
- Frontend: `frontend/src/components/Step{1..5}*.vue`, `frontend/src/api/simulation.js`
