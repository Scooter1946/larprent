# Rent — Implementation Plan

## Goal
Build a Snowflake-backed context-margin ledger where every retrieved bundle pays rent for its context seat (tokenizer-estimated per-bundle allocation of the measured request totals) and earns only when it is the supporting evidence behind a correctly-answered question, prune the bundles that run negative (real `active=false`, no backfill, no per-memory EverOS delete), and prove on stage — via a genuinely zero-call replay mode plus one live query — that the fixed 8-question answer set holds at a lower measured cost per query.

## Why this wins
- Real P&L, not a rigged one: request-level token totals are measured (show_details); each bundle's rent is its tokenizer-estimated share of that measured context; its earnings come only from questions it actually supported correctly. Decoys structurally run negative — "not paying rent" is literally true in the ledger, not a narrative gloss.
- The prune mechanic is API-honest and TRUE no-backfill: context seats are frozen by rank before the active filter runs, so a pruned seat is provably empty, never quietly replaced by the next-ranked bundle.
- "Context is capital" closes both prize tracks (Track 3 wildcard + UpScaleX bounty) with a genuine zero-external-call `--replay` mode driving the entire app — the outage fallback and the stage safety net are the same code path.

## Architecture
Twelve fixture bundles (literal text, final wording) seed twelve EverOS sessions under one Acme user; a Snowflake registry maps each `session_id` to a `bundle_id` and holds the only mutable state (`active`). `benchmark.py` runs BOTH arms (naive full-history, memory top-k, true no-backfill) for all 8 questions, logging measured request-level token totals, tokenizer-estimated per-bundle footprints, and paired-arm savings to Snowflake. An attribution query turns those logs into per-bundle RENT (tokens it occupied × rate), EARNED (savings attributed only when it was correct+supporting evidence), and NET (earned − rent) — negative rows are real. The Streamlit leaderboard reads the ledger; PRUNE flips `active=false` for real (SQL only, zero LLM calls). The 8-question regression is captured pre-show for both registry states and replayed on stage; one extra question runs live. A sidebar toggle switches the ENTIRE app (leaderboard, candidates, regression, PRUNE) to a pure-local replay mode driven only by captured JSON — zero external calls, the same code path used if Snowflake/EverOS goes down mid-demo.

```
fixtures/rent_world.json (12 bundles, literal text, 8 Qs, gold answers, support map)
            |
            v
         seed.py  (idempotent: scoped delete + re-add per bundle)
            +----------------> EverOS sessions (12, one per bundle, user_id="acme:support")
            |                          session_id
            v                             v
   bundle_registry (Snowflake) <----------+   session_id <-> bundle_id, active flag
            v
   benchmark.py -- PAIRED ARMS, per question, same model (claude-haiku-4-5)
      naive arm (full history, 8K-capped)   |   memory arm (bundles.recall_bundles, TRUE no-backfill)
            +---------------------+---------+
                                   v
     llm_call_log . eval_results . retrieval_log (+bundle_tokens)   (Snowflake, measured, show_details)
                                   v
              rent_ledger  (rent = tokens occupied x rate; earn = savings, supporting+correct only)
                                   v
                    leaderboard UI (Streamlit app.py) -- live Snowflake OR local --replay JSON
       ranked NET $ | red "not paying rent" (negative net) | idle column (zero/zero)
                                   v
                     [human clicks PRUNE, on stage]
        bundle_registry.active = FALSE for prune-eligible bundle_ids  (live mode: real SQL)
              (seats frozen by rank BEFORE active filter; no backfill; no EverOS per-memory delete)
                                   v
          benchmark.py --phase post_prune   (already run + captured PRE-SHOW)
                                   v
     captures/replay_post_prune.json --> 8 checks REPLAYED on stage + ONE live/replayed query
```

## Phase 0 — Environment & accounts (embedded from SHARED-CONTRACT.md, closes review items 6 & 10; target ≤ 40 min)

Run before any Rent-specific file exists, both lanes together.

1. **[HUMAN]** Snowflake trial: signup.snowflake.com, AWS US region. $400 free credits, no card. Create a **Programmatic Access Token** (PAT) in Snowsight (Admin → Users → your user → Programmatic access tokens) — it drops in as the connector `password`. No key-pair, no plain password.
2. **[HUMAN]** EverOS Cloud key: sign up at https://everos.evermind.ai → create an API key. Use the CLOUD SDK (`everos-cloud`), not the self-hosted `everos` package.
3. Codex creates the project skeleton and captures the EXACT tested pin (a version range is not sufficient — the contract requires the exact resolved version in requirements):
   ```bash
   uv venv && source .venv/bin/activate
   uv pip install "everos-cloud>=1.0,<2.0" snowflake-connector-python streamlit streamlit-autorefresh \
                   tiktoken jsonschema python-dotenv
   uv pip freeze | grep -iE "^(everos-cloud|snowflake-connector-python|streamlit|streamlit-autorefresh|tiktoken|jsonschema|python-dotenv)==" > requirements.txt
   # ^ ALL direct deps, exact resolved versions — not just everos-cloud; `>` (not `>>`) so reruns don't append stale duplicates
   ```
   From this point on, `requirements.txt` is the tested pin — any rebuild uses `uv pip install -r requirements.txt`, never the open range again. (No FastAPI/uvicorn — Streamlit talks to `snow.py`/`mem.py` directly, no REST layer needed for this plan.)
   `.env` (git-ignored): `SNOWFLAKE_USER`, `SNOWFLAKE_PAT`, `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_WAREHOUSE=COMPUTE_WH`, `SNOWFLAKE_DATABASE=HACKDB`, `SNOWFLAKE_SCHEMA=PUBLIC`, `EVEROS_API_KEY`. Every entrypoint (`bootstrap.py`, `seed.py`, `benchmark.py`, `app.py`, `smoke.py`, `check_demo.py`, `reset_prune.py`) starts with `from dotenv import load_dotenv; load_dotenv()` as the FIRST lines — no exceptions.
4. `bootstrap.py` (run ONCE, explicit two-step connection order — the binding sequence is: raw connection with NO database/schema → separate `CREATE DATABASE` → reconnect WITH database/schema → separate `CREATE TABLE` statements):
   ```python
   from dotenv import load_dotenv; load_dotenv()
   import os, snowflake.connector
   # Step A: raw connection, database/schema do NOT exist yet
   conn = snowflake.connector.connect(user=os.environ["SNOWFLAKE_USER"], password=os.environ["SNOWFLAKE_PAT"],
                                       account=os.environ["SNOWFLAKE_ACCOUNT"], warehouse="COMPUTE_WH")
   conn.cursor().execute("CREATE DATABASE IF NOT EXISTS HACKDB")
   conn.close()
   # Step B: reconnect WITH database/schema now that they exist
   conn = snowflake.connector.connect(user=os.environ["SNOWFLAKE_USER"], password=os.environ["SNOWFLAKE_PAT"],
                                       account=os.environ["SNOWFLAKE_ACCOUNT"], warehouse="COMPUTE_WH",
                                       database="HACKDB", schema="PUBLIC")
   conn.cursor().execute("CREATE SCHEMA IF NOT EXISTS PUBLIC")
   conn.cursor().execute("""CREATE TABLE IF NOT EXISTS llm_call_log (
     call_id STRING DEFAULT UUID_STRING(), ts TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
     model STRING, purpose STRING, prompt_tokens INT, completion_tokens INT,
     latency_ms INT, credits_est FLOAT, user_id STRING, session_id STRING, extra VARIANT)""")
   conn.close()
   ```
5. `snow.py` (shared module — EVERY script after `bootstrap.py` uses `get_conn()`, which always connects WITH `database="HACKDB", schema="PUBLIC"` since bootstrap already created them):
   - `MODEL_RATES = {"mistral-7b": 0.12, "claude-haiku-4-5": 0.35, "openai-gpt-5-mini": 0.32, "claude-sonnet-5": 2.6, "claude-opus-class": 12.0}` (credits/M tokens); `USD_PER_CREDIT = 2.00`.
   - `ai_complete(model, prompt, purpose, run_id, user_id=None, session_id=None, agent_tag=None, model_parameters=None, extra=None) -> (text: str, usage: dict)` — exact executable sketch:
     ```python
     import json
     def ai_complete(model, prompt, purpose, run_id, user_id=None, session_id=None, agent_tag=None,
                      model_parameters=None, extra=None):
         conn = get_conn(); cur = conn.cursor()
         cur.execute("ALTER SESSION SET QUERY_TAG = %s", (f"{run_id}:{agent_tag or purpose}",))
         cur.execute("SELECT AI_COMPLETE(model => %(model)s, prompt => %(prompt)s, "
                     "model_parameters => PARSE_JSON(%(mp)s), show_details => TRUE) AS resp",
                     {"model": model, "prompt": prompt, "mp": json.dumps(model_parameters or {})})
         raw = cur.fetchone()[0]
         resp = json.loads(raw) if isinstance(raw, str) else raw
         # CONFIRM exact field names against your account's live response in the Phase 0 smoke test —
         # print(resp) once before trusting this. Expected shape per Snowflake docs:
         # resp["choices"][0]["messages"] (text), resp["usage"]["prompt_tokens"]/["completion_tokens"].
         text = resp["choices"][0]["messages"]
         usage = {"prompt_tokens": resp["usage"]["prompt_tokens"],
                   "completion_tokens": resp["usage"]["completion_tokens"]}
         cur.execute("INSERT INTO llm_call_log (model, purpose, prompt_tokens, completion_tokens, "
                     "credits_est, user_id, session_id, extra) VALUES (%s,%s,%s,%s,%s,%s,%s,PARSE_JSON(%s))",
                     (model, purpose, usage["prompt_tokens"], usage["completion_tokens"],
                      (usage["prompt_tokens"]+usage["completion_tokens"])/1e6*MODEL_RATES[model],
                      user_id, session_id, json.dumps({"run_id": run_id, "agent_tag": agent_tag, **(extra or {})})))
         conn.commit()
         return text, usage
     ```
   - Label every derived dollar in the UI "estimated prompt-input cost — measured tokens × published rate." Rent only counts PROMPT (input) tokens by design (pinned in the settled spec) even though Snowflake bills both directions — this is a deliberate accounting convention, state it on-slide, never silently mix in completion tokens.
   - Three cost tiers, all shown: (a) measured tokens from `show_details`; (b) estimated $ = measured × `MODEL_RATES`; (c) billed credits from `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY` filtered by `query_tag LIKE 'rent-%'`, labeled "billed credits (Snowflake metering, ~5 min lag) — corroborates a prior run, never drives the live ticker" (Task 8's receipts panel).
6. `mem.py` (shared module wrapping `everos_cloud.EverOS`; closes contract's binding "Codex dry-run corrections" items 12 & 14 — EverOS client scoping and one typed-response adapter):
   - Client constructed ONCE, module-level, with FIXED scope defaults: `client = EverOS(api_key=os.environ["EVEROS_API_KEY"], app_id="rent", project_id="rent")`. Every add/search/get/flush/edit/delete call in this module reuses this same client — mixed `app_id`/`project_id` scopes across calls silently break add→flush→search round trips (binding correction), so no function below ever constructs a second client or overrides the scope.
   - `_normalize_episode(ep) -> dict`: the ONE adapter function that normalizes a typed SDK episode into a plain dict `{"session_id": ep.session_id, "score": ep.score, "content": ep.content}` and asserts `ep.session_id` is present (`assert getattr(ep, "session_id", None), "episode missing originating-session field"`) — this is where "verify results originate from the expected session" happens, in one place, so every caller downstream works with plain dicts, never the raw SDK type.
   - `remember(session_id, messages) -> None` = `client.add(...)` immediately followed by `client.flush(session_id)` — NEVER skip flush.
   - `recall(query, user_id, top_k=10) -> list[dict]` = `client.search(query, user_id=user_id, top_k=top_k, method="hybrid")`, then `[_normalize_episode(ep) for ep in result.episodes]` — returns normalized dicts, NOT the raw `SearchResult`; callers (Task 4's `bundles.py`) index `ep["session_id"]`/`ep["score"]`, never `.session_id`/`.score`.
   - `delete(user_id, session_id) -> None` = `client.delete(user_id=user_id, session_id=session_id)` pass-through (scoped soft-delete — used by `seed.py` for idempotent reseeding, see Task 5).
   - **Rent-specific check (once)**: after one `remember()`, `hits = recall(...)`, `print(hits[0])` to confirm the normalized shape `{'session_id':..., 'score':..., 'content':...}` — this replaces inspecting raw SDK attributes, since `_normalize_episode` already did that translation.
7. Smoke gate (must pass before ANY product code): `python smoke.py` runs one `ai_complete('claude-haiku-4-5', 'say ok', 'smoke', run_id='smoke')` and asserts `usage["prompt_tokens"] > 0` (nonzero measured tokens — per the contract's binding correction, a zero here means `show_details` parsing is broken, not a valid smoke pass; print the raw `resp` once per step 5's note if it fails) plus one `remember`→`flush`→`recall` round trip asserting the returned list is non-empty. Claude unavailable → run `ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';`; if still unavailable, change `MODEL = "openai-gpt-5-mini"` in `benchmark.py` (Task 6) — a one-line constant change, not a code path — and re-run this smoke gate. `403 VERSION_NOT_ALLOWED` → key needs v2 enablement, fix before continuing.

## Tasks

Files/interfaces/lane/time for every task; Tasks 3, 4, 6 are the "tricky 20%" and are fully sketched. Corrected dependency order: **fixtures → schema → ledger.py → bundles.py → seed.py → benchmark.py → calibrate/prune → UI**. Lane A = Snowflake/backend/fixtures; Lane B = Streamlit UI/demo PLUS one cross-lane assist (Task 4) to make the schedule fit — see Hour-by-hour schedule for why. Different files only, no merge conflicts.

---

### Task 1 — Fixture world
**Lane A · 20 min** · **Files**: `fixtures/rent_world.json`, `rent_fixtures.py`

Transcribe the LITERAL `bundles` and `questions` JSON given verbatim in **Fixtures spec** below into `fixtures/rent_world.json` — do not paraphrase, do not invent wording, the text there is final. `rent_fixtures.py`:
```python
import json, re
USER_ID = "acme:support"

def load_world(path: str = "fixtures/rent_world.json") -> dict: ...

def normalize(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s).replace(",", "")
    s = re.sub(r"\$\s+", "$", s)
    return re.sub(r"\s+%", "%", s)
```
**Acceptance**: `python -c "from rent_fixtures import load_world as L; w=L(); assert len(w['bundles'])==12 and len(w['questions'])==8; print('ok',len(w['bundles']),len(w['questions']))"` → `ok 12 8`.

---

### Task 2 — Rent schema bootstrap
**Lane A · 20 min** · **Files**: `rent_schema.sql`, run via `bootstrap_rent.py` (executes each `CREATE TABLE` as its own `cur.execute()` call — the connector does not run multi-statement strings by default)

```sql
CREATE TABLE IF NOT EXISTS bundle_registry (
  bundle_id STRING PRIMARY KEY, session_id STRING NOT NULL, title STRING, category STRING,
  is_idle BOOLEAN DEFAULT FALSE, active BOOLEAN DEFAULT TRUE,
  created_ts TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(), pruned_ts TIMESTAMP_LTZ);

CREATE TABLE IF NOT EXISTS fixture_support_map (question_id STRING, bundle_id STRING);

CREATE TABLE IF NOT EXISTS eval_results (
  result_id STRING DEFAULT UUID_STRING(), run_id STRING, phase STRING, arm STRING,
  question_id STRING, model STRING, prompt_hash STRING, model_answer STRING, gold_answer STRING,
  is_correct BOOLEAN, prompt_tokens INT, completion_tokens INT, context_bundle_ids VARIANT,
  ts TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP());

CREATE TABLE IF NOT EXISTS retrieval_log (
  retrieval_id STRING DEFAULT UUID_STRING(), run_id STRING, phase STRING, question_id STRING,
  bundle_id STRING, score FLOAT, rank INT, bundle_tokens INT, arm STRING DEFAULT 'memory',
  ts TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP());

CREATE TABLE IF NOT EXISTS rent_ledger (
  ledger_id STRING DEFAULT UUID_STRING(), run_id STRING, phase STRING, bundle_id STRING,
  question_id STRING, arm STRING, retrieved_rank INT, n_bundles_in_context INT, bundle_tokens INT,
  naive_prompt_tokens INT, memory_prompt_tokens INT, tokens_saved_for_question INT,
  is_correct BOOLEAN, is_supporting BOOLEAN, n_supporting_retrieved INT,
  rent_dollars FLOAT, earned_dollars FLOAT, net_dollars FLOAT,
  ts TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP());
```
**Acceptance**: `SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='PUBLIC' AND TABLE_NAME IN ('BUNDLE_REGISTRY','FIXTURE_SUPPORT_MAP','EVAL_RESULTS','RETRIEVAL_LOG','RENT_LEDGER');` → `5`.

---

### Task 3 — `ledger.py`: insert/query layer + rent/earn/net attribution SQL
**Lane A · 45 min — TRICKY 20%, fully sketched** · **Files**: `ledger.py`. Built BEFORE `benchmark.py` (Task 6) so nothing imports a nonexistent module.

**Ledger math (pinned, replaces the earlier even-split-everything convention):** every bundle retrieved into a question's memory-arm context pays RENT = the tokenizer-estimated (`cl100k_base`, via `tiktoken`) token count of ITS OWN formatted block in that prompt × published rate — an ESTIMATE of that bundle's share of the prompt, not the exact Claude-tokenizer count (AI_COMPLETE's `show_details` measures request-level totals only; it does not expose a per-snippet breakdown). A bundle EARNS on a question only if it is in that question's supporting-evidence set AND the memory arm answered correctly; earnings = that question's paired-arm token savings (`naive_prompt_tokens − memory_prompt_tokens` — these ARE measured request-level totals, from `show_details`), split evenly across however many supporting bundles were retrieved for it (in this fixture that is always exactly one, so earnings go wholly to the one bundle that actually answered the question). NET = earned − rent. Consequence: decoys pay rent every time they're retrieved and never earn — genuinely negative net. Idle bundles are retrieved zero times — zero rent, zero earnings, net zero. The PRUNE RULE is unchanged: retrieved ≥2 times AND never correct+supporting. Two distinct labels, never conflated: the request-level `naive_prompt_tokens`/`memory_prompt_tokens` (and therefore `tokens_saved_for_question`, `earned_dollars`) are MEASURED; the per-bundle `bundle_tokens`/`rent_dollars` allocation is TOKENIZER-ESTIMATED.

```python
from snow import get_conn, MODEL_RATES, USD_PER_CREDIT

def clear_run(run_id: str, phase: str) -> None:
    """Idempotency: delete any prior rows for this exact (run_id, phase) before reinserting —
    reruns of the same run_id/phase never duplicate or cross-multiply rows."""
    conn = get_conn(); cur = conn.cursor()
    for table in ("eval_results", "retrieval_log", "rent_ledger"):
        cur.execute(f"DELETE FROM {table} WHERE run_id=%(run_id)s AND phase=%(phase)s",
                    {"run_id": run_id, "phase": phase})
    conn.commit()

def insert_eval_result(**row) -> None:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""INSERT INTO eval_results (run_id, phase, arm, question_id, model, prompt_hash,
        model_answer, gold_answer, is_correct, prompt_tokens, completion_tokens, context_bundle_ids)
        VALUES (%(run_id)s,%(phase)s,%(arm)s,%(question_id)s,%(model)s,%(prompt_hash)s,
        %(model_answer)s,%(gold_answer)s,%(is_correct)s,%(prompt_tokens)s,%(completion_tokens)s,
        PARSE_JSON(%(cbi_json)s))""",
        {**row, "cbi_json": __import__("json").dumps(row["context_bundle_ids"])})
    conn.commit()

def insert_retrieval_log(run_id: str, phase: str, question_id: str, ranked_bundles: list[dict],
                          bundle_tokens: dict[str, int]) -> None:
    conn = get_conn(); cur = conn.cursor()
    for b in ranked_bundles:
        cur.execute("""INSERT INTO retrieval_log (run_id, phase, question_id, bundle_id, score,
            rank, bundle_tokens) VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (run_id, phase, question_id, b["bundle_id"], b["score"], b["rank"],
             bundle_tokens[b["bundle_id"]]))
    conn.commit()

ATTRIBUTION_SQL = """
INSERT INTO rent_ledger
(run_id, phase, bundle_id, question_id, arm, retrieved_rank, n_bundles_in_context, bundle_tokens,
 naive_prompt_tokens, memory_prompt_tokens, tokens_saved_for_question, is_correct, is_supporting,
 n_supporting_retrieved, rent_dollars, earned_dollars, net_dollars)
WITH naive AS (
  SELECT question_id, prompt_tokens AS naive_prompt_tokens FROM eval_results
  WHERE run_id=%(run_id)s AND phase=%(phase)s AND arm='naive'),
mem AS (
  SELECT question_id, prompt_tokens AS memory_prompt_tokens, is_correct FROM eval_results
  WHERE run_id=%(run_id)s AND phase=%(phase)s AND arm='memory'),
per_question AS (
  SELECT m.question_id, n.naive_prompt_tokens, m.memory_prompt_tokens,
         (n.naive_prompt_tokens - m.memory_prompt_tokens) AS tokens_saved_for_question, m.is_correct
  FROM mem m JOIN naive n ON m.question_id = n.question_id),
retrieved AS (
  SELECT r.question_id, r.bundle_id, r.rank, r.bundle_tokens,
         COUNT(*) OVER (PARTITION BY r.question_id) AS n_bundles_in_context
  FROM retrieval_log r WHERE r.run_id=%(run_id)s AND r.phase=%(phase)s AND r.arm='memory'),
supporting AS (SELECT DISTINCT question_id, bundle_id FROM fixture_support_map),
supporting_retrieved AS (
  SELECT retrieved.question_id, COUNT(*) AS n_supporting_retrieved
  FROM retrieved JOIN supporting
    ON supporting.question_id = retrieved.question_id AND supporting.bundle_id = retrieved.bundle_id
  GROUP BY retrieved.question_id)
SELECT %(run_id)s, %(phase)s, retrieved.bundle_id, retrieved.question_id, 'memory',
  retrieved.rank, retrieved.n_bundles_in_context, retrieved.bundle_tokens,
  per_question.naive_prompt_tokens, per_question.memory_prompt_tokens,
  per_question.tokens_saved_for_question, per_question.is_correct,
  (supporting.bundle_id IS NOT NULL) AS is_supporting,
  COALESCE(sr.n_supporting_retrieved, 0) AS n_supporting_retrieved,
  retrieved.bundle_tokens / 1000000.0 * %(rate)s * %(usd_per_credit)s AS rent_dollars,
  CASE WHEN supporting.bundle_id IS NOT NULL AND per_question.is_correct AND sr.n_supporting_retrieved > 0
       THEN (per_question.tokens_saved_for_question / sr.n_supporting_retrieved) / 1000000.0 * %(rate)s * %(usd_per_credit)s
       ELSE 0 END AS earned_dollars,
  (CASE WHEN supporting.bundle_id IS NOT NULL AND per_question.is_correct AND sr.n_supporting_retrieved > 0
       THEN (per_question.tokens_saved_for_question / sr.n_supporting_retrieved) / 1000000.0 * %(rate)s * %(usd_per_credit)s
       ELSE 0 END) - (retrieved.bundle_tokens / 1000000.0 * %(rate)s * %(usd_per_credit)s) AS net_dollars
FROM retrieved
JOIN per_question ON retrieved.question_id = per_question.question_id
LEFT JOIN supporting ON supporting.question_id = retrieved.question_id AND supporting.bundle_id = retrieved.bundle_id
LEFT JOIN supporting_retrieved sr ON sr.question_id = retrieved.question_id;
"""

def run_attribution_sql(run_id: str, phase: str, model: str = "claude-haiku-4-5") -> None:
    cur = get_conn().cursor()
    cur.execute(ATTRIBUTION_SQL, {"run_id": run_id, "phase": phase,
                                   "rate": MODEL_RATES[model], "usd_per_credit": USD_PER_CREDIT})
    cur.connection.commit()

def _rows_as_dicts(cur) -> list[dict]:
    """Shared column-name-lowercasing helper — every query function below routes through this so
    live rows and (Task 9's) replay rows can be built to the exact same normalized key set."""
    cols = [c[0].lower() for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]

# LEADERBOARD ROW SCHEMA (normalized, shared by live rows here AND Task 9's compute_local_ledger):
# {bundle_id, title, category, is_idle, active, total_earned, total_rent, total_net, times_retrieved}
def get_leaderboard(run_id: str, phase: str) -> list[dict]:
    cur = get_conn().cursor()
    cur.execute("""SELECT b.bundle_id, b.title, b.category, b.is_idle, b.active,
              COALESCE(SUM(l.earned_dollars),0) AS total_earned,
              COALESCE(SUM(l.rent_dollars),0) AS total_rent,
              COALESCE(SUM(l.net_dollars),0) AS total_net,
              COUNT(DISTINCT l.question_id) AS times_retrieved
       FROM bundle_registry b LEFT JOIN rent_ledger l
         ON b.bundle_id=l.bundle_id AND l.run_id=%(run_id)s AND l.phase=%(phase)s
       GROUP BY b.bundle_id, b.title, b.category, b.is_idle, b.active ORDER BY total_net DESC""",
       {"run_id": run_id, "phase": phase})
    return _rows_as_dicts(cur)

def get_prune_candidates(run_id: str, phase: str = "pre_prune") -> list[str]:
    """PINNED RULE, with a global safety net: bundles retrieved >=2 times, never correct+supporting
    in THIS run, AND never a supporting bundle for ANY question in the fixture (categorical exclusion,
    not just this run's ledger rows)."""
    cur = get_conn().cursor()
    cur.execute("""SELECT bundle_id FROM rent_ledger WHERE run_id=%(run_id)s AND phase=%(phase)s AND arm='memory'
        GROUP BY bundle_id HAVING COUNT(DISTINCT question_id) >= 2
           AND SUM(CASE WHEN is_correct AND is_supporting THEN 1 ELSE 0 END) = 0
           AND NOT EXISTS (SELECT 1 FROM fixture_support_map fsm WHERE fsm.bundle_id = rent_ledger.bundle_id)
        ORDER BY bundle_id""", {"run_id": run_id, "phase": phase})
    return [r[0] for r in cur.fetchall()]

def get_idle_bundles(run_id: str, phase: str) -> list[dict]:
    cur = get_conn().cursor()
    cur.execute("""SELECT b.bundle_id, b.title, b.category FROM bundle_registry b
        WHERE NOT EXISTS (SELECT 1 FROM retrieval_log r WHERE r.bundle_id=b.bundle_id
                           AND r.run_id=%(run_id)s AND r.phase=%(phase)s)""",
        {"run_id": run_id, "phase": phase})   # measured against retrieval_log, not just the seeded is_idle label
    return _rows_as_dicts(cur)

# Exact retrieval-design matrix from Fixtures spec, as data — this is the real gate, not aggregate counts.
EXPECTED_RETRIEVAL = {
    "B01": {"Q1"}, "B02": {"Q2"}, "B03": {"Q3"}, "B04": {"Q4"},
    "B05": {"Q5"}, "B06": {"Q6"}, "B07": {"Q7"}, "B08": {"Q8"},
    "B09": {"Q1", "Q2"}, "B10": {"Q3", "Q4"}, "B11": set(), "B12": set()}

def get_calibration_report(run_id: str, phase: str) -> dict[str, dict]:
    """Verifies PER-QUESTION retrieval membership against EXPECTED_RETRIEVAL — not just an aggregate
    count — including an EXPLICIT zero-retrieval assertion for the idle bundles B11/B12 (their expected
    set is empty, so 'matches_expected' requires actually seeing zero rows, not just a low count)."""
    cur = get_conn().cursor()
    cur.execute("""SELECT bundle_id, question_id FROM retrieval_log
                   WHERE run_id=%(run_id)s AND phase=%(phase)s AND arm='memory'""",
                {"run_id": run_id, "phase": phase})
    actual = {bid: set() for bid in EXPECTED_RETRIEVAL}
    for bundle_id, question_id in cur.fetchall():
        actual.setdefault(bundle_id, set()).add(question_id)
    cur.execute("""SELECT bundle_id, question_id FROM rent_ledger
                   WHERE run_id=%(run_id)s AND phase=%(phase)s AND arm='memory'
                     AND is_correct AND is_supporting""",
                {"run_id": run_id, "phase": phase})
    correct_supporting = {bid: set() for bid in EXPECTED_RETRIEVAL}
    for bundle_id, question_id in cur.fetchall():
        correct_supporting.setdefault(bundle_id, set()).add(question_id)
    report = {}
    for bid, expected_qs in EXPECTED_RETRIEVAL.items():
        actual_qs = actual.get(bid, set())
        report[bid] = {
            "expected_questions": sorted(expected_qs),
            "actual_questions": sorted(actual_qs),
            # Strict EQUALITY everywhere: B11/B12 (expected_qs empty) must show EXACTLY zero rows,
            # and supporting/decoy bundles must be retrieved for EXACTLY their designed questions —
            # an unexpected retrieval is a calibration failure, not a pass.
            "matches_expected": actual_qs == expected_qs,
            "correct_supporting_count": len(correct_supporting.get(bid, set()))}
    return report
```
**Acceptance**: `python -c "import ledger"` succeeds with no errors (module is self-contained, no dependency on `bundles`/`benchmark`); every function above executes real SQL (none are docstring-only stubs).

---

### Task 4 — `bundles.py`: TRUE no-backfill retrieval + prune primitives
**Lane B (cross-lane assist — independent of ledger.py/UI, unblocks Lane A's Task 5) · 45 min — TRICKY 20%, fully sketched** · **Files**: `bundles.py`

**True no-backfill (fixes the earlier bug where the overfetch tail silently replaced pruned seats):** freeze the first `top_k` UNIQUE bundle_ids by rank — active or not — BEFORE looking at `active` status at all. Only after that freeze do we drop any frozen seat whose bundle is inactive; a dropped seat stays EMPTY. Ranks beyond the freeze point are never consulted, so nothing downstream can ever fill a pruned seat.

```python
import mem
from snow import get_conn

TOP_K_DEFAULT, OVERFETCH_PAD = 6, 4   # pad only absorbs duplicate episodes of the SAME session; never a backfill source

def get_session_to_bundle_map() -> dict[str, dict]:
    """{session_id: {'bundle_id': str, 'active': bool}} — fresh 12-row read, cheap."""
    cur = get_conn().cursor()
    cur.execute("SELECT session_id, bundle_id, active FROM bundle_registry")
    return {r[0]: {"bundle_id": r[1], "active": r[2]} for r in cur.fetchall()}

def recall_bundles(query: str, user_id: str, top_k: int = TOP_K_DEFAULT) -> list[dict]:
    hits = mem.recall(query, user_id=user_id, top_k=top_k + OVERFETCH_PAD)   # list[dict], already normalized by mem.py's adapter
    reg = get_session_to_bundle_map()
    seen, frozen_seats = set(), []
    for rank, ep in enumerate(hits, start=1):
        info = reg.get(ep["session_id"])
        if info is None or info["bundle_id"] in seen:
            continue
        seen.add(info["bundle_id"])
        frozen_seats.append({"bundle_id": info["bundle_id"], "score": ep["score"], "rank": rank,
                              "active": info["active"]})
        if len(frozen_seats) == top_k:
            break   # SEATS FROZEN HERE — ranks beyond this point are never read, ever
    return [s for s in frozen_seats if s.pop("active")]   # drop inactive seats, no replacement

def apply_prune(bundle_ids: list[str]) -> None:
    """Real, live SQL. Zero LLM calls. Zero EverOS delete calls — application-level demotion only."""
    conn = get_conn(); cur = conn.cursor()
    cur.executemany("UPDATE bundle_registry SET active=FALSE, pruned_ts=CURRENT_TIMESTAMP() "
                     "WHERE bundle_id = %s", [(b,) for b in bundle_ids])
    conn.commit()

def reset_active_all() -> None:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("UPDATE bundle_registry SET active=TRUE, pruned_ts=NULL")
    conn.commit()
```
**Acceptance — two parts.** Part A (now, no data needed): `python -c "import bundles"` succeeds and every function above has the right signature — this only proves the module imports cleanly. Part B (the REQUIRED deterministic no-backfill check) needs real seeded bundles, which do not exist until Task 5 runs — so run Part B once, immediately after Task 5 completes and BEFORE Task 6 starts (a 2-minute check folded into that transition, not a separate schedule line):
```python
from rent_fixtures import load_world
world = load_world()
q1 = next(q for q in world["questions"] if q["question_id"] == "Q1")["query"]
full = recall_bundles(q1, user_id="acme:support", top_k=12)   # full ranking, all 12 active (Task 5 just seeded them)
rank7_id = full[6]["bundle_id"]
target = full[0]["bundle_id"]
apply_prune([target])
after = recall_bundles(q1, user_id="acme:support", top_k=6)
assert len(after) == 5                                    # seat left EMPTY, not backfilled
assert rank7_id not in {b["bundle_id"] for b in after}     # rank 7 never entered the top-6 window
assert target not in {b["bundle_id"] for b in after}
reset_active_all()   # RESTORE all-12-active before Task 6 runs — do not leave a bundle pruned
```

---

### Task 5 — `seed.py`: idempotent seeding
**Lane A · 30 min** · **Files**: `seed.py`. Depends on Task 1 (fixture content) + Task 4 (`bundles.reset_active_all`, must exist first).

```python
from dotenv import load_dotenv; load_dotenv()
import sys
import mem
from bundles import reset_active_all
from rent_fixtures import load_world
from snow import get_conn

def upsert_registry_row(bundle: dict, session_id: str) -> None:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""MERGE INTO bundle_registry t USING (SELECT %(bid)s AS bundle_id) s
        ON t.bundle_id = s.bundle_id
        WHEN MATCHED THEN UPDATE SET session_id=%(sid)s, title=%(title)s, category=%(cat)s, is_idle=%(idle)s
        WHEN NOT MATCHED THEN INSERT (bundle_id, session_id, title, category, is_idle)
          VALUES (%(bid)s,%(sid)s,%(title)s,%(cat)s,%(idle)s)""",
        {"bid": bundle["bundle_id"], "sid": session_id, "title": bundle["title"],
         "cat": bundle["category"], "idle": bundle["is_idle"]})
    conn.commit()

def seed_bundle(bundle: dict, user_id: str) -> None:
    session_id = f"acme-bundle-{bundle['bundle_id']}"
    try:
        mem.delete(user_id=user_id, session_id=session_id)   # scoped soft-delete — makes reseeding idempotent
    except Exception:
        pass   # first run: nothing to delete yet, ignore
    mem.remember(session_id=session_id,
                 messages=[{"sender_id": user_id, "role": "user", "content": bundle["content"]}])
    episodes = mem.recall(bundle["title"], user_id=user_id, top_k=12)   # list[dict] — Phase 0 adapter
    if not any(ep["session_id"] == session_id for ep in episodes):
        raise RuntimeError(f"seed verify FAILED for {bundle['bundle_id']}: not retrievable after flush")
    upsert_registry_row(bundle, session_id)

def reseed_bundle(bundle_id: str) -> None:
    """Calibration hook (Task 7): after editing rent_world.json, reseed ONLY the changed bundle —
    scoped delete + re-add — never reuse stale indexed text."""
    world = load_world()
    b = next(x for x in world["bundles"] if x["bundle_id"] == bundle_id)
    seed_bundle(b, world["user_id"])

def seed_support_map(world: dict) -> None:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM fixture_support_map")   # idempotent: clear before repopulating
    for q in world["questions"]:
        for bid in q["supporting_bundle_ids"]:
            cur.execute("INSERT INTO fixture_support_map (question_id, bundle_id) VALUES (%s,%s)",
                        (q["question_id"], bid))
    conn.commit()

def main():
    world = load_world()
    for b in world["bundles"]:
        seed_bundle(b, world["user_id"])
    seed_support_map(world)
    reset_active_all()   # every fresh seed starts with all 12 active
    print(f"seeded {len(world['bundles'])} bundles, {len(world['questions'])} support rows")

if __name__ == "__main__":
    if "--restore-active" in sys.argv:
        reset_active_all()   # ONLY the active flag — EverOS content, show1 captures, and ledger rows untouched
        print("bundle_registry: all 12 bundles restored to active=TRUE (show1's captures/ledger rows untouched)")
    elif "--reset" in sys.argv:
        conn = get_conn(); cur = conn.cursor()
        for t in ("eval_results", "retrieval_log", "rent_ledger"):
            cur.execute(f"DELETE FROM {t}")
        conn.commit()
        main()
    else:
        main()
```
`python seed.py --reset` clears the 4 result/log tables (NOT `bundle_registry`, which `upsert_registry_row`/MERGE handles idempotently) and re-seeds — must finish in < 2 min (the "wifi died" rebuild button). This is for pre-show rebuilds only — see Task 7 and the Hour-by-hour schedule for why it must NEVER run after the final `show1` capture is generated. `python seed.py --restore-active` is the lightweight, non-destructive sibling used right before the live demo (Task 7) and between rehearsal passes (Task 11) — it touches ONLY `bundle_registry.active`, nothing else.
**Acceptance**: `python seed.py` → `seeded 12 bundles, 8 support rows`, no `FAILED` lines; `SELECT COUNT(*) FROM bundle_registry;` → `12`; `SELECT COUNT(*) FROM fixture_support_map;` → `8`; `SELECT COUNT(*) FROM bundle_registry WHERE active=TRUE;` → `12`.

---

### Task 6 — `benchmark.py`: paired-arm capture
**Lane A · 80 min — TRICKY 20%, fully sketched** · **Files**: `benchmark.py`, `captures/`. Depends on Task 3 (`ledger`), Task 4 (`bundles`), Task 5 (seeded data) — all now built first. (+5 min vs. the original 75 for `save_receipts_snapshot()` below.)

```python
import argparse, hashlib, json, time, uuid
import jsonschema, tiktoken
from dotenv import load_dotenv; load_dotenv()
from snow import ai_complete, get_conn
from bundles import recall_bundles
from rent_fixtures import load_world, normalize, USER_ID
import ledger

MODEL, TOP_K, CAP = "claude-haiku-4-5", 6, 8000   # fallback: openai-gpt-5-mini (Phase 0 step 7)
GEN_PARAMS = {"temperature": 0, "max_tokens": 40}
ENC = tiktoken.get_encoding("cl100k_base")
SYSTEM_PROMPT = ("You are Acme's internal support/ops assistant. Answer using ONLY the context "
                  "below. Reply with just the short exact fact — no explanation, no extra words.")
RESULT_ROW_SCHEMA = {  # structural grader check, per contract — never runs against model prose directly
  "type": "object",
  "required": ["run_id","phase","arm","question_id","model","prompt_hash","model_answer",
               "gold_answer","is_correct","prompt_tokens","completion_tokens"],
  "properties": {"prompt_tokens": {"type": "integer", "minimum": 0},
                 "completion_tokens": {"type": "integer", "minimum": 0},
                 "is_correct": {"type": "boolean"}}}

def cap_tokens(blocks: list[str], cap: int) -> str:
    b = list(blocks)
    while b and len(ENC.encode("\n\n".join(b))) > cap:
        b.pop(0)
    return "\n\n".join(b)

def _fmt(bid, by_id): return f"[{bid}] {by_id[bid]['title']}\n{by_id[bid]['content']}"

def build_naive_prompt(world: dict, question: dict) -> tuple[str, list[str]]:
    by_id = {b["bundle_id"]: b for b in world["bundles"]}
    ids = sorted(by_id)
    ctx = cap_tokens([_fmt(i, by_id) for i in ids], CAP)
    return f"{SYSTEM_PROMPT}\n\nCONTEXT:\n{ctx}\n\nQUESTION: {question['query']}\nANSWER:", ids

def build_memory_prompt(world: dict, question: dict) -> tuple[str, list[dict], dict]:
    hits = recall_bundles(question["query"], user_id=USER_ID, top_k=TOP_K)
    by_id = {b["bundle_id"]: b for b in world["bundles"]}
    ids = sorted({h["bundle_id"] for h in hits})
    blocks = {i: _fmt(i, by_id) for i in ids}
    bundle_tokens = {i: len(ENC.encode(blocks[i])) for i in ids}   # rent basis — tokenizer-ESTIMATED (cl100k_base), per bundle; not exact Claude tokens
    ctx = cap_tokens(list(blocks.values()), CAP)
    prompt = f"{SYSTEM_PROMPT}\n\nCONTEXT:\n{ctx}\n\nQUESTION: {question['query']}\nANSWER:"
    return prompt, hits, bundle_tokens

def run_arm(arm: str, world: dict, question: dict, run_id: str, phase: str) -> dict:
    hits, bundle_tokens = [], {}
    if arm == "naive":
        prompt, bundle_ids = build_naive_prompt(world, question)
    else:
        prompt, hits, bundle_tokens = build_memory_prompt(world, question)
        bundle_ids = [h["bundle_id"] for h in hits]
    text, usage = ai_complete(MODEL, prompt, purpose=f"rent_eval_{arm}", run_id=run_id, user_id=USER_ID,
                               agent_tag=f"rent:{arm}:{phase}", model_parameters=GEN_PARAMS,
                               extra={"question_id": question["question_id"]})
    row = {"run_id": run_id, "phase": phase, "arm": arm, "question_id": question["question_id"],
           "model": MODEL, "prompt_hash": hashlib.sha256(prompt.encode()).hexdigest(),
           "model_answer": text.strip(), "gold_answer": question["gold_answer"],
           "is_correct": normalize(text) == normalize(question["gold_answer"]),
           "prompt_tokens": usage["prompt_tokens"], "completion_tokens": usage["completion_tokens"]}
    jsonschema.validate(row, RESULT_ROW_SCHEMA)   # validate the DB-row shape BEFORE adding capture-only fields below
    ledger.insert_eval_result(**row, context_bundle_ids=bundle_ids)
    if arm == "memory":
        ledger.insert_retrieval_log(run_id, phase, question["question_id"], hits, bundle_tokens)
        row["bundle_token_map"] = bundle_tokens   # capture-only field, Task 9's compute_local_ledger needs it
    row["context_bundle_ids"] = bundle_ids        # capture-only field — the returned row feeds captures/*.json directly
    return row

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["pre_prune", "post_prune"], required=True)
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()
    run_id = args.run_id or f"rent-{args.phase}-{uuid.uuid4().hex[:8]}"
    ledger.clear_run(run_id, args.phase)   # idempotent rerun — never duplicates rows
    world = load_world()
    events = [{"question_id": q["question_id"],
               "naive": run_arm("naive", world, q, run_id, args.phase),
               "memory": run_arm("memory", world, q, run_id, args.phase)} for q in world["questions"]]
    ledger.run_attribution_sql(run_id, args.phase, model=MODEL)
    json.dump({"run_id": run_id, "phase": args.phase, "model": MODEL, "events": events},
               open(f"captures/replay_{args.phase}.json", "w"), indent=2)
    naive_ok = sum(e["naive"]["is_correct"] for e in events)
    memory_ok = sum(e["memory"]["is_correct"] for e in events)
    if naive_ok != 8:
        print(f"WARNING: NAIVE ARM {naive_ok}/8 — fix fixture/prompt before trusting the savings math")
    print(f"benchmark {args.phase} done: run_id={run_id}, naive={naive_ok}/8, memory={memory_ok}/8")

def save_receipts_snapshot(run_id: str) -> None:
    """Captures the billed-credits tier to a STATIC file so REPLAY_MODE's receipts panel (Task 8/9)
    never queries Snowflake — this is what makes replay genuinely offline for all three cost tiers,
    not just the leaderboard. ~5 min metering lag: call this LAST in Task 7's sequence."""
    cur = get_conn().cursor()
    cur.execute("""SELECT start_time, model_name, query_tag, credits
                   FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY
                   WHERE query_tag LIKE %s ORDER BY start_time DESC LIMIT 20""", (f"{run_id}%",))
    rows = [{"start_time": str(r[0]), "model_name": r[1], "query_tag": r[2], "credits": float(r[3])}
            for r in cur.fetchall()]
    json.dump(rows, open("fixtures/receipts_snapshot.json", "w"), indent=2)
    print(f"receipts snapshot: {len(rows)} rows -> fixtures/receipts_snapshot.json")

if __name__ == "__main__":
    main()
```
**Acceptance**: `python benchmark.py --phase pre_prune --run-id demo1` → `benchmark pre_prune done: run_id=demo1, naive=8/8, memory=8/8` (BOTH arms must hit 8/8 — a naive failure is loud and must be fixed, never silently ignored, since it invalidates the savings math); `captures/replay_pre_prune.json` has 8 entries under `events`.

---

### Task 7 — Calibration + real prune + post-prune capture
**Lane A · 30 min** · **Files**: `reset_prune.py`

**Calibration** (verification, not iteration — the fixture text in Fixtures spec was already designed against the retrieval matrix, so this should pass on the first try): `python -c "import ledger,json; print(json.dumps(ledger.get_calibration_report('demo1','pre_prune'), indent=2))"` — this checks PER-QUESTION membership against `ledger.EXPECTED_RETRIEVAL`, not just aggregate counts. Every bundle's `matches_expected` must be `true`, INCLUDING B11 and B12 (whose `expected_questions` is `[]`, so `matches_expected=true` for them specifically requires zero actual retrieval rows — an explicit, individually checked zero, not an incidental low count). If any bundle shows `matches_expected: false`: edit ONLY that bundle's `content` in `fixtures/rent_world.json` (add/remove shared vocabulary, never touch the gold fact), then `python -c "import seed; seed.reseed_bundle('B09')"` (scoped delete + re-add for that ONE bundle — never edit-in-place without reseeding, stale text stays indexed otherwise), then rerun Task 6 for `demo1`.

**Real prune + post-prune capture + pre-demo staging**, order matters — reproduces the exact sequencing the demo needs:
```bash
python benchmark.py --phase pre_prune --run-id show1        # registry: all 12 active (Task 5 guarantees this)
python -c "import ledger,json; json.dump(ledger.get_prune_candidates('show1','pre_prune'), open('captures/prune_candidates.json','w'))"
python -c "import bundles,json; bundles.apply_prune(json.load(open('captures/prune_candidates.json')))"
python benchmark.py --phase post_prune --run-id show1        # registry: B09,B10 now inactive; TRUE no-backfill shrinks context
python -c "import benchmark; benchmark.save_receipts_snapshot('show1')"   # ~5 min lag — run last, before restoring active
python seed.py --restore-active   # REQUIRED staging step — see below, do not skip
```
`python seed.py --restore-active` flips `bundle_registry.active` back to `TRUE` for all 12 bundles WITHOUT touching EverOS content, `show1`'s captured JSON, or any `rent_ledger`/`eval_results`/`retrieval_log` rows — those stay exactly as captured. This is required because the demo needs a REAL active→inactive transition when PRUNE is clicked on stage: without this step, B09/B10 would already show "pruned" before the presenter ever clicks the button, and the click would be a no-op. Do NOT call `bundles.reset_active_all()` or `seed.py --reset` at any point after the post-prune capture — those are fine (they're what `--restore-active` calls under the hood via `reset_active_all()`), but `seed.py --reset` ALSO wipes `eval_results`/`retrieval_log`/`rent_ledger`, which would destroy `show1`'s captured data — use `--restore-active` specifically, never `--reset`, this close to the demo. `reset_prune.py --run-id show1` wraps the five capture/receipts lines above (not the restore step); `reset_prune.py --restore` (rehearsal only) calls `bundles.reset_active_all()` then reruns both benchmark phases for a fresh `show1` — use it if a rehearsal pass needs a full redo, otherwise just `seed.py --restore-active` between rehearsal PRUNE clicks (Task 11).
**Acceptance**: immediately after the post-prune capture line (before restore), `captures/replay_post_prune.json` has `naive=8/8, memory=8/8` (if memory drops, a supporting bundle was misclassified as a prune candidate — stop, fix Task 3's `NOT EXISTS` guard, do not ship a broken prune) and mean `memory.prompt_tokens` across the 8 questions is strictly lower than in `replay_pre_prune.json` (guaranteed by Task 4's true no-backfill); `SELECT active FROM bundle_registry WHERE bundle_id IN ('B09','B10');` → both `FALSE` at that point. AFTER `seed.py --restore-active` runs: the same query → both `TRUE` — this is the state the demo starts from.

### Task 8 — Leaderboard UI
**Lane B · 90 min** · **Files**: `app.py`. Skeleton + mock data can start right after Phase 0 (11:40), in parallel with Tasks 1–6; wire to real Snowflake queries once Task 3 exists (~13:05). Top of file: `from dotenv import load_dotenv; load_dotenv()`, then `import streamlit as st, os, json`, then `import ledger, bundles` once Tasks 3/4 exist — Task 9 (below) shows the full import block this file ends with.

Dark finance-terminal theme — name it **"Rent Terminal Dark"**, injected via `st.markdown("<style>...</style>", unsafe_allow_html=True)`:

| Token | Hex | Use |
|---|---|---|
| `--bg` | `#0B0F14` | page background |
| `--panel` | `#11161D` | card/table background |
| `--border` | `#1F2937` | hairlines |
| `--text` | `#E6EDF3` | primary text |
| `--muted` | `#6B7280` | idle-column text, footnotes |
| `--green` | `#00D26A` | positive net $, "paying rent" |
| `--red` | `#FF4D4F` | negative net $, "not paying rent", PRUNE button |
| `--amber` | `#FFB000` | headline number, PRUNE callout |

Monospace stack (`"JetBrains Mono", "IBM Plex Mono", ui-monospace, monospace`) throughout — ticker aesthetic. `st.set_page_config(layout="wide")`, ≤2 logical screens (Leaderboard, Regression/Prune — toggle via `st.session_state`). Sidebar: `REPLAY_MODE = st.sidebar.checkbox("Replay mode (zero external calls)", value=os.environ.get("RENT_REPLAY_MODE")=="1")` — this is BOTH the outage fallback and a deliberate demo choice; see Task 9 for what it switches.

All panels below render from ONE normalized row shape — Task 3's LEADERBOARD ROW SCHEMA (`bundle_id, title, category, is_idle, active, total_earned, total_rent, total_net, times_retrieved`) — regardless of source: live mode calls `ledger.get_leaderboard()`/`get_prune_candidates()`/`get_idle_bundles()`; `REPLAY_MODE` calls Task 9's `compute_local_ledger()`, which returns the identical field names. The rendering code below is written ONCE against that shape, never branches on `REPLAY_MODE` itself — only the data-fetching call site does.

Leaderboard screen, top to bottom:
1. Headline `st.metric("ESTIMATED NET $ THIS RUN", f"${total_net:.4f}")` — sum of non-idle `total_net`, amber, largest font on screen.
2. Ranked table (12 non-idle-first rows sorted by `total_net` desc): rank, `bundle_id`, `title`, `category`, `total_earned`, `total_rent`, `total_net`, `times_retrieved`, `active` badge (ACTIVE/PRUNED) — green text `total_net > 0`, red `total_net <= 0` (for retrieved-and-negative rows only; idle rows render in the separate gray panel, not here).
3. **Red "NOT PAYING RENT" panel** — bundle_ids from `get_prune_candidates(run_id, 'pre_prune')`, joined against the same leaderboard rows, red-bordered card showing each candidate's actual `total_rent` charged and `total_earned` (always $0.00) side by side: "retrieved `times_retrieved` times, paid `${total_rent}` in rent, earned $0.00 — never supported a correct answer."
4. **Idle column** — gray card, rows from `get_idle_bundles(...)`: "never entered prompt context — $0.00 rent, $0.00 earned. Audit candidates, not part of the P&L."
5. **Receipts panel** (contract's third cost tier) — DUAL MODE, same as every other panel: live mode queries `SELECT start_time, model_name, query_tag, credits FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY WHERE query_tag LIKE 'show1%' ORDER BY start_time DESC LIMIT 20` directly; `REPLAY_MODE` reads the SAME rows from the static `fixtures/receipts_snapshot.json` written by Task 6's `save_receipts_snapshot()` — zero Snowflake queries in replay mode, this panel included. Labeled either way: "billed credits — Snowflake metering, ~5 min lag — corroborates the run above, never drives the live ticker."
6. Muted footer, two DISTINCT labels, never conflated: "Request-level tokens (naive/memory prompt totals, and therefore \$ earned) are MEASURED — from `AI_COMPLETE`'s `show_details`. Per-bundle rent allocation (\$ rent, \$ net) is TOKENIZER-ESTIMATED (`cl100k_base` via `tiktoken`) — Claude's exact per-snippet token count isn't exposed by `AI_COMPLETE`, so each bundle's rent is an estimate of its share of the measured total, at claude-haiku-4-5's published rate ($0.35/M-token credits × $2.00/credit)."

During Phase 0/dev iteration only (not the scripted demo), enable `from streamlit_autorefresh import st_autorefresh; st_autorefresh(interval=5000, key="dev_refresh")` on the Leaderboard screen so live Snowflake writes show up without a manual click; leave it off for the actual demo since the demo is driven by explicit PRUNE/query clicks against static captures, not a live ticker.
**Acceptance**: `streamlit run app.py` loads dark/monospace with no errors; with `run_id="show1", phase="pre_prune"` loaded (live mode), the red panel lists exactly `B09`/`B10` with `net_dollars < 0` for both, the idle panel lists exactly `B11`/`B12` with `net == 0`.

---

### Task 9 — PRUNE button + replay suite + one live query + whole-app `--replay` mode
**Lane B · 95 min** · **Files**: `app.py` (extends Task 8). The replay-mode compute layer (`compute_local_ledger`) can be built and unit-tested against a HAND-WRITTEN mock capture JSON as soon as Task 8's skeleton exists (~12:25) — it does not need to wait for real captures. A short final pass swaps in the real `captures/*.json` + `fixtures/receipts_snapshot.json` once Task 7 finishes. (+10 min vs. the original 85, for the normalized-schema alignment and the receipts-snapshot read path below.)

```python
import json, os
import streamlit as st
import bundles, ledger
from rent_fixtures import load_world
from benchmark import build_memory_prompt, MODEL, GEN_PARAMS, USER_ID   # reused, not duplicated
from snow import ai_complete, MODEL_RATES, USD_PER_CREDIT

def load_agg(path: str) -> dict:
    """Zero-network aggregate from a capture file — no separate stored 'aggregates' section needed."""
    data = json.load(open(path))
    events = data["events"]
    mean_tokens = sum(e["memory"]["prompt_tokens"] for e in events) / len(events)
    rate = MODEL_RATES[data["model"]]
    return {"mean_memory_prompt_tokens": mean_tokens,
            "mean_memory_cost_per_query": mean_tokens / 1e6 * rate * USD_PER_CREDIT}

def load_receipts_snapshot() -> list[dict]:
    """REPLAY_MODE's receipts panel (Task 8, bullet 5) reads this instead of querying ACCOUNT_USAGE —
    zero Snowflake calls, sourced from Task 6's save_receipts_snapshot()."""
    return json.load(open("fixtures/receipts_snapshot.json"))

def compute_local_ledger(pre_path: str, post_path: str, world: dict, use_post: bool = False) -> dict:
    """Pure-Python reimplementation of ledger.ATTRIBUTION_SQL + get_prune_candidates/get_idle_bundles,
    driven ONLY by captured JSON + the local fixture file — zero Snowflake, zero EverOS calls. Returns
    the SAME LEADERBOARD ROW SCHEMA as ledger.get_leaderboard() (Task 3) — bundle_id, title, category,
    is_idle, active, total_earned, total_rent, total_net, times_retrieved — so app.py's rendering code
    never branches on REPLAY_MODE, only the call site does. Used by --replay mode so the whole app (not
    just the regression rows) survives an outage."""
    data = json.load(open(post_path if use_post else pre_path))
    events = data["events"]
    rate = MODEL_RATES[data["model"]]
    support = {q["question_id"]: set(q["supporting_bundle_ids"]) for q in world["questions"]}
    per_bundle = {b["bundle_id"]: {"title": b["title"], "category": b["category"], "is_idle": b["is_idle"],
                                    "total_earned": 0.0, "total_rent": 0.0, "times_retrieved": 0}
                  for b in world["bundles"]}
    candidate_hits = {b["bundle_id"]: 0 for b in world["bundles"]}
    correct_supporting = {b["bundle_id"]: 0 for b in world["bundles"]}
    for e in events:
        qid, mem_row = e["question_id"], e["memory"]
        saved = e["naive"]["prompt_tokens"] - mem_row["prompt_tokens"]
        ctx_ids = mem_row["context_bundle_ids"]
        supporting_here = [b for b in ctx_ids if b in support[qid]]
        for bid in ctx_ids:
            tok = mem_row.get("bundle_token_map", {}).get(bid, mem_row["prompt_tokens"] // max(len(ctx_ids), 1))
            rent = tok / 1e6 * rate * USD_PER_CREDIT   # tokenizer-estimated per-bundle share, see Task 3
            per_bundle[bid]["total_rent"] += rent
            per_bundle[bid]["times_retrieved"] += 1
            candidate_hits[bid] += 1
            if bid in support[qid] and mem_row["is_correct"] and supporting_here:
                per_bundle[bid]["total_earned"] += saved / len(supporting_here) / 1e6 * rate * USD_PER_CREDIT
                correct_supporting[bid] += 1
    # Candidates/idle are PRE-PRUNE concepts and pruned state is the frozen Task-7 decision — never
    # derive either from the post capture: pruned bundles are absent from post-capture retrieval and
    # would masquerade as "idle but active" (the exact bug this replaces).
    if use_post:
        pre_events = json.load(open(pre_path))["events"]
        candidate_hits = {b["bundle_id"]: 0 for b in world["bundles"]}
        correct_supporting = {b["bundle_id"]: 0 for b in world["bundles"]}
        for e in pre_events:
            qid, mem_row = e["question_id"], e["memory"]
            sup_here = [b for b in mem_row["context_bundle_ids"] if b in support[qid]]
            for bid in mem_row["context_bundle_ids"]:
                candidate_hits[bid] += 1
                if bid in support[qid] and mem_row["is_correct"] and sup_here:
                    correct_supporting[bid] += 1
        pruned_ids = set(json.load(open("captures/prune_candidates.json")))  # frozen in Task 7
    else:
        pruned_ids = set()   # pre-prune view: everything active
    all_supporting_ids = {bid for s in support.values() for bid in s}
    candidates = sorted(bid for bid, n in candidate_hits.items()
                         if n >= 2 and correct_supporting[bid] == 0 and bid not in all_supporting_ids)
    idle = sorted(bid for bid, n in candidate_hits.items() if n == 0)
    leaderboard = sorted(({"bundle_id": bid, **v, "total_net": v["total_earned"] - v["total_rent"],
                            "active": bid not in pruned_ids}
                           for bid, v in per_bundle.items()), key=lambda r: -r["total_net"])
    return {"leaderboard": leaderboard, "candidates": candidates, "idle": idle}

if st.button("PRUNE", type="primary"):
    if REPLAY_MODE:
        st.session_state["pruned"] = True   # LOCAL state flip only — zero Snowflake calls
    else:
        candidates = json.load(open("captures/prune_candidates.json"))       # frozen in Task 7
        bundles.apply_prune(candidates)   # REAL SQL, live, zero LLM calls
        st.session_state["pruned"] = True
    pre, post = load_agg("captures/replay_pre_prune.json"), load_agg("captures/replay_post_prune.json")
    st.session_state.update(cost_before=pre["mean_memory_cost_per_query"],
                             cost_after=post["mean_memory_cost_per_query"])
```
Scoreboard callout (amber → green flash): `st.metric("ESTIMATED PROMPT-INPUT COST / QUERY", f"${cost_after:.5f}", delta=f"{cost_after-cost_before:+.5f}", delta_color="inverse")` beside a plain `${cost_before:.5f}` "before" tile. Pinned wording: "our fixed regression set retained an identical score at lower cost" — never "identical accuracy."

```python
def animate_regression_suite(pruned: bool):
    path = "captures/replay_post_prune.json" if pruned else "captures/replay_pre_prune.json"
    for ev in json.load(open(path))["events"]:
        r = ev["memory"]; icon = "PASS" if r["is_correct"] else "FAIL"
        st.write(f"[{icon}] {ev['question_id']}: {r['model_answer']}  (gold: {r['gold_answer']})")
    # label once, top of section: "measured pre-show run (replayed) — zero live calls"

def run_query(question: dict, run_id: str):
    if REPLAY_MODE:
        ev = next(e for e in json.load(open("captures/replay_post_prune.json"))["events"]
                  if e["question_id"] == question["question_id"])
        r = ev["memory"]
        st.write(f"REPLAYED: {question['query']} -> {r['model_answer']} "
                 f"(context: {r['context_bundle_ids']}, {r['prompt_tokens']} prompt tokens)")
    else:
        prompt, hits, _ = build_memory_prompt(load_world(), question)   # reflects the PRUNED registry
        text, usage = ai_complete(MODEL, prompt, purpose="rent_eval_live", run_id=run_id,
                                   user_id=USER_ID, agent_tag="rent:memory:live", model_parameters=GEN_PARAMS)
        st.write(f"LIVE: {question['query']} -> {text.strip()} "
                 f"(context: {[h['bundle_id'] for h in hits]}, {usage['prompt_tokens']} prompt tokens)")
```
`animate_regression_suite` ALWAYS renders from a captured file — 8 rows, zero LLM calls at click time in EITHER mode (satisfies the binding two-live-call cap). In live mode the leaderboard/candidates/idle panels read Snowflake via `ledger.py`; in `REPLAY_MODE` they read `compute_local_ledger(...)` instead — same shapes, same UI code, zero external calls either way, which is exactly the outage fallback.
**Acceptance**: with `REPLAY_MODE=True` and Snowflake/EverOS DISCONNECTED, the full app (leaderboard, red panel, idle panel, PRUNE click, regression suite, one query) still renders correctly end to end; with `REPLAY_MODE=False`, PRUNE click flips `bundle_registry.active` for `B09`/`B10` to `FALSE` in Snowflake and `run_query` makes exactly one new `llm_call_log` row.

**Note on the replay event schema** — for `compute_local_ledger`'s per-bundle rent math to work standalone, `benchmark.py`'s memory-arm rows must also serialize a `bundle_token_map: {bundle_id: tokens}` field into each capture event (the same `bundle_tokens` dict `build_memory_prompt` already computes) — add `"bundle_token_map": bundle_tokens` to the `row` dict for the memory arm in Task 6's `run_arm` before `json.dump`, alongside the existing `run_id`, `phase`/`arm`, `model`, `prompt_hash`, `model_answer`, `gold_answer`+`is_correct`, `prompt_tokens`/`completion_tokens`, `context_bundle_ids`.

---

### Task 10 — `check_demo.py`
**Lane B · 10 min** · **Files**: `check_demo.py`

```python
from dotenv import load_dotenv; load_dotenv()
import json
from rent_fixtures import load_world
from snow import get_conn

def main():
    world = load_world()
    assert len(world["bundles"]) == 12 and len(world["questions"]) == 8
    pre = json.load(open("captures/replay_pre_prune.json"))
    post = json.load(open("captures/replay_post_prune.json"))
    for cap, name in ((pre, "pre"), (post, "post")):
        assert sum(e["naive"]["is_correct"] for e in cap["events"]) == 8, f"{name}: naive arm not 8/8"
        assert sum(e["memory"]["is_correct"] for e in cap["events"]) == 8, f"{name}: memory arm not 8/8"
    pre_mean = sum(e["memory"]["prompt_tokens"] for e in pre["events"]) / 8
    post_mean = sum(e["memory"]["prompt_tokens"] for e in post["events"]) / 8
    assert post_mean < pre_mean, "post-prune cost/query did not decrease"
    assert set(json.load(open("captures/prune_candidates.json"))) == {"B09", "B10"}
    cur = get_conn().cursor()
    cur.execute("SELECT COUNT(*) FROM rent_ledger WHERE run_id='show1'")
    assert cur.fetchone()[0] > 0, "show1 rows missing from Snowflake — was a destructive reset run after capture?"
    cur.execute("SELECT active FROM bundle_registry WHERE bundle_id IN ('B09','B10')")
    assert all(r[0] is True for r in cur.fetchall()), \
        "B09/B10 are not active — run `python seed.py --restore-active` (Task 7) so the live PRUNE click has a real transition to perform, then rerun this check"
    print(f"check_demo OK: pre_mean={pre_mean:.1f} tok, post_mean={post_mean:.1f} tok, show1 rows verified live, B09/B10 staged ACTIVE")

if __name__ == "__main__":
    main()
```
**Acceptance**: `python check_demo.py` → `check_demo OK: ...`, exit code 0. Single end-to-end gate, checks BOTH the capture files (still 8/8 both arms, both phases; post-prune cheaper) AND that `show1`'s live Snowflake rows exist AND that the registry is staged for a REAL demo transition (`B09`/`B10` currently `active=TRUE`, i.e. `seed.py --restore-active` has already run) — run right before the 15:40 buffer, never followed by a destructive reset.

---

### Task 11 — [HUMAN] Demo rehearsal
**Both · 15 min** (compressed — see cut line)

Before EACH pass: confirm `check_demo.py` last printed `B09/B10 staged ACTIVE` (if a prior pass clicked PRUNE, it flipped them to inactive — run `python seed.py --restore-active` first, it's instant, no need for the heavier `reset_prune.py --restore`). One full timed pass of the demo script (below), toggling `REPLAY_MODE` on for a second pass if time allows to confirm the outage fallback actually works end to end. Confirm `python check_demo.py` is green and `show1` has NOT been reset. Print two index cards: the Q&A cheat sheet and the pinned wording lines ("our fixed regression set retained an identical score at lower cost" / "Context is capital. We built the P&L for it.") so no one paraphrases them wrong on stage.

## Hour-by-hour schedule (11:00–16:00 HARD submission, 15:40 work buffer)

Rebuilt around the corrected dependency graph: `Phase0 → {Task1, Task2→Task3} ∥ Task4 → Task5 → Task6 → Task7 → Task10`, with Task 8/9 built mostly in parallel against mock data on Lane B, Task 4 as an explicit cross-lane assist (independent of ledger.py and UI, and it unblocks Lane A's Task 5 — building it on Lane B is what makes the critical path fit). Own task-time estimates used throughout, matching each Task's header above: Lane A = 20+20+45+30+80+30 = **225 min** (Tasks 1,2,3,5,6,7); Lane B = 45+90+95+10 = **240 min** (Tasks 4,8,9,10); both fit inside the 11:40–15:40 = 240-minute window — Lane B fits with zero slack, Lane A has 15 min slack.

| Time | Lane A | Lane B |
|---|---|---|
| 11:00–11:40 | Phase 0 together: accounts, `bootstrap.py`, `snow.py`, `mem.py`, `smoke.py` PASSES | (joins Lane A) |
| 11:40–12:00 | Task 1: fixture world (20 min) | Task 4: `bundles.py` begins (cross-lane assist, 45 min total, 11:40–12:25) |
| 12:00–12:20 | Task 2: schema bootstrap (20 min) | Task 4 continues |
| 12:20–13:05 | Task 3: `ledger.py` (45 min) | Task 4 finishes @12:25 (lunch overlap ~12:30–13:00), then Task 8 begins: `app.py` skeleton + dark theme + leaderboard against MOCK data (90 min, 12:25–13:55) |
| 13:05–13:35 | Task 5: `seed.py` (30 min; needs Task 1 @12:00 + Task 4 @12:25 — both ready) | Task 8 continues |
| 13:35–14:55 | Task 6: `benchmark.py` (80 min) — **CHECKPOINT: pre_prune run hits naive=8/8, memory=8/8** | Task 8 finishes @13:55, then Task 9 build begins against MOCK captures (95 min total, 13:55–15:30) |
| 14:55–15:25 | Task 7: calibration + real prune + post-prune capture + receipts snapshot + `seed.py --restore-active` (30 min) | Task 9 build continues |
| 15:25–15:30 | Lane A's own tasks done (15 min slack); joins Task 10 prep | Task 9: final wire pass to REAL `captures/*.json` + `fixtures/receipts_snapshot.json`, confirm live-mode AND replay-mode both render |
| 15:30–15:40 | Task 10: `check_demo.py` GREEN (needs Task 7 @15:25 + Task 9 @15:30; asserts `B09`/`B10` staged `active=TRUE`) | (joins Task 10) |
| **— 15:40 work buffer starts —** | | |
| 15:40–15:50 | [HUMAN] Task 11 rehearsal (one pass, toggle `REPLAY_MODE` once; `seed.py --restore-active` between any repeat passes) | [HUMAN] Task 11 rehearsal |
| 15:50–16:00 | Freeze: if the last rehearsal pass clicked PRUNE, run `python seed.py --restore-active` once more, then re-run `check_demo.py`. Do NOT run `seed.py --reset` or `reset_prune.py --restore` after this point — those destroy/regenerate `show1`. | Freeze. |

**Checkpoint / cut line at 14:30** (mid-`benchmark.py`, the single biggest risk item — see Risk table): if Task 6 is not yet producing a clean `pre_prune` run, drop in this order:
1. Rehearsal drops to zero dedicated passes — the LAST run of Task 6/7 IS the rehearsal; Task 11 becomes a 5-minute dry read of the demo script only, no live toggling.
2. Task 9's `REPLAY_MODE` build gets a single, simpler code path: skip the amber→green flash / delta styling, keep the raw `st.metric` numbers only.
3. Task 8's receipts panel (billed-credits tier) is cut — the two measured/estimated tiers stay, the third (lagged, ~5 min) is dropped from the UI and only shown as a screenshot if asked.
4. Task 7's calibration loop is skipped entirely — ship whatever `get_prune_candidates` returns on the FIRST run, as long as it is non-empty and excludes every bundle in `fixture_support_map` (verify that one invariant manually via `check_demo.py`'s assertions — non-negotiable, everything else above it is negotiable).

## Fixtures spec

Domain: fictional SaaS "Acme." 12 bundles = 12 one-session EverOS memories, one Snowflake registry row each. 8 questions, each with exactly one supporting bundle and one short exact-match gold answer. 2 decoys (B09/B10) are worded to be retrieved for specific OTHER questions' queries but never support a correct answer — guaranteed prune candidates. 2 bundles (B11/B12) are idle: their content is deliberately scrubbed of `$`, "month", "plan," "customer," and every other SaaS/product/pricing word so they never surface for any of the 8 queries.

### Retrieval-design matrix (exact — Task 7's calibration gate verifies this)

| Bundle | Category | Retrieved for (by design) | Supporting for | Expected `times_retrieved` |
|---|---|---|---|---|
| B01 | product_spec | Q1 | Q1 | ≥1 |
| B02 | product_spec | Q2 | Q2 | ≥1 |
| B03 | pricing_history | Q3 | Q3 | ≥1 |
| B04 | pricing_history | Q4 | Q4 | ≥1 |
| B05 | customer_quirk | Q5 | Q5 | ≥1 |
| B06 | customer_quirk | Q6 | Q6 | ≥1 |
| B07 | incident_postmortem | Q7 | Q7 | ≥1 |
| B08 | incident_postmortem | Q8 | Q8 | ≥1 |
| B09 (decoy) | product_spec | Q1, Q2 | none | ≥2, 0 correct+supporting |
| B10 (decoy) | pricing_history | Q3, Q4 | none | ≥2, 0 correct+supporting |
| B11 (idle) | idle | none | none | 0 |
| B12 (idle) | idle | none | none | 0 |

### `fixtures/rent_world.json` — literal, final content (transcribe verbatim in Task 1)

```json
{
  "world": "acme_saas_v1",
  "user_id": "acme:support",
  "bundles": [
    {"bundle_id": "B01", "title": "Kanban Board v3 launch", "category": "product_spec", "is_idle": false,
     "content": "Acme's redesigned Kanban board shipped to all plans on 2026-01-15. The new board adds drag-and-drop swimlanes, per-column WIP limits, and configurable swimlane color-coding. Existing boards on the legacy list view were auto-migrated overnight, and no customer action was required. The WIP-limit warning banner is enabled by default for every workspace."},
    {"bundle_id": "B02", "title": "Automations Engine limits", "category": "product_spec", "is_idle": false,
     "content": "Acme's automations engine runs on a trigger, condition, and action model that customers configure without code. The Team plan allows up to 60 automation runs per minute, while the Starter plan is capped at 15 runs per minute and the Enterprise plan has no cap. Each automation can chain up to 5 actions in sequence. Automation history is retained for 30 days on every plan."},
    {"bundle_id": "B03", "title": "2026 Plan Overhaul", "category": "pricing_history", "is_idle": false,
     "content": "Acme restructured its pricing plans effective 2026-01-01. The new Starter plan is $19 per month, the new Team plan is $79 per month, and Enterprise pricing remains custom and quote-based. Before the overhaul the equivalent plans were Starter $15, Pro $59, and Business $149. Customers on the old plans were grandfathered at their existing rate for 90 days after the change."},
    {"bundle_id": "B04", "title": "Enterprise SSO add-on", "category": "pricing_history", "is_idle": false,
     "content": "Single sign-on via SAML and SCIM is sold as an add-on exclusively on Acme's Enterprise plan. The SSO add-on costs $199 per month, billed separately from the base per-seat price. Turning it on requires a dedicated onboarding call with Acme's solutions team to configure the identity provider. SSO cannot currently be purchased on the Starter or Team plans."},
    {"bundle_id": "B05", "title": "Northwind Traders SLA", "category": "customer_quirk", "is_idle": false,
     "content": "Northwind Traders is a 400-seat logistics customer that negotiated a custom uptime SLA outside Acme's standard terms. Their contract guarantees 99.95% uptime, above Acme's standard 99.9% SLA, with financial penalties if Acme falls short. The Northwind contract renews every March and is managed directly by Acme's enterprise account team. Northwind's primary contact is their logistics operations director."},
    {"bundle_id": "B06", "title": "Globex Corp residency", "category": "customer_quirk", "is_idle": false,
     "content": "Globex Corp's contract includes a data residency addendum requiring all of their account data to remain in the EU region. Acme's default data residency for new accounts is US-East unless a customer explicitly negotiates an override like Globex did. Globex Corp's account owner on their side is Priya Nair, VP of IT. The EU residency requirement was a condition of Globex signing their original contract."},
    {"bundle_id": "B07", "title": "2025-11-02 Search Outage", "category": "incident_postmortem", "is_idle": false,
     "content": "On 2025-11-02, a bad index migration took Acme's full-text search offline for 47 minutes, from 14:02 to 14:49 UTC. The root cause was an unbounded reindex job that exhausted memory on the search cluster. The incident was resolved by rolling back the migration and adding a hard memory cap to future reindex jobs. No customer data was lost, and the postmortem was published within 48 hours."},
    {"bundle_id": "B08", "title": "2026-02-14 Billing Double-Charge", "category": "incident_postmortem", "is_idle": false,
     "content": "On 2026-02-14, a retry-logic bug in Acme's Stripe webhook handler double-charged 312 customers. All duplicate charges were automatically refunded within 24 hours of detection. The postmortem action item added idempotency keys to the webhook handler so retries can no longer create duplicate charges. Acme's billing team also added a daily reconciliation job to catch similar issues faster in the future."},
    {"bundle_id": "B09", "title": "Product FAQ (general overview)", "category": "product_spec", "is_idle": false,
     "content": "Acme's product FAQ describes the Kanban board and the automations engine in general marketing language for prospective customers. It says the board is fast and flexible and that automations run automatically to save teams time. The FAQ does not list a launch date for any board version, and it does not state how many automation runs per minute any plan allows. It links out to the full changelog for customers who want exact figures."},
    {"bundle_id": "B10", "title": "External Pricing One-Pager", "category": "pricing_history", "is_idle": false,
     "content": "Acme's external marketing one-pager summarizes plan pricing for prospective customers in broad strokes. It says plans start at $15 per month and mentions that single sign-on is available on the Enterprise plan without listing its price. The one-pager was written before Acme's 2026 pricing overhaul and has not been updated since. Acme's sales team occasionally still links to it by mistake when a prospect asks about pricing."},
    {"bundle_id": "B11", "title": "Team Lunch Potluck Sign-Up", "category": "idle", "is_idle": true,
     "content": "The Tuesday team lunch potluck sign-up sheet is posted on the breakroom whiteboard every week. This week's theme is 'bring a dish from where you grew up,' and eleven people have signed up so far. Whoever is bringing a hot dish should label it with reheating instructions. Leftovers go in the shared fridge and are first-come, first-served on Wednesday morning."},
    {"bundle_id": "B12", "title": "Parking Garage Repaving Schedule", "category": "idle", "is_idle": true,
     "content": "The parking garage next to the office building will have its top two levels repaved starting next Monday. Employees who normally park on levels three and four should use the overflow lot two blocks north for the week. Building management sent a reminder email with a map of the overflow lot and its access hours. The repaving is expected to finish by the following Friday, weather permitting."}
  ],
  "questions": [
    {"question_id": "Q1", "query": "What date did Acme's Kanban Board v3 launch?", "gold_answer": "2026-01-15", "supporting_bundle_ids": ["B01"]},
    {"question_id": "Q2", "query": "How many automation runs per minute does the Team plan allow?", "gold_answer": "60", "supporting_bundle_ids": ["B02"]},
    {"question_id": "Q3", "query": "What is the monthly price of Acme's Team plan after the 2026 pricing overhaul?", "gold_answer": "$79", "supporting_bundle_ids": ["B03"]},
    {"question_id": "Q4", "query": "How much does Acme's Enterprise SSO add-on cost per month?", "gold_answer": "$199", "supporting_bundle_ids": ["B04"]},
    {"question_id": "Q5", "query": "What uptime SLA percentage did Acme commit to for Northwind Traders?", "gold_answer": "99.95%", "supporting_bundle_ids": ["B05"]},
    {"question_id": "Q6", "query": "Which data residency region is contractually required for Globex Corp's account?", "gold_answer": "EU", "supporting_bundle_ids": ["B06"]},
    {"question_id": "Q7", "query": "How long did the 2025-11-02 search outage last?", "gold_answer": "47 minutes", "supporting_bundle_ids": ["B07"]},
    {"question_id": "Q8", "query": "How many customers were affected by the 2026-02-14 billing double-charge incident?", "gold_answer": "312", "supporting_bundle_ids": ["B08"]}
  ]
}
```

Grading: `rent_fixtures.normalize(model_answer) == rent_fixtures.normalize(gold_answer)` — exact match after lowercase/whitespace-collapse/comma-strip/`$`- and `%`-spacing normalization. `SYSTEM_PROMPT` (Task 6) already instructs short exact-form answers, so this match is realistic. Every bundle's content is 4 sentences (~90–130 tokens) — long enough that the 8K naive-arm cap is never actually the source of measured savings in this fixture (12 bundles × ~110 tokens ≈ 1,300 tokens, well under 8K); the savings this fixture demonstrates come entirely from bundle-count reduction (12 in the naive arm vs. up to 6 in the memory arm) and, post-prune, from the two empty seats where B09/B10 used to sit.

## Demo script (3 minutes)

**0:00–0:20 — Leaderboard, pre-loaded from the measured `show1` run (live mode, `REPLAY_MODE` off).** Pre-demo staging (Task 7) already ran `seed.py --restore-active`, so all 12 bundles — INCLUDING B09/B10 — show ACTIVE badges right now; the PRUNE click below is a real flip, not a re-display. "12 memory bundles seeded into EverOS, one real support/ops question stream, 8 exact-answer questions. Every bundle pays rent for its seat and only earns if it's the actual evidence behind a right answer — here's the P&L." Headline NET `$` metric already filled in.

**0:20–0:50 — Walk the ranked table.** Point to the top earner: "Its rent is what it cost to sit in context; its earnings are the tokens we saved on the one question it actually answered — net is the difference, and it's real, not a guess." Point to the gray idle panel: "these two never entered prompt context at all. Zero rent, zero earned — audit candidates, not part of the P&L."

**0:50–1:00 — Red panel: "not paying rent."** "These two got pulled into context multiple times each — the panel shows exactly how many — and every single time they charged rent and earned nothing. That's a genuinely negative number, computed the same way as everyone else's, not a label we chose." (Sets up the hire-then-fire contrast next.)

**1:00–1:30 — Watch a memory get hired (live lifecycle beat).** Type one new fact into "Feed the agent" — the audience watches EverOS extract and store it; a "memory born" panel shows what it distilled, and it enters the board ACTIVE and in the red. A freeform query pulls it back and its FIRST rent charge lands on the leaderboard as a `+$` chip. "Every memory starts life in the red — it has to earn its seat. These two [B09/B10] never did." (If extraction stalls past ~10s, pivot to the pre-fed Initech memory — same beat, no stumble.)

**1:30–1:45 — Fire the freeloaders, live.** Ask the room which decoy dies first, click its `FIRE` button — real SQL flips `active=false` for that one bundle on screen (a genuine ON→OFF transition, not a re-reveal), then `PRUNE` fires the rest. "No fake delete, EverOS doesn't even have a per-memory delete API — this is the exact mechanic it supports, and the seats they vacate stay empty, nothing backfills them." Before/after estimated prompt-input cost-per-query tiles count up, amber → green, sourced from the `show1` post-prune run captured before the show.

**1:45–2:20 — Regression suite, replayed.** "Our fixed regression set retained an identical score at lower cost" — 8 PASS rows animate from the captured post-prune run. On-screen label: "measured pre-show run (replayed) — zero live calls right now."

**2:20–2:50 — One query.** Presenter asks a representative question against the now-pruned registry. Real `ai_complete` call, real token count, right answer, on screen — labeled LIVE (or, if `REPLAY_MODE` had to come on because of a connectivity hiccup earlier in the demo, labeled REPLAYED without breaking stride — same code path, same UI, the audience shouldn't be able to tell from the flow that anything changed).

**2:50–3:00 — Close.** "Context is capital. We built the P&L for it."

## Risk table

| # | Risk | Trigger | Fallback |
|---|---|---|---|
| 1 | Retrieval doesn't match the retrieval-design matrix | Task 7's calibration report shows a bundle's `times_retrieved`/`correct_supporting_count` off the matrix | Edit ONLY the drifting bundle's `content` (shared vocabulary, never the gold fact), run `seed.reseed_bundle(bundle_id)` (scoped delete + re-add — never edit-in-place without reseeding), rerun Task 6 for `demo1`; if still failing at the 14:30 checkpoint, ship whatever `get_prune_candidates` returns as long as it excludes every bundle in `fixture_support_map` (the one non-negotiable invariant) |
| 2 | `claude-haiku-4-5` unavailable/region-locked | `smoke.py`/`benchmark.py` errors on model resolution | Change `MODEL = "openai-gpt-5-mini"` in `benchmark.py` (one constant, Phase 0 step 7), re-run Tasks 6–7 fully before freezing `show1` — never mix models across arms mid-run |
| 3 | Live PRUNE click, live query, or leaderboard read fails on stage (network/Snowflake/EverOS outage) | Any exception during a live segment | Flip the `REPLAY_MODE` sidebar checkbox — the WHOLE app (leaderboard, red panel, idle panel, PRUNE, regression suite, query) switches to `compute_local_ledger(...)` over `captures/*.json` with zero external calls; on-screen copy relabels to "replayed" automatically |
| 4 | EverOS scoped-delete/write failure during idempotent seed or reseed | `seed.py`'s round-trip verify raises `RuntimeError` for a bundle | `seed.py` aborts loudly per-bundle; retry `seed_bundle()` up to 3x before failing the run; the scoped `mem.delete()` before every `add()` means reruns are safe to retry without accumulating duplicate episodes |
| 5 | A supporting bundle's net comes out flat or negative (savings too close to its own rent) | Task 6/7 acceptance shows a B01–B08 row with `total_net <= 0` in `ledger.get_leaderboard` | Verify sign for at least one supporting bundle during Task 6's acceptance check, before Task 7; if flat, the fixture's bundle-count asymmetry (12 naive vs ≤6 memory) is too small relative to per-bundle content length — trim one non-gold sentence from 1–2 bundles to widen the naive/memory token gap, rerun Task 6 |

## Q&A cheat sheet

**"Why do the decoys show negative dollars instead of just zero?"** Because rent isn't optional — every bundle retrieved into a request's context pays for its own token footprint (that bundle's tokenizer-estimated share of that prompt × published rate), regardless of whether it helped. Earnings only accrue when a bundle is literally the supporting evidence behind a question we answered correctly. The two decoys share vocabulary with real questions so they keep getting pulled into context, but neither one contains the fact that actually answers anything — they rack up rent every time and earn nothing. Net negative is computed the same way for every bundle; it just happens to land negative for these two because that's what the numbers say.

**"Is that rent number exact?"** Be precise, not defensive: the request-level totals (naive vs. memory prompt tokens, and therefore \$ earned) are MEASURED — straight from `AI_COMPLETE`'s `show_details`, real Cortex metering. The per-bundle split of that total (\$ rent, and therefore \$ net) is TOKENIZER-ESTIMATED — we count each bundle's tokens with `tiktoken`'s `cl100k_base` because Claude doesn't expose a per-snippet token count through `AI_COMPLETE`. The sign of the result (decoys negative, supporting bundles positive) holds either way; we just don't oversell the per-bundle number as more precise than it is, and the UI labels the two differently on purpose.

**"Did you really delete the pruned memories?"** No, and we're not claiming to. EverOS's real API has no per-memory-ID delete; `delete()` is a session/user-scoped soft delete only. Our prune is an application-level `active=false` flag in our own Snowflake registry. Retrieval freezes the top-k candidate seats by rank BEFORE it even looks at which bundles are active — a pruned seat is dropped and never replaced by whatever was ranked 7th. That's the exact mechanic the API supports, and we can show the deterministic test that proves rank 7 never sneaks in.

**"Why didn't quality drop after pruning?"** Because the prune rule structurally cannot touch a bundle that's a supporting bundle for ANY question in the fixture — that's a global exclusion in the SQL (`NOT EXISTS` against `fixture_support_map`), not just a check against this run's history. Both arms hit 8/8 before AND after pruning, and `check_demo.py` doesn't just trust the capture files — it also queries live Snowflake to confirm `show1`'s rows and pruned registry state are still there, not reset away.


**"So the eval is what saves the tokens?"** No — the eval doesn't save tokens; it tells you which
memories are wasting them. The PRUNE saves tokens — on every call, forever: retrieval stops seating
the pruned memories, the no-backfill rule keeps their seats empty, so every future live prompt is
smaller. The eval is the audit that makes the prune safe (same score, with evidence instead of
vibes). Audits don't make money; closing the money-losing stores does.

**"That's your eval set — what about my real traffic?"** Rent already meters on ANY live prompt, no
ground truth needed. Earnings need an outcome signal plus a counterfactual; the demo uses a fixed
eval because that's provable in a 3-minute window — every number on screen is measured, not
modeled. In production the same ledger runs on your real outcome signals (thumbs up/down, task
completion, did-the-user-re-ask) with a sampled naive baseline. The ledger's inputs are pluggable;
the accounting doesn't change.

**Pitch spine, one line:** costs accrue live, earnings accrue on evidence — every memory pays rent
from the day it's born, and has to prove it earned its seat.
