# Shared Engineering Contract — SVAI Hackathon Implementation Plans

Every implementation plan MUST embed this contract verbatim-or-adapted in its own "Phase 0 — Setup"
and follow these conventions, so either teammate's Codex agent can execute any plan interchangeably.

## Audience for the plan document
The plan is executed by **Codex 5.6** (OpenAI's coding agent) from a cold start in an empty repo,
supervised by 2 human builders. Assume: skilled agent, zero context about this event, EverOS, or the
Snowflake account. The plan must be 100% self-contained — every command, every code interface, every
env var named exactly. Humans do only the steps marked **[HUMAN]** (account signups, secrets, demo
rehearsal). The plan should read as direct instructions to Codex ("Create file X containing…",
"Run Y, expect Z"), never as prose about what could be done.

## Phase 0 — Environment & accounts (common to all projects; target ≤ 30 min wall clock)
1. **[HUMAN] Snowflake trial**: signup.snowflake.com (choose AWS US region for widest Cortex model
   availability incl. claude models; $400 free credits, no card). Create a **Programmatic Access
   Token** (PAT) in Snowsight (Admin → Users → your user → Programmatic access tokens). PAT is used
   as the `password` field in the Python connector — do NOT set up key-pair auth or use plain
   password (MFA friction).
2. **[HUMAN] EverOS Cloud key**: sign up at https://everos.evermind.ai → create API key. (At the
   event, EverMind staff hand out credits — grab them.) We use the CLOUD SDK (`everos-cloud`), NOT
   the self-hosted `everos` package. Do not confuse the two.
3. Codex creates the project:
   - Python 3.12+, `uv venv` (or plain venv), deps:
     `uv pip install everos-cloud snowflake-connector-python streamlit fastapi uvicorn tiktoken jsonschema`
   - `.env` (git-ignored): `SNOWFLAKE_USER`, `SNOWFLAKE_PAT`, `SNOWFLAKE_ACCOUNT` (account locator),
     `SNOWFLAKE_WAREHOUSE=COMPUTE_WH`, `SNOWFLAKE_DATABASE=HACKDB`, `SNOWFLAKE_SCHEMA=PUBLIC`,
     `EVEROS_API_KEY`.
   - `snow.py` — one shared module: `get_conn()` (connector using PAT-as-password), `ai_complete(model,
     prompt, purpose, **params) -> (text, usage)` calling `AI_COMPLETE(model_parameters=...,
     show_details => TRUE)` via SQL, parsing token counts from the details, and ALWAYS inserting a row
     into `llm_call_log` before returning. This is the only path through which ANY LLM call happens.
   - `mem.py` — one shared module wrapping `everos_cloud.EverOS`: `remember(session_id, messages)`
     (= add + immediate `flush(session_id)` — NEVER skip flush, async extraction breaks live demos),
     `recall(query, user_id, top_k=10)`, `list_memories(kind, user_id)`, plus pass-throughs for
     `edit`/`delete`. All EverOS access goes through this module.
4. Bootstrap SQL (Codex runs once via `snow.py`):
   ```sql
   CREATE DATABASE IF NOT EXISTS HACKDB; USE DATABASE HACKDB;
   CREATE TABLE IF NOT EXISTS llm_call_log (
     call_id STRING DEFAULT UUID_STRING(), ts TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
     model STRING, purpose STRING, prompt_tokens INT, completion_tokens INT,
     latency_ms INT, credits_est FLOAT, user_id STRING, session_id STRING, extra VARIANT);
   ```
   Credits estimate per call: `tokens/1e6 * rate` with rates pinned in a `MODEL_RATES` dict
   (mistral-7b: 0.12, claude-haiku-4-5: ~0.35, openai-gpt-5-mini: 0.32, claude-sonnet-5: ~2.6,
   claude-opus class: ~12 credits/M tokens; $2.00/credit) — label as "published rates" in UI; also
   read `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY` (≈5-min lag — poll it, it makes
   cost data REAL; never the deprecated CORTEX_FUNCTIONS_USAGE_HISTORY).
5. Smoke test gate (must pass before any product code):
   `python smoke.py` → runs one `ai_complete('claude-haiku-4-5', 'say ok', 'smoke')`, one
   remember→recall round-trip, prints both. If claude models error as unavailable, enable
   cross-region (`ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';`) and fall back
   model order: claude-sonnet-5 → llama3.3-70b; small tier: claude-haiku-4-5 → openai-gpt-5-mini → mistral-7b.

## Conventions all plans follow
- **UI**: local Streamlit (NOT Streamlit-in-Snowflake), dark theme, giant number tickers
  (st.metric), auto-refresh (`st.rerun` loop or `st_autorefresh`), demo-day font sizes (readable
  from the back of a room). Keep to ≤ 2 screens; every screen has ONE headline number.
- **Determinism over live risk**: every demo has a `--replay` mode driven by seeded fixtures
  (scripted conversations/tasks in `fixtures/*.json`); live inference is the garnish, replay is the
  spine. Pre-warm EverOS memories before the demo; keep a `seed.py` that rebuilds all demo state
  from scratch in <2 min (the "wifi died, rebuild everything" button).
- **Honesty rules baked into UI copy**: measured numbers labeled "measured (Snowflake metering)";
  conventions/simulations labeled as such on-screen. Never a rigged baseline: baselines use the same
  model/quality bar, both arms logged in llm_call_log with different `purpose` tags.
- **Repo layout**: `snow.py`, `mem.py`, `app.py` (Streamlit), `seed.py`, `smoke.py`,
  `fixtures/`, product modules per plan. No tests beyond `smoke.py` + the plan's single
  `check_demo.py` end-to-end check (asserts the demo's headline numbers compute and the replay
  finishes) — hackathon, not production.
- **Two-person split**: each plan splits tasks into **Lane A** (data/backend: snow.py, product
  engine, fixtures) and **Lane B** (mem.py, Streamlit UI, demo script) with explicit interface
  handoffs so both Codex sessions run in parallel without merge conflicts (different files only).
- **Hour-by-hour schedule**: every plan maps its tasks onto the real clock (11:00 build start,
  12:00 lunch overlap, 16:00 HARD submission) with a "cut line" — features below the line are
  pre-designated sacrifices if behind at 14:30.
- **Demo script**: every plan ends with a timed 3-minute script (beat-by-beat, who says what, which
  screen is up, the one unforgettable moment marked) + a 30-second Q&A cheat sheet (the 3 hardest
  judge questions + honest answers).

## Codex R1 amendments (BINDING — override anything above where in conflict)
Source: Codex implementer review round 1 (codex-review-r1.md). Every plan must comply.

1. **EverOS version gate**: pin the exact tested `everos-cloud` 1.x version in requirements. EverOS
   1.x targets the v2 API — v1-only accounts return `403 VERSION_NOT_ALLOWED`. `smoke.py` must
   verify the key is v2-enabled and fail loudly with remediation text if not.
2. **dotenv**: add `python-dotenv` to deps; every entrypoint calls `load_dotenv()` first.
3. **Bootstrap order**: first connection is made WITHOUT database/schema (they don't exist yet);
   run `CREATE DATABASE` / `CREATE TABLE` as separate statements; then reconnect with
   `database=HACKDB, schema=PUBLIC`.
4. **`ai_complete()` full signature**: `ai_complete(model, prompt, purpose, run_id, user_id=None,
   session_id=None, agent_tag=None, extra=None) -> (text, usage)`. It sets a per-call
   `QUERY_TAG = f"{run_id}:{agent_tag or purpose}"` on the Snowflake session (this is how arms/
   agents/departments are attributed in ACCOUNT_USAGE) and logs all fields into `llm_call_log.extra`.
5. **Three cost tiers, labeled in every UI**: (a) *measured tokens* — from `show_details => TRUE`;
   (b) *estimated credits/$* — measured tokens × pinned rate table; (c) *billed credits* — from
   `CORTEX_AI_FUNCTIONS_USAGE_HISTORY`, which lags 2–5 min: it corroborates a prior run in a
   "receipts" panel and must NEVER drive a live ticker.
6. **Replay, defined**: a replay event = a captured record of a REAL prior run (prompt hash, model,
   output, usage, route/decision, grader result, timestamp, run_id) produced by a pre-show benchmark
   script (`benchmark.py`). Replay mode issues ZERO external calls and never inserts synthetic rows
   labeled as measured. Demos animate captured events + execute exactly ONE (or two) scripted live
   calls as the garnish. On-screen label: "measured pre-show run (replayed) + live call".
7. **Agent-mode memory path**: `mem.py` also exposes `remember_case(agent_id, session_id, messages)`
   (uses `add(..., mode="agent")`) and `recall_cases(query, agent_id, top_k)`. Plans that use
   agent-side learning (Broke, Allowance) MUST prove one agent-case add→flush→search round trip in
   Phase 0 smoke; the plan states an explicit fallback if extraction quality is poor (fingerprinted
   user-mode memories under a synthetic `user_id=f"agent:{name}"` — still EverOS retrieval).
8. **EverOS mutation semantics (hard API facts)**: there is NO per-memory-ID delete — `delete()` is
   scoped soft-delete by user/session/agent only; `edit()` operates on PROFILE items only, not
   episodes. Any "prune/demote/expire" mechanic is therefore an APPLICATION-LEVEL `active` flag
   (stored in Snowflake, filtering retrieved memory IDs at query time, with no backfill of the
   filtered slots), optionally followed by scoped session soft-delete. Search results DO expose
   memory IDs, originating session IDs, scores, and support `min_score` — use those for gates.
9. **Grader safety**: graders are `jsonschema.validate` + expected-value comparison, exact/normalized
   match against gold labels. NEVER `exec()` model output. No LLM-opinion grading on the critical
   path; if an LLM judge appears at all it is a secondary, disclosed, structured-output check.
10. **Session/identity discipline**: cross-session reveals must use same `user_id` + NEW
    `session_id` (otherwise you're demoing Streamlit state, not memory). Every fresh run uses a
    fresh `run_id`/`agent_id` namespace so `seed.py` can rebuild the world in <2 min.
11. **Safety-relevant facts** (allergies etc.): captured as explicitly confirmed structured data via
    profile `edit()`, never inferred from casual chat.

## Codex dry-run corrections (BINDING — verified against official docs during plan review)
12. **`AI_COMPLETE` response parsing**: with `show_details => TRUE` the function returns a serialized
    JSON string; `json.loads()` it, and the generated text lives at `choices[0]["messages"]` (NOT
    `["message"]["content"]`). Token counts are in the `usage` object. Smoke must assert nonzero
    measured tokens.
13. **`model_parameters` binding**: the Python connector cannot bind a Python dict — pass the
    options as a JSON string through `PARSE_JSON(%s)` (or inline SQL object syntax) in the SQL text.
    Anything inserted via `PARSE_JSON` must be `json.dumps()`-encoded, never `str(dict)`.
14. **EverOS client scoping**: construct the `EverOS` client with `app_id`/`project_id` defaults (or
    pass the identical scope to EVERY call — add/search/get/flush/edit/delete); mixed scopes silently
    break add→flush→search round trips. Normalize typed SDK responses (e.g. `.agent_cases`,
    `.profiles`/`.profile_data`) in ONE adapter function in `mem.py`; verify results originate from
    the expected session via each item's originating-session field.
15. **Fallback model names are full Cortex names** (e.g. `openai-gpt-5-mini`, never `gpt-5-mini`).

## Plan document format (per plan)
`# <Name> — Implementation Plan` → Goal (1 sentence) → Why this wins (3 bullets) → Architecture
(≤10 lines + ASCII diagram) → Phase 0 pointer (embed the contract steps) → Tasks (numbered; each
with: Files to create — exact paths; full interface signatures; key code sketches for the tricky
20%; acceptance check — exact command + expected output; lane assignment; time estimate) →
Hour-by-hour schedule with cut line → Fixtures spec (exact seeded content) → Demo script →
Risk table (top 5, each with trigger + fallback) → Q&A cheat sheet.
