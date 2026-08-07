# Broke — Implementation Plan

## Goal
Ship a `/route` API that picks the cheapest Snowflake Cortex model that still passes a graded task, gets measurably cheaper as it accumulates EverOS agent-case memory of what worked, and proves it with a replayed paired benchmark (30 tasks is the default critical-path run, 150 tasks is the stretch) plus one live routing decision on stage that routes cheap off promotion state persisted from the pre-show run.

## Why this wins
- The only router in the room with a **learning curve** — the adaptive/frontier cost ratio visibly bends down as cases accumulate, not a flat "we picked a cheap model" story.
- EverOS **agent-side memory** (`agent_case`, not user profile/episodes) used exactly as the real v2 API allows — the deepest EverOS API fidelity on the Track 1 slate.
- Headline number is **honest and measured**: `1 − adaptive_estimated_credits / paired_frontier_estimated_credits`, both arms logged with distinct `QUERY_TAG`s from the same fixed task stream, gated by an actual equality check on quality — no rigged baseline, no fabricated percentage.

## Architecture
```
        benchmark.py (pre-show; DEFAULT fixtures/tasks_small.json = 30 tasks/6 fingerprints;
                       STRETCH fixtures/tasks.json = 150 tasks/30 fingerprints; fixed order;
                       writes replay_events.jsonl INCREMENTALLY, resumable)
                          |
        +-----------------+------------------+
        v                                    v
 FRONTIER ARM (baseline)           ADAPTIVE ARM (router_policy.py state machine)
 always claude-sonnet-5            NEW->SHADOW->PROMOTED->COOLDOWN, deterministic fingerprint id
        |                                    |
        +-----------------+------------------+
                          v
       snow.py::ai_complete() -> AI_COMPLETE (choices[0]["messages"]) + llm_call_log insert
                          |                    \
       fixtures/graders.py (compare to gold)     snow.py::mark_graded(call_id, passed)
                          |
       mem.py::remember_case()/recall_cases() (EverOS agent_case, adapter normalizes .agent_cases)
                          |
   policy_state.json (promotion/cooldown, loaded by api.py) + cases_snapshot.json (real case evidence)
                          |
       replay_events.jsonl -> app.py (Streamlit --replay default, PAUSED at frame 0 until Start)
       two cost tickers, downward-bending cost-ratio curve, cases-learned panel, live-call button
                          |
       api.py loads policy_state.json at startup -> /route serves the ONE live call cheap
```

## Phase 0 — Environment & accounts (embedded from SHARED-CONTRACT.md; target ≤30 min)

Execute in order before any Broke-specific code. Do not skip the smoke gate (0.6).

### 0.1 [HUMAN] Snowflake trial
signup.snowflake.com, AWS US region (widest Cortex/Claude availability), $400 credits, no card. In Snowsight: **Admin → Users → your user → Programmatic access tokens** → create a **PAT**. PAT is the `password` field in the connector. No key-pair auth, no plain password (MFA friction).

### 0.2 [HUMAN] EverOS Cloud key
Sign up at https://everos.evermind.ai → create an API key (grab event staff credits if offered). Use the **Cloud SDK** `everos-cloud`, NOT self-hosted `everos`.

### 0.3 Codex: project bootstrap
```bash
mkdir -p broke && cd broke
python3.12 -m venv .venv && source .venv/bin/activate
pip install python-dotenv
pip install 'everos-cloud>=1,<2' snowflake-connector-python streamlit streamlit-autorefresh \
  fastapi uvicorn tiktoken jsonschema pandas
```
(`'everos-cloud>=1,<2'` is quoted so zsh does not glob-expand it. Per Codex R1 amendment #1, this must resolve to an EverOS v2-enabled 1.x release — smoke.py step 0.6 verifies this and fails loudly with remediation text if not.)

Pin the exact resolved versions into a real `requirements.txt`:
```bash
EVEROS_VERSION=$(pip show everos-cloud | awk '/^Version/{print $2}')
{
  echo "everos-cloud==$EVEROS_VERSION"
  pip freeze | grep -Ei '^(snowflake-connector-python|streamlit|streamlit-autorefresh|fastapi|uvicorn|tiktoken|jsonschema|python-dotenv|pandas)=='
} > requirements.txt
cat requirements.txt   # verify every line has a pinned == version before proceeding
```

Create `.env` (git-ignored), ONE assignment per line:
```
SNOWFLAKE_USER=
SNOWFLAKE_PAT=
SNOWFLAKE_ACCOUNT=
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
SNOWFLAKE_DATABASE=HACKDB
SNOWFLAKE_SCHEMA=PUBLIC
EVEROS_API_KEY=
```
`.gitignore`: `.env`, `.venv/`, `__pycache__/`, `policy_state.json`, `cases_snapshot.json`, `case_index.jsonl`.

### 0.3b [HUMAN] Populate secrets
Codex cannot know your Snowflake user/PAT/account locator or your EverOS API key — a human fills in the five blank values above in `.env` now (`SNOWFLAKE_USER`, `SNOWFLAKE_PAT`, `SNOWFLAKE_ACCOUNT`, `EVEROS_API_KEY`; `SNOWFLAKE_WAREHOUSE`/`DATABASE`/`SCHEMA` are already defaulted). Do not proceed to 0.4 until all five are non-empty. Do not commit `.env`.

### 0.4 Codex: `snow.py` (Lane A owns; Lane B imports only)
```python
# snow.py
from __future__ import annotations
import os, time, uuid, json
from dotenv import load_dotenv
import snowflake.connector
load_dotenv()

MODEL_RATES = {  # credits per 1M tokens, "published rates"
    "mistral-7b": 0.12, "claude-haiku-4-5": 0.35, "openai-gpt-5-mini": 0.32,
    "claude-sonnet-5": 2.6, "claude-opus-4-8": 12.0,
}
# $2.00/credit applies to GLOBAL/cross-region routing (this plan enables
# CORTEX_ENABLED_CROSS_REGION in step 0.6 if a model errors as unavailable).
# If your account is pinned to home-region routing instead, credits cost $2.20 —
# change this constant and every UI/demo-copy $ figure derives from it, nothing is hardcoded twice.
CREDIT_PRICE_USD = 2.00

def get_conn(with_schema: bool = True):
    kw = dict(user=os.environ["SNOWFLAKE_USER"], password=os.environ["SNOWFLAKE_PAT"],
              account=os.environ["SNOWFLAKE_ACCOUNT"], warehouse=os.environ["SNOWFLAKE_WAREHOUSE"])
    if with_schema:
        kw["database"] = os.environ["SNOWFLAKE_DATABASE"]; kw["schema"] = os.environ["SNOWFLAKE_SCHEMA"]
    return snowflake.connector.connect(**kw)

def bootstrap():
    """First connection has NO database/schema (they don't exist yet)."""
    conn = get_conn(with_schema=False); cur = conn.cursor()
    cur.execute("CREATE DATABASE IF NOT EXISTS HACKDB")
    cur.execute("USE DATABASE HACKDB")
    cur.execute("CREATE SCHEMA IF NOT EXISTS PUBLIC")
    cur.execute("""CREATE TABLE IF NOT EXISTS llm_call_log (
      call_id STRING DEFAULT UUID_STRING(), ts TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
      model STRING, purpose STRING, prompt_tokens INT, completion_tokens INT,
      latency_ms INT, credits_est FLOAT, user_id STRING, session_id STRING,
      run_id STRING, agent_tag STRING, passed BOOLEAN, extra VARIANT)""")
    conn.close()

def ai_complete(model: str, prompt: str, purpose: str, run_id: str,
                 user_id: str | None = None, session_id: str | None = None,
                 agent_tag: str | None = None, extra: dict | None = None,
                 max_tokens: int = 300, temperature: float = 0.0) -> tuple[str, dict]:
    """THE ONLY path through which any LLM call happens. Sets QUERY_TAG, logs every call.
    show_details=>TRUE returns a JSON string whose generated text lives at
    choices[0]["messages"] (a plain string, NOT choices[0]["message"]["content"] — verified
    against Snowflake's AI_COMPLETE response docs). model_parameters cannot bind a Python
    dict through the connector, so it is built as a json.dumps() string and passed through
    PARSE_JSON(%s)."""
    conn = get_conn(); cur = conn.cursor()
    cur.execute("ALTER SESSION SET QUERY_TAG = %s", (f"{run_id}:{agent_tag or purpose}",))
    params_json = json.dumps({"temperature": temperature, "max_tokens": max_tokens})
    t0 = time.time()
    cur.execute("""SELECT AI_COMPLETE(model => %s, prompt => %s,
        model_parameters => PARSE_JSON(%s), show_details => TRUE)""",
        (model, prompt, params_json))
    resp = json.loads(cur.fetchone()[0])
    latency_ms = int((time.time() - t0) * 1000)
    text = resp["choices"][0]["messages"]
    usage = resp.get("usage", {})
    pt, ct = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    credits_est = (pt + ct) / 1_000_000 * MODEL_RATES.get(model, 0.0)
    call_id = str(uuid.uuid4())
    cur.execute("""INSERT INTO llm_call_log
        (call_id, model, purpose, prompt_tokens, completion_tokens, latency_ms,
         credits_est, user_id, session_id, run_id, agent_tag, passed, extra)
        SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, NULL, PARSE_JSON(%s)""",
        (call_id, model, purpose, pt, ct, latency_ms, credits_est, user_id, session_id,
         run_id, agent_tag, json.dumps(extra or {})))
    conn.commit(); conn.close()
    return text, {"call_id": call_id, "model": model, "prompt_tokens": pt,
                  "completion_tokens": ct, "latency_ms": latency_ms, "credits_est": credits_est}

def mark_graded(call_id: str, passed: bool | None) -> None:
    """Persists the grader outcome for a specific call, keyed by call_id — this, not the
    EverOS case text, is the authoritative join between a routing decision and its measured
    correctness (see Task 3)."""
    conn = get_conn(); cur = conn.cursor()
    cur.execute("UPDATE llm_call_log SET passed = %s WHERE call_id = %s", (passed, call_id))
    conn.commit(); conn.close()

def billed_credits_since(minutes: int = 60) -> list[dict]:
    """Corroboration panel only — NEVER drives a live ticker (2-5 min lag). Callers must gate
    this behind an explicit user action (button click), never call it during --replay autorefresh."""
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""SELECT start_time, model_name, query_tag, credits
        FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY
        WHERE start_time >= DATEADD('minute', -%s, CURRENT_TIMESTAMP()) ORDER BY start_time DESC""",
        (minutes,))
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close(); return rows
```

### 0.5 Codex: `mem.py` (Lane B owns; Lane A imports only)

Ground-truth v2 API facts (verified against docs.evermind.ai's OpenAPI spec — do not deviate):
- `add()` accepts `session_id, messages, app_id, project_id, mode ("chat"|"agent"), async_mode`. There is **no `agent_id` field on add**. Agent identity travels via each message's `sender_id`, the same way `user_id` travels via `sender_id` in chat mode.
- `search()` accepts `agent_id` but has **no `mode` field** — passing `agent_id` alone selects agent-case search.
- Agent-case results come back under `.agent_cases` (NOT `.memories`/`.episodes`), each item exposing `id, app_id, project_id, agent_id, session_id, task_intent, approach, quality_score, key_insight, timestamp, score`. There is no arbitrary caller-supplied metadata dict — `task_intent`/`approach`/`key_insight` are EXTRACTED by EverOS from the message content, same mechanism as episode/profile extraction. Never assume they echo the input text verbatim.
- The client is scoped with fixed `app_id`/`project_id` on every call (mixed scopes silently break add→flush→search round trips per the contract).

```python
# mem.py
from __future__ import annotations
import os
from dotenv import load_dotenv
from everos_cloud import EverOS
load_dotenv()

APP_ID = "broke"
PROJECT_ID = "broke"

def _client() -> EverOS:
    """app_id/project_id as CONSTRUCTOR defaults (Contract §14) — every call made on this client,
    including flush/edit/delete which never pass scope explicitly, inherits it. Passing scope only
    on add/search/get and leaving flush/edit/delete unscoped is exactly the mixed-scope bug the
    contract warns silently breaks add->flush->search round trips."""
    return EverOS(api_key=os.environ["EVEROS_API_KEY"], app_id=APP_ID, project_id=PROJECT_ID)

def remember(session_id: str, messages: list[dict]) -> None:
    """User-mode add + immediate flush. NEVER skip flush — async extraction breaks live demos."""
    with _client() as c:
        c.add(session_id=session_id, messages=messages, app_id=APP_ID, project_id=PROJECT_ID)
        c.flush(session_id)

def recall(query: str, user_id: str, top_k: int = 10):
    with _client() as c:
        return c.search(query, user_id=user_id, top_k=top_k, app_id=APP_ID, project_id=PROJECT_ID,
                         include_profile=True)

def list_memories(kind: str, user_id: str, page: int = 1, page_size: int = 20):
    with _client() as c:
        return c.get(kind, user_id=user_id, page=page, page_size=page_size,
                      app_id=APP_ID, project_id=PROJECT_ID)

def edit(user_id: str, operations: list[dict]) -> None:
    with _client() as c: c.edit(user_id, operations=operations)

def delete(user_id: str, session_id: str | None = None) -> None:
    with _client() as c: c.delete(user_id=user_id, session_id=session_id)

def delete_agent_cases(agent_id: str) -> None:
    """Scoped soft-delete of ALL cases for an agent_id — used by seed.py --full for a genuine
    fresh-namespace rebuild without renaming the stable agent_id="broke" identity."""
    with _client() as c: c.delete(agent_id=agent_id)

# --- Agent-mode memory path: Broke's routing brain ---
def remember_case(agent_id: str, session_id: str, messages: list[dict]) -> None:
    """add() has NO agent_id field (verified) -- agent identity travels via sender_id."""
    tagged = [{**m, "sender_id": agent_id} for m in messages]
    with _client() as c:
        c.add(session_id=session_id, messages=tagged, mode="agent", app_id=APP_ID, project_id=PROJECT_ID)
        c.flush(session_id)

def recall_cases(query: str, agent_id: str, top_k: int = 5) -> list[dict]:
    """THE ONE TESTED ADAPTER FUNCTION for agent-case search (contract item 14). search() has
    no mode field -- agent_id alone selects agent-case search. Normalizes the typed SDK
    response's .agent_cases into plain dicts; every other module in this repo calls THIS,
    never touches `.agent_cases` directly."""
    with _client() as c:
        result = c.search(query, agent_id=agent_id, top_k=top_k, app_id=APP_ID, project_id=PROJECT_ID)
    cases = getattr(result, "agent_cases", None) or []
    return [{"id": c.id, "session_id": c.session_id, "score": c.score,
              "task_intent": getattr(c, "task_intent", None), "approach": getattr(c, "approach", None),
              "quality_score": getattr(c, "quality_score", None), "key_insight": getattr(c, "key_insight", None),
              "timestamp": getattr(c, "timestamp", None)} for c in cases]

def recall_cases_from_session(query: str, agent_id: str, session_id: str, top_k: int = 5) -> list[dict]:
    """Filters recall_cases() to results originating from a SPECIFIC session — used by smoke.py
    to prove retrieval is reading the just-written case, not stale data from an earlier run."""
    return [c for c in recall_cases(query, agent_id, top_k=top_k) if c["session_id"] == session_id]

# --- Phase-0 fallback path (AGENT_MODE=False): SAME dict shape as recall_cases(), so every
# downstream consumer (cases_snapshot, the UI panel, _log_case callers) works unmodified
# regardless of which mode is active — this is the "normalize through the same adapter" fix. ---
def remember_case_fallback(agent_id: str, session_id: str, messages: list[dict]) -> None:
    remember(session_id, [{**m, "sender_id": f"agent:{agent_id}"} for m in messages])

def recall_cases_fallback(query: str, agent_id: str, top_k: int = 5) -> list[dict]:
    result = recall(query, user_id=f"agent:{agent_id}", top_k=top_k)
    episodes = getattr(result, "episodes", None) or []
    return [{"id": getattr(e, "id", None), "session_id": getattr(e, "session_id", None),
              "score": getattr(e, "score", None),
              "task_intent": getattr(e, "content", None) or getattr(e, "description", None),
              "approach": None, "quality_score": None, "key_insight": None,
              "timestamp": getattr(e, "timestamp", None)} for e in episodes]

def parse_case_ids(case: dict) -> tuple[str | None, str | None]:
    """Best-effort case -> Snowflake join (Task 3). add() has no metadata field, so _log_case()
    embeds '...|call_id=<uuid>|task_id=<id>' as a structured tail line in the message text; EverOS's
    own extraction (task_intent/approach/key_insight) usually preserves short ID-like tokens
    verbatim, but this is NOT a documented guarantee -- a parse miss is expected, not an error.
    llm_call_log.call_id (written directly by ai_complete(), never through EverOS) remains the ONLY
    authoritative source; this is a debugging/evidence convenience, never load-bearing."""
    import re
    blob = " ".join(str(case.get(k) or "") for k in ("task_intent", "approach", "key_insight"))
    m = re.search(r"call_id=(\S+?)(?:\||\s|$)", blob)
    t = re.search(r"task_id=(\S+?)(?:\||\s|$)", blob)
    return (m.group(1) if m else None, t.group(1) if t else None)
```

### 0.6 [GATE] Phase-0 agent-case smoke proof (BINDING — Codex R1 amendment #7)
Tests the ACTUAL PRODUCTION model pair FIRST (`claude-sonnet-5` frontier, `openai-gpt-5-mini` cheap —
Pinned decisions #2/#3), only falling back to the contract's ordered list if those specifically are
unavailable; writes whichever models actually pass to `models.json`, which `router_policy.py` loads
at import time — constants never drift from what smoke actually verified. Wraps BOTH the user-mode
and agent-case EverOS round trips in the same 403-remediation handling (a prior draft only wrapped
agent-case, so a v1-key error in the user-mode block crashed before the gate could even run), and
distinguishes "agent-case failed, user-mode fallback still works" (exit 2) from "both failed" (exit 3
— the real Déjà Vu trigger) from "all green" (exit 0).

`smoke.py`:
```python
# smoke.py
import json, sys, uuid
from dotenv import load_dotenv
load_dotenv()
import snow, mem

# Production pair tried FIRST (index 0) so the smoke test proves what actually ships, not just
# whatever's most broadly available; contract-ordered fallbacks trail behind.
FRONTIER_CANDIDATES = ["claude-sonnet-5", "llama3.3-70b"]
CHEAP_CANDIDATES = ["openai-gpt-5-mini", "claude-haiku-4-5", "mistral-7b"]

def try_model(tier_name, candidates):
    for model in candidates:
        try:
            text, usage = snow.ai_complete(model, "Reply with exactly: ok", "smoke", run_id="smoke-run")
            assert usage["prompt_tokens"] > 0, f"{model}: measured prompt_tokens was 0 -- parsing is broken"
            print(f"{tier_name} OK: {model} -> {text[:30]!r} tokens={usage['prompt_tokens']}+{usage['completion_tokens']}")
            return model
        except Exception as e:
            print(f"{tier_name}: {model} unavailable ({e}); trying next fallback")
    raise RuntimeError(f"No {tier_name} model available even after fallbacks — check "
                        f"CORTEX_ENABLED_CROSS_REGION and region availability")

def _remediate_if_v1(e):
    msg = str(e)
    if "403" in msg and "VERSION_NOT_ALLOWED" in msg:
        print("REMEDIATION: this EverOS key is v1-only. Regenerate a v2-enabled key at "
              "https://everos.evermind.ai (or ask event staff for a v2 key) and rerun smoke.py.")

def main():
    print("== Snowflake bootstrap =="); snow.bootstrap()
    frontier_model = try_model("frontier", FRONTIER_CANDIDATES)
    cheap_model = try_model("cheap", CHEAP_CANDIDATES)
    json.dump({"frontier_model": frontier_model, "cheap_model": cheap_model}, open("models.json", "w"))
    print(f"wrote models.json: frontier={frontier_model} cheap={cheap_model}")

    print("== EverOS user-mode round trip ==")
    user_mode_ok = False
    try:
        sid = f"smoke-{uuid.uuid4().hex[:8]}"
        mem.remember(sid, [{"sender_id": "smoke-user", "role": "user", "content": "I love hiking"}])
        r = mem.recall("outdoor hobbies", user_id="smoke-user", top_k=5)
        assert len(r.episodes) > 0, "user-mode round trip returned 0 episodes"
        user_mode_ok = True
        print("user-mode recall episodes:", len(r.episodes))
    except Exception as e:
        _remediate_if_v1(e)
        print(f"USER-MODE ROUND TRIP FAILED ({e}).")

    print("== EverOS AGENT-CASE round trip (Broke's routing brain — GATE) ==")
    agent_case_ok = False
    try:
        asid = f"smoke-agent-{uuid.uuid4().hex[:8]}"
        mem.remember_case("broke", asid, [{"sender_id": "broke", "role": "assistant",
            "content": "Routed json_extraction fingerprint invoice_total to mistral-7b, result PASS, "
                       "142 tokens.|call_id=smoke|task_id=smoke"}])
        cases = mem.recall_cases_from_session("json_extraction invoice_total", agent_id="broke",
                                               session_id=asid, top_k=5)
        print("agent-case recall count (from THIS session):", len(cases))
        if len(cases) == 0:
            raise AssertionError("agent-case search returned 0 results originating from the fresh session "
                                  "-- either extraction is too slow (retry once after a short pause) or broken")
        agent_case_ok = True
        print("AGENT-CASE MODE: CONFIRMED. benchmark.py/api.py run with AGENT_MODE=True.")
    except Exception as e:
        _remediate_if_v1(e)
        print(f"AGENT-CASE MODE FAILED ({e}).")

    if not user_mode_ok and not agent_case_ok:
        print("BOTH EverOS round trips failed — this is the Déjà Vu pivot trigger (see risk table R1 item 2).")
        sys.exit(3)  # exit 3 = total EverOS failure, pivot
    if not agent_case_ok:
        print("FALLBACK: fingerprinted user-mode memory under user_id='agent:broke'. "
              "Set AGENT_MODE=False in benchmark.py and api.py. "
              "Copy guard: strike 'agent-side memory used as designed' from all UI/demo copy.")
        sys.exit(2)  # exit 2 = fallback required, not a hard failure
    print("Phase 0 smoke: ALL GREEN.")

if __name__ == "__main__": main()
```
Run `python smoke.py`. Expect `models.json` to be written, then either `Phase 0 smoke: ALL GREEN.` (exit 0), the exit-2 fallback message (apply it immediately: set `AGENT_MODE = False` at the top of `benchmark.py` and `api.py`), or exit 3 — total EverOS failure, the Déjà Vu PIVOT trigger (risk table item 2 spells out exactly what this costs and what it reuses; it is a ~20-minute planning cost, not a ready-made fallback). If a model errors as unavailable, the fallback loop already retries the next candidate; if ALL candidates in a tier fail, run `ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';` and rerun.

### 0.7 Note
`snow.bootstrap()` (0.4) already sequences `CREATE DATABASE`/`CREATE TABLE` on a schema-less first connection, then all later `get_conn()` calls use `database=HACKDB, schema=PUBLIC`. No separate bootstrap script needed.

---

## Pinned decisions (binding — do not relitigate)

1. **`task_family` is REQUIRED on every `/route` request** — one of `"json_extraction" | "classification" | "summarization"`.
2. **Primary cheap model: `openai-gpt-5-mini`.** Fallback (only if unavailable in trial region): `mistral-7b`. Exactly one cheap model active per benchmark run — no mid-run alternation.
3. **Frontier model: `claude-sonnet-5`** (fixed, fallback `llama3.3-70b`).
   Decisions #2/#3 are the INTENDED pair — `smoke.py` (0.6) verifies them against the actual account and writes whichever models really passed to `models.json`, which `router_policy.py` loads at import time. If a fallback fired, the constants reflect that automatically; nothing needs manual editing.
4. **Deterministic caps, both arms, every call:** `max_tokens=300`, `temperature=0`.
5. **Fingerprint identity is DETERMINISTIC, not semantically matched** — `fingerprint_id = f"{task_family}:{fingerprint_seed}"`. **Design correction from the original spec:** the confirmed EverOS v2 `agent_cases` schema (`task_intent`/`approach`/`quality_score`/`key_insight`, all LLM-extracted, no caller-supplied metadata dict — see Task 2) cannot support exact-match lookup of an arbitrary `fingerprint_id` field. Relying on semantic search for state-machine identity was found to be non-reproducible against the real API and is dropped from the critical path. `recall_cases()` is retained as real, queried EverOS evidence for the "cases learned" UI panel (Task 6) and as the write-side record of every graded outcome — just not as the router's identity key. This keeps "`task_family` required" intact while making the rest of the pin implementable.
6. **`/route` requires `gold` for every request in this build.** This is a routing-benchmark API, not a general ungraded production endpoint — every request must be gradable so promotion/escalation can run. (A production deployment would split "shadow-graded learning traffic" from "ungraded traffic that only reads cached routing state" — out of scope for a 5-hour build.)
7. **Credit price: $2.00/credit**, valid under the cross-region routing this plan enables in step 0.6. If your account stays pinned to home-region routing, it is $2.20/credit instead — change `snow.CREDIT_PRICE_USD` and every derived $ figure updates with it.
8. **Copy guards (apply verbatim):** never "identical accuracy" — say **"same measured score on our fixed benchmark"** ONLY if `check_demo.py`'s parity assertion (Task 7) actually passed; if it didn't, state both measured numbers instead. If Phase-0 fell back to user-mode memory, strike **"agent-side memory used as designed"** and say **"fingerprinted user-mode memory (EverOS agent-case fallback)."** All percentages/dollars on stage are the measured values from the pre-show `benchmark.py` run.

---

## Tasks

### Task 1 — Fixture generator (`fixtures/generate.py`, `fixtures/tasks_small.json`, `fixtures/tasks.json`, `fixtures/graders.py`)
**Lane A** · **Est: 45 min**

**All 30 fingerprint slugs (10 per family, fixed):**
- `json_extraction`: `invoice_total, ticket_id, order_number, tracking_number, employee_id, po_number, account_balance, flight_number, confirmation_code, membership_id`
- `classification`: `sentiment, priority, spam, topic, urgency, language, intent, risk_level, department, escalation`
- `summarization`: `meeting_notes, incident_report, customer_call, sprint_retro, sales_call, support_ticket, product_review, onboarding_note, vendor_email, status_update`

**Two output files, both fixed order, both deterministic (`random.Random(42)`):**
- `fixtures/tasks_small.json` — **DEFAULT critical-path fixture.** 30 tasks = the FIRST 2 slugs of each family (`invoice_total, ticket_id` / `sentiment, priority` / `meeting_notes, incident_report`) × 5 reps = 6 fingerprints × 5 repeats.
- `fixtures/tasks.json` — **STRETCH fixture.** 150 tasks = all 10 slugs/family × 5 reps = 30 fingerprints × 5 repeats. Only attempt after `tasks_small.json` has a green benchmark run (see schedule).

`graders.py` — fixes two bugs found in dry-run: JSON extraction must compare BOTH `field` and `value` to gold (previously only `value` was checked, so any `field` string passed); classification's punctuation strip must happen in ONE combined `strip()` call, not chained single-character calls (chained `.strip('"').strip(".")` fails on `"positive".` because stripping `.` first exposes a trailing `"` that the quote-strip pass already finished with):
```python
# fixtures/graders.py
import json, re
from jsonschema import validate, ValidationError

JSON_EXTRACTION_SCHEMA = {"type": "object", "required": ["field", "value"],
                           "properties": {"field": {"type": "string"}, "value": {}}}

def grade_json_extraction(output_text: str, gold: dict) -> bool:
    try:
        parsed = json.loads(_extract_json_block(output_text))
        validate(instance=parsed, schema=JSON_EXTRACTION_SCHEMA)
    except (json.JSONDecodeError, ValidationError, TypeError):
        return False  # parse failure = incorrect. Never exec(). Never LLM-judge.
    field_ok = _normalize(parsed.get("field", "")) == _normalize(gold["field"])
    value_ok = _normalize(parsed["value"]) == _normalize(gold["value"])
    return field_ok and value_ok

def grade_classification(output_text: str, gold: dict) -> bool:
    cleaned = output_text.strip().strip("\"'.,;:").strip().lower()  # ONE combined strip() call
    return cleaned == gold["label"].lower()

def grade_summarization(output_text: str, gold: dict) -> bool:
    low = output_text.lower()
    return all(fact.lower() in low for fact in gold["required_facts"])  # ALL required facts

def _normalize(v):
    return re.sub(r"\s+", " ", v.strip().lower()) if isinstance(v, str) else v

def _extract_json_block(text: str) -> str:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else text

GRADERS = {"json_extraction": grade_json_extraction, "classification": grade_classification,
           "summarization": grade_summarization}
```

`generate.py` — DEFAULT set fully coded below (run this first; it is the only thing the 14:30 cut line depends on). One generic template per family + a per-slug value/label table; gold is DERIVED from the substituted value, never hand-typed:
```python
# fixtures/generate.py
import json, random

JX_SPECS = {  # slug -> (field_name, label_text, value_generator(rnd))
    "invoice_total": ("total_due", "Total Due", lambda r: round(r.uniform(20, 500), 2)),
    "ticket_id": ("ticket_id", "Ticket reference", lambda r: f"SUP-{r.randint(10000,99999)}"),
    # STRETCH-only slugs (150-task run): order_number, tracking_number, employee_id, po_number,
    # account_balance, flight_number, confirmation_code, membership_id -- add entries here
    # following the identical (field, label, value_generator) 3-tuple shape before running the
    # stretch generator.
}
JX_CONTEXTS = ["Acme Corp record #{n}. {label}: {value}.", "Bolt Supply document #{n}. {label}: {value}.",
               "Vertex Labs entry #{n}. {label}: {value}."]

CL_LABELS = {"sentiment": ["positive","negative","neutral"], "priority": ["low","medium","high"]}
CL_BANK = {  # slug -> >=5 (text, label) tuples, cycled by index
    "sentiment": [
        ("This blender broke on day two and support never responded.", "negative"),
        ("Solid build quality, does what it says, arrived early.", "positive"),
        ("It's fine. Does the job, nothing special.", "neutral"),
        ("Worst purchase this year, complete waste of money.", "negative"),
        ("Exceeded every expectation, will buy again.", "positive"),
    ],
    "priority": [
        ("Production database returning 500s for all customers right now.", "high"),
        ("Typo in the footer copyright year.", "low"),
        ("Checkout is slow for about 5% of users during peak hours.", "medium"),
        ("Entire site is down, every customer affected.", "high"),
        ("Feature request: dark mode for the settings page.", "low"),
    ],
    # STRETCH-only slugs: spam, topic, urgency, language, intent, risk_level, department, escalation
    # -- add a CL_LABELS entry + a >=5-tuple CL_BANK entry per slug, identical shape to the two above.
}

SM_BANK = {  # slug -> >=5 (note_text, required_facts[3]) tuples
    "meeting_notes": [
        ("Team discussed Q3 roadmap. Decided to delay mobile launch to prioritize the API rewrite. "
         "Sarah owns the API rewrite. Target: September 15.", ["api rewrite", "sarah", "september 15"]),
        ("Marketing sync on launch campaign. Decided social-first over email. Devon owns the campaign. "
         "Must go live by October 1.", ["social-first", "devon", "october 1"]),
        ("Eng sync on tech debt. Decided to pause new features for two weeks. Priya owns the cleanup. "
         "Wraps November 3.", ["tech debt", "priya", "november 3"]),
        ("Support sync on backlog. Decided to hire a contractor. Miguel owns onboarding them. "
         "Starts December 1.", ["contractor", "miguel", "december 1"]),
        ("Finance sync on Q4 budget. Decided to freeze new hires. Alex owns communicating it. "
         "Announced January 5.", ["freeze", "alex", "january 5"]),
    ],
    "incident_report": [
        ("At 14:02 UTC checkout began timing out. Root cause: a connection pool leak in payments. "
         "Resolved by restarting the pool at 14:41 UTC.", ["connection pool leak", "payments", "restart"]),
        ("At 09:15 UTC login failed for EU users. Root cause: an expired TLS cert on the auth "
         "gateway. Resolved by rotating the cert at 09:40 UTC.", ["tls cert", "auth gateway", "rotat"]),
        ("At 22:03 UTC search returned empty results. Root cause: the index rebuild job crashed. "
         "Resolved by rerunning the job at 22:50 UTC.", ["index rebuild", "crashed", "rerun"]),
        ("At 03:11 UTC billing double-charged 40 accounts. Root cause: a retry without idempotency "
         "keys. Resolved by refunding and deploying a fix at 04:00 UTC.", ["idempotency", "refund", "billing"]),
        ("At 16:20 UTC uploads failed for large files. Root cause: a storage bucket hit quota. "
         "Resolved by raising the quota at 16:35 UTC.", ["storage bucket", "quota", "raising"]),
    ],
    # STRETCH-only slugs: customer_call, sprint_retro, sales_call, support_ticket, product_review,
    # onboarding_note, vendor_email, status_update -- add a >=5-tuple SM_BANK entry per slug,
    # identical (note_text, required_facts[3]) shape.
}

def gen_json_extraction(slugs, rnd):
    tasks = []
    for si, slug in enumerate(slugs):
        field, label, valgen = JX_SPECS[slug]
        for rep in range(5):
            value = valgen(rnd)
            sentence = rnd.choice(JX_CONTEXTS).format(n=rnd.randint(1000, 9999), label=label, value=value)
            tasks.append({"task_id": f"jx-{si*5+rep+1:03d}", "task_family": "json_extraction",
                "fingerprint_seed": slug,
                "prompt": (f"Extract the {field} from this text. Respond with ONLY a JSON object of the "
                           f"form {{\"field\": \"{field}\", \"value\": <value>}}. Text: '{sentence}'"),
                "gold": {"field": field, "value": value}})
    return tasks

def gen_classification(slugs, rnd):
    tasks = []
    for si, slug in enumerate(slugs):
        bank = CL_BANK[slug]
        for rep in range(5):
            text, label = bank[rep % len(bank)]
            tasks.append({"task_id": f"cl-{si*5+rep+1:03d}", "task_family": "classification",
                "fingerprint_seed": slug,
                "prompt": (f"Classify this text as exactly one word from {CL_LABELS[slug]}. "
                           f"Respond with ONLY that one word. Text: '{text}'"),
                "gold": {"label": label}})
    return tasks

def gen_summarization(slugs, rnd):
    tasks = []
    for si, slug in enumerate(slugs):
        bank = SM_BANK[slug]
        for rep in range(5):
            text, facts = bank[rep % len(bank)]
            tasks.append({"task_id": f"sm-{si*5+rep+1:03d}", "task_family": "summarization",
                "fingerprint_seed": slug,
                "prompt": (f"Summarize this note in 2 sentences. Your summary MUST mention all of: "
                           f"{', '.join(facts)}-relevant details. Note: '{text}'"),
                "gold": {"required_facts": facts}})
    return tasks

def build(jx_slugs, cl_slugs, sm_slugs):
    rnd = random.Random(42)
    return gen_json_extraction(jx_slugs, rnd) + gen_classification(cl_slugs, rnd) + gen_summarization(sm_slugs, rnd)

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true",
                     help="also generate the 150-task fixtures/tasks.json (requires all 30 slugs "
                          "filled into JX_SPECS/CL_LABELS+CL_BANK/SM_BANK above first)")
    args = ap.parse_args()
    small = build(["invoice_total", "ticket_id"], ["sentiment", "priority"], ["meeting_notes", "incident_report"])
    json.dump(small, open("fixtures/tasks_small.json", "w"), indent=2)
    print(f"wrote fixtures/tasks_small.json: {len(small)} tasks")
    if args.full:
        # fixtures/tasks.json is NOT generated by default -- only by this stated flag, and only
        # once the 24 remaining stretch slugs are filled in (see the STRETCH-only comments above).
        full = build(list(JX_SPECS), list(CL_BANK), list(SM_BANK))
        json.dump(full, open("fixtures/tasks.json", "w"), indent=2)
        print(f"wrote fixtures/tasks.json: {len(full)} tasks")
```

**Acceptance check (DEFAULT, required):**
```bash
python fixtures/generate.py && python -c "
import json
d = json.load(open('fixtures/tasks_small.json'))
assert len(d) == 30, len(d)
from collections import Counter
fams = Counter(t['task_family'] for t in d)
assert fams == {'json_extraction': 10, 'classification': 10, 'summarization': 10}, fams
fps = Counter(t['fingerprint_seed'] for t in d)
assert len(fps) == 6 and all(v == 5 for v in fps.values()), fps
print('OK', fams, fps)"
```
Expected: `OK Counter({'json_extraction': 10, 'classification': 10, 'summarization': 10}) Counter({...6 slugs each =5...})`

**Acceptance check (STRETCH, only after filling in all 30 slugs):**
```bash
python fixtures/generate.py --full     # tasks.json is only ever produced by this explicit flag
python -c "
import json
d = json.load(open('fixtures/tasks.json'))
assert len(d) == 150, len(d)
from collections import Counter
fams = Counter(t['task_family'] for t in d)
assert fams == {'json_extraction': 50, 'classification': 50, 'summarization': 50}, fams
fps = Counter(t['fingerprint_seed'] for t in d)
assert len(fps) == 30 and all(v == 5 for v in fps.values()), fps
print('OK', fams)"
```
Expected: `OK Counter({'json_extraction': 50, 'classification': 50, 'summarization': 50})`

---

### Task 2 — `router_policy.py` (exploration state machine — SHARED with Allowance, fully sketched)
**Lane A owns this file exclusively — Lane B never edits `router_policy.py`, only imports it (`api.py`, `app.py`).** · **Est: 90 min** — hardest task in the plan; do not compress, do not shrink its schedule slot.

File: `router_policy.py` (repo root). Per `slate-v31-pins.md`, Allowance imports this exact module unmodified: *"Learner policy = EXACTLY Broke's state machine."*

**Fingerprint identity is DETERMINISTIC**: `fingerprint_id = f"{task_family}:{fingerprint_seed}"` (see Pinned decision #5 — the original semantic-match design does not survive contact with the real `agent_cases` schema, which has no caller-supplied metadata field to match on). `recall_cases()` is still called every route (via `remember_case`) purely to WRITE real, queryable EverOS evidence for the UI's cases-learned panel — it does not participate in state lookup.

**States:**
```
NEW      -> first time this fingerprint is seen
SHADOW   -> frontier is authoritative; cheap model ALSO called silently, graded, never returned
PROMOTED -> cheap model is authoritative
COOLDOWN -> cheap model failed once; frontier authoritative for 3 more requests, then re-trial
```

**Transitions (exact):**
1. `NEW` → route=frontier + fire one shadow cheap call, grade both. `cheap_pass_count` initialized from shadow result. State → `SHADOW`.
2. `SHADOW`, next request same fingerprint → route=frontier again + another shadow call. Cheap pass → `cheap_pass_count += 1`; at `>= 2` (cumulative, not necessarily consecutive) → `PROMOTED`. Cheap fail → stay `SHADOW` (no decrement — frontier was authoritative, no user-facing harm), log failure case.
3. `PROMOTED` → route=cheap only (no shadow — this is where savings accrue). Pass → stay `PROMOTED`. Fail → escalate THIS request to frontier immediately (return that answer), log failure case, → `COOLDOWN`, `cooldown_remaining=3`.
4. `COOLDOWN` → route=frontier, decrement each request; at 0 → next request for that fingerprint starts `SHADOW` with `cheap_pass_count=0` (full re-trial, not instant re-promotion).

All four states' calls count toward spend — frontier, shadow, escalation, and promoted-cheap calls are ALL logged to `llm_call_log` with distinct `purpose` tags (`route_frontier`, `route_shadow`, `route_escalation`, `route_cheap`). No call is ever excluded from the paired-economics denominator. Every call whose task carries `gold` (Pinned decision #6: always true for `/route` in this build) is graded and its outcome persisted via `snow.mark_graded(call_id, passed)` — this, not EverOS case text, is the authoritative join (Task 3).

**Persistence (closes "captured promotion cannot reach the live API"):** `RouterPolicy.save_state()`/`load_state()` serialize `self._records` to `policy_state.json`. `benchmark.py` saves after its run; `api.py` loads it at startup, so a fingerprint promoted during the pre-show benchmark is already `PROMOTED` for the live demo process — no dependency on cross-process EverOS lookups for correctness.

```python
# router_policy.py — shared module, imported verbatim by Allowance. Lane A owns this file.
"""
AGENT-CASE PAYLOAD CONTRACT (Broke <-> Allowance shared module)
Every graded routing decision writes ONE EverOS agent-case message (via remember_case) describing
what happened in plain language, e.g. "Routed json_extraction/invoice_total to openai-gpt-5-mini,
result PASS." EverOS's own extraction turns this into agent_cases fields (task_intent, approach,
quality_score, key_insight) -- those are LLM-paraphrased, not exact-matchable, and are NEVER used
as the cost/grading source of truth. That source of truth is llm_call_log: every ai_complete() call
carries extra={"task_id","fingerprint_id","task_family"} and gets its `passed` column set via
snow.mark_graded(call_id, ...) once graded. The EverOS case is real, queried evidence for the
UI's cases-learned panel (Task 6) -- not a database index.
"""
import json
from dataclasses import dataclass, asdict
from enum import Enum

def _load_models(path="models.json"):
    """smoke.py (0.6) writes models.json with whichever models actually passed its test --
    load them here so router constants never drift from what was verified. Falls back to the
    Pinned-decision defaults only if smoke.py hasn't run yet (fresh checkout, not yet gated)."""
    try:
        m = json.load(open(path))
        return m["frontier_model"], m["cheap_model"]
    except (FileNotFoundError, KeyError):
        return "claude-sonnet-5", "openai-gpt-5-mini"  # run smoke.py first

FRONTIER_MODEL, CHEAP_MODEL = _load_models()
MAX_TOKENS = 300
TEMPERATURE = 0
PROMOTION_THRESHOLD = 2                 # verified cheap passes to promote
COOLDOWN_LENGTH = 3                     # requests before cheap re-trial eligible

class FPState(str, Enum):
    NEW = "NEW"; SHADOW = "SHADOW"; PROMOTED = "PROMOTED"; COOLDOWN = "COOLDOWN"

@dataclass
class FingerprintRecord:
    fingerprint_id: str; task_family: str
    state: FPState = FPState.NEW; cheap_pass_count: int = 0; cooldown_remaining: int = 0

@dataclass
class RouteDecision:
    task_id: str; fingerprint_id: str; state_before: FPState; state_after: FPState
    route_model: str; shadow_model: str | None; escalated: bool
    output_text: str; passed: bool | None; calls: list[dict]  # every ai_complete() call made

class RouterPolicy:
    """Stateful across one benchmark/demo run. remember_case_fn/recall_cases_fn are already
    resolved by the CALLER to either the real agent-case functions or the Phase-0 fallback
    (fingerprinted user-mode memory) based on smoke.py's exit code -- this class never branches
    on agent_mode itself, so read and write paths can never disagree (dry-run bug fixed)."""

    def __init__(self, ai_complete_fn, remember_case_fn, recall_cases_fn, mark_graded_fn,
                 agent_id: str = "broke", run_id: str = "adaptive",
                 index_path: str = "case_index.jsonl"):
        self.ai_complete, self.remember_case = ai_complete_fn, remember_case_fn
        self.recall_cases, self.mark_graded = recall_cases_fn, mark_graded_fn
        self.agent_id, self.run_id, self.index_path = agent_id, run_id, index_path
        self._records: dict[str, FingerprintRecord] = {}

    def fingerprint(self, task_family: str, seed_text: str) -> str:
        return f"{task_family}:{seed_text}"   # deterministic — see Pinned decision #5

    def route(self, task: dict) -> RouteDecision:
        fp_id = self.fingerprint(task["task_family"], task["fingerprint_seed"])
        rec = self._records.get(fp_id)
        if rec is None:
            rec = FingerprintRecord(fp_id, task["task_family"])  # defaults to NEW; never reset an existing record
        state_before, calls = rec.state, []

        if rec.state in (FPState.NEW, FPState.SHADOW):
            frontier_text, fu, f_pass = self._call_and_grade(FRONTIER_MODEL, task, "route_frontier", fp_id); calls.append(fu)
            cheap_text, cu, cheap_pass = self._call_and_grade(CHEAP_MODEL, task, "route_shadow", fp_id); calls.append(cu)
            if cheap_pass: rec.cheap_pass_count += 1
            rec.state = FPState.PROMOTED if rec.cheap_pass_count >= PROMOTION_THRESHOLD else FPState.SHADOW
            route_model, shadow_model, escalated, output_text, passed = FRONTIER_MODEL, CHEAP_MODEL, False, frontier_text, f_pass
            self._log_case(fp_id, task, "shadow_eval", cheap_pass, cu)

        elif rec.state == FPState.PROMOTED:
            cheap_text, cu, cheap_pass = self._call_and_grade(CHEAP_MODEL, task, "route_cheap", fp_id); calls.append(cu)
            if cheap_pass:
                route_model, shadow_model, escalated, output_text, passed = CHEAP_MODEL, None, False, cheap_text, True
            else:
                frontier_text, fu, f_pass = self._call_and_grade(FRONTIER_MODEL, task, "route_escalation", fp_id); calls.append(fu)
                route_model, shadow_model, escalated, output_text, passed = FRONTIER_MODEL, None, True, frontier_text, f_pass
                rec.state, rec.cooldown_remaining = FPState.COOLDOWN, COOLDOWN_LENGTH
            self._log_case(fp_id, task, "promoted_eval", cheap_pass, cu)

        else:  # COOLDOWN
            frontier_text, fu, f_pass = self._call_and_grade(FRONTIER_MODEL, task, "route_frontier", fp_id); calls.append(fu)
            route_model, shadow_model, escalated, output_text, passed = FRONTIER_MODEL, None, False, frontier_text, f_pass
            rec.cooldown_remaining -= 1
            if rec.cooldown_remaining <= 0:
                rec.state, rec.cheap_pass_count = FPState.SHADOW, 0
            self._log_case(fp_id, task, "cooldown_tick", None, fu)

        self._records[fp_id] = rec
        return RouteDecision(task["task_id"], fp_id, state_before, rec.state, route_model,
                              shadow_model, escalated, output_text, passed, calls)

    def _call_and_grade(self, model, task, purpose, fp_id):
        text, usage = self.ai_complete(model, task["prompt"], purpose, run_id=self.run_id,
                                        agent_tag=f"broke:{purpose}",
                                        extra={"task_id": task["task_id"], "fingerprint_id": fp_id,
                                               "task_family": task["task_family"]},
                                        max_tokens=MAX_TOKENS, temperature=TEMPERATURE)
        passed = None
        if task.get("gold"):
            from fixtures.graders import GRADERS
            passed = GRADERS[task["task_family"]](text, task["gold"])
            self.mark_graded(usage["call_id"], passed)
        return text, usage, passed

    def _log_case(self, fp_id, task, event, passed, usage):
        result = 'PASS' if passed else 'FAIL' if passed is False else 'N/A'
        # Structured tail line (Task 3): add() has no metadata field, so call_id/task_id ride
        # inside the message text itself -- mem.parse_case_ids() parses them back out of whatever
        # EverOS's own extraction preserves. This is a best-effort join; llm_call_log.call_id
        # (set directly by ai_complete/mark_graded) is the actual authoritative source.
        content = (f"Routed {task['task_family']}/{task['fingerprint_seed']} (fingerprint {fp_id}) "
                   f"to {usage.get('model')} for event {event}, result {result}, "
                   f"{usage.get('prompt_tokens')}+{usage.get('completion_tokens')} tokens."
                   f"|call_id={usage.get('call_id')}|task_id={task['task_id']}")
        # ONE session per case write (run:fingerprint:task) -- a recalled case's originating
        # session_id therefore maps to exactly ONE index row and ONE call_id: unambiguous join,
        # no reliance on what the extractor kept. self.index_path is a constructor arg
        # (default "case_index.jsonl"); benchmark.py passes os.path.join(out_dir, "case_index.jsonl")
        # so acceptance scratch runs never write into the production working directory.
        session_id = f"{self.run_id}:{fp_id}:{task['task_id']}"
        with open(self.index_path, "a") as f:
            f.write(json.dumps({"session_id": session_id, "call_id": usage.get("call_id"),
                                 "task_id": task["task_id"], "fingerprint_id": fp_id,
                                 "ts": time.time()}) + "\n")
        self.remember_case(self.agent_id, session_id, [{"role": "assistant", "content": content}])

    def save_state(self, path: str = "policy_state.json") -> None:
        data = {"run_id": self.run_id, "agent_id": self.agent_id,
                "fingerprints": {fp: {**asdict(r), "state": r.state.value} for fp, r in self._records.items()}}
        json.dump(data, open(path, "w"), indent=2)

    def load_state(self, path: str = "policy_state.json") -> None:
        try:
            data = json.load(open(path))
        except FileNotFoundError:
            return
        for fp, r in data.get("fingerprints", {}).items():
            self._records[fp] = FingerprintRecord(fp, r["task_family"], FPState(r["state"]),
                                                    r["cheap_pass_count"], r["cooldown_remaining"])

    def record_snapshot(self, fp_id: str) -> dict:
        """Full serialized FingerprintRecord, embedded in each adaptive replay event ("record_after")
        so resume can RESTORE state instead of re-applying transitions (see benchmark.py)."""
        r = self._records[fp_id]
        return {**asdict(r), "state": r.state.value}

    def restore_records(self, snapshots: dict) -> None:
        """snapshots: {fingerprint_id: record_after dict} -- last event wins, applied verbatim."""
        for fp, r in snapshots.items():
            self._records[fp] = FingerprintRecord(fp, r["task_family"], FPState(r["state"]),
                                                    r["cheap_pass_count"], r["cooldown_remaining"])
```

**Acceptance check:**
```bash
python -c "
from router_policy import RouterPolicy, FPState
def fake_ai(model, prompt, purpose, **kw):
    return ('{\"field\":\"total_due\",\"value\":42}', {'call_id':'c1','model': model,'prompt_tokens':10,'completion_tokens':5,'credits_est':0.001})
def fake_remember(*a,**k): pass
def fake_recall(*a,**k): return []
def fake_mark_graded(*a,**k): pass
import json, os
# Assert against the smoke-selected cheap model, never a literal -- on accounts where smoke fell
# back (e.g. to mistral-7b), the acceptance must still pass with the model actually in service.
CHEAP = json.load(open('models.json'))['cheap_model'] if os.path.exists('models.json') else 'openai-gpt-5-mini'
p = RouterPolicy(fake_ai, fake_remember, fake_recall, fake_mark_graded, run_id='test')
t = {'task_id':'jx-001','task_family':'json_extraction','prompt':'x','gold':{'field':'total_due','value':42},'fingerprint_seed':'inv'}
d1 = p.route(t)
assert d1.state_after == FPState.SHADOW, d1.state_after
d2 = p.route({**t,'task_id':'jx-002'})
assert d2.state_after == FPState.PROMOTED, d2.state_after
d3 = p.route({**t,'task_id':'jx-003'})
assert d3.route_model == CHEAP and d3.shadow_model is None, d3
p.save_state('/tmp/_broke_test_state.json')
p2 = RouterPolicy(fake_ai, fake_remember, fake_recall, fake_mark_graded, run_id='test2')
p2.load_state('/tmp/_broke_test_state.json')
d4 = p2.route({**t,'task_id':'jx-004'})
assert d4.state_before == FPState.PROMOTED and d4.route_model == CHEAP, d4
print('OK', [d.state_after for d in (d1,d2,d3)], 'persisted:', d4.state_before)"
```
Expected: `OK [FPState.SHADOW, FPState.PROMOTED, FPState.PROMOTED] persisted: FPState.PROMOTED`. The 4th assertion proves a FRESH `RouterPolicy` instance (simulating `api.py`'s own process) recovers `PROMOTED` state purely from `policy_state.json`, which is what makes the live demo call route cheap.

---

### Task 3 — Agent-case payload spec + case→outcome join
**Lane A** · **Est: 10 min** — the contract is already embedded as the docstring at the top of Task 2's `router_policy.py`, the `extra=` payload wired into `_call_and_grade`, and the `passed` column + `mark_graded()` wired into `snow.py`/`router_policy.py`. This task is verification only.

**Primary source of truth (no parsing needed):** every `ai_complete()` call already carries `extra={"task_id","fingerprint_id","task_family"}` and gets `passed` set via `call_id` directly — this join needs no EverOS involvement at all:
```sql
SELECT call_id, model, purpose, passed, prompt_tokens, completion_tokens, extra:fingerprint_id::string AS fingerprint_id
FROM llm_call_log WHERE run_id = '<run_id>' ORDER BY ts;
```

**Secondary, EverOS-side join (reliable — does NOT depend on extraction preserving anything):**
`_log_case()` (Task 2) also appends one line to a local `case_index.jsonl` at write time:
`{"session_id": "<run_id>:<fp_id>:<task_id>", "call_id": ..., "task_id": ..., "fingerprint_id": ..., "ts": ...}` — one EverOS session per case write, so a recalled case's originating `session_id` maps to one logical index row. The file is append-only; a crash-retry may append a duplicate row for the same session, so readers ALWAYS take the last row per `session_id` (last-write-wins — duplicates differ only in `call_id`, and the last one is the call whose event actually made it into `replay_events.jsonl`).
Recalled cases carry their originating `session_id` (a documented EverOS search-result field), so the
join is: `case["session_id"]` → `case_index.jsonl` rows for that session → `llm_call_log.call_id` —
reliable regardless of what EverOS's extraction kept, because the index is written by us, not by the
extractor. (Add `case_index.jsonl` to `.gitignore`; `seed.py --reset` deletes it with the other state.)
The embedded `"...|call_id=<uuid>|task_id=<id>"` tail line + `mem.parse_case_ids(case)` remains as a
best-effort per-case refinement when extraction preserves it:
```python
call_id, task_id = mem.parse_case_ids(case)  # case is one dict from mem.recall_cases()
```
```sql
SELECT call_id, model, purpose, passed, prompt_tokens, completion_tokens,
       extra:fingerprint_id::string AS fingerprint_id, extra:task_id::string AS task_id
FROM llm_call_log WHERE call_id = '<call_id from mem.parse_case_ids(case)>';
```

**Acceptance check:**
```bash
grep -q "AGENT-CASE PAYLOAD CONTRACT" router_policy.py && \
grep -q 'extra={"task_id"' router_policy.py && \
grep -q "def mark_graded" snow.py && \
grep -q "def parse_case_ids" mem.py && \
grep -q "call_id={usage.get(.call_id.)}" router_policy.py && echo OK
```
Expected: `OK`

---

### Task 4 — `benchmark.py` (pre-show paired run, captures replay events)
**Lane A** · **Est: 20 min for the default 30-task run** (plus an optional ~35 min stretch slot for the 150-task run if ahead of schedule — see hour-by-hour schedule).

Runs BOTH arms over a fixed task stream, same order, writing `replay_events.jsonl` **incrementally** (one line appended per completed task, flushed immediately — a crash mid-run leaves a valid, resumable file; rerunning the same command skips `task_id`s already present for that arm) plus `benchmark_summary.json`, `policy_state.json` (persisted promotion state, see Task 2), and `cases_snapshot.json` (real EverOS case evidence for the UI, captured now so replay mode never queries EverOS live). Each event is contract-complete: `run_id, task_id, prompt_hash, output, usage/calls, route/state, passed, ts`.

**True call counts (not "~300" — recomputed honestly):** DEFAULT 30-task run = 30 frontier-baseline calls + ~42 adaptive-arm calls (6 fingerprints × [2 shadow-stage reps × 2 calls + 3 promoted-stage reps × 1 call], assuming clean promotion with no failures) = **~72 real Cortex calls**, plus **30 synchronous EverOS case writes** (`_log_case()` fires once per task, every branch — not "6", that was fingerprint count, not write count) and up to 6 `cases_snapshot` reads (one per fingerprint that reaches `PROMOTED`). STRETCH 150-task run = 150 + 210 (30 fingerprints × 7) = **~360 real Cortex calls**, 150 EverOS case writes, up to 30 `cases_snapshot` reads.

```python
# benchmark.py
"""DEFAULT: fixtures/tasks_small.json (30 tasks, ~72 calls). --full: fixtures/tasks.json
(150 tasks, ~360 calls) -- attempt only after a green default run. Incremental + resumable:
rerunning the same command skips task_ids already present in replay_events.jsonl for that arm.
seed.py deletes replay_events.jsonl for a genuinely fresh rebuild; this script never deletes it."""
import argparse, hashlib, json, os, time, uuid
from dotenv import load_dotenv
load_dotenv()
import snow, mem
from router_policy import RouterPolicy, FRONTIER_MODEL
from fixtures.graders import GRADERS

AGENT_MODE = True  # set False if smoke.py exited 2 (Phase-0 fallback) -- see risk table R1
EVENTS_PATH = "replay_events.jsonl"

def _hash(text): return hashlib.sha256(text.encode()).hexdigest()[:16]

def _existing_run_id():
    try: return json.loads(open(EVENTS_PATH).readline())["run_id"]
    except (FileNotFoundError, json.JSONDecodeError, StopIteration): return None

def _done_ids(arm):
    done = set()
    try:
        for line in open(EVENTS_PATH):
            e = json.loads(line)
            if e["arm"] == arm: done.add(e["task_id"])
    except FileNotFoundError: pass
    return done

def _append(event):
    with open(EVENTS_PATH, "a") as f: f.write(json.dumps(event) + "\n"); f.flush()

def _bound_mem_fns():
    """Same normalized adapter shape either way (mem.py's fallback functions match
    recall_cases()'s dict keys exactly) -- see mem.py's fallback adapter comment."""
    return (mem.remember_case, mem.recall_cases) if AGENT_MODE else \
           (mem.remember_case_fallback, mem.recall_cases_fallback)

def run_frontier_baseline_arm(tasks, run_id, resume):
    done = _done_ids("frontier_baseline") if resume else set()
    for t in tasks:
        if t["task_id"] in done: continue
        text, usage = snow.ai_complete(FRONTIER_MODEL, t["prompt"], "baseline_frontier", run_id=run_id,
            agent_tag="broke:baseline", extra={"task_id": t["task_id"]}, max_tokens=300, temperature=0)
        passed = GRADERS[t["task_family"]](text, t["gold"])
        snow.mark_graded(usage["call_id"], passed)
        _append({"arm": "frontier_baseline", "run_id": run_id, "task_id": t["task_id"],
                  "task_family": t["task_family"], "model": FRONTIER_MODEL, "prompt_hash": _hash(t["prompt"]),
                  "output": text, "passed": passed, "usage": usage, "ts": time.time()})

def run_adaptive_arm(tasks, run_id, agent_id, resume, state_path):
    remember_fn, recall_fn = _bound_mem_fns()
    policy = RouterPolicy(snow.ai_complete, remember_fn, recall_fn, snow.mark_graded, agent_id=agent_id, run_id=run_id,
                          index_path=os.path.join(os.path.dirname(state_path) or ".", "case_index.jsonl"))
    if resume:
        # CRITICAL: rebuild promotion state from the EVENT LOG's embedded snapshots, never by
        # re-applying transitions. For each fingerprint, the LAST adaptive event's "record_after"
        # is restored verbatim -- idempotent no matter how many times a task was retried, so pass
        # counts and cooldowns can never double. This is also what makes the acceptance check's
        # mandatory second `python benchmark.py` run safe: with nothing left to do, it restores and
        # re-saves the SAME state instead of erasing it. (policy.load_state(state_path) is only the
        # fallback if the events file is missing but a state file exists.)
        snapshots = {}
        if os.path.exists(EVENTS_PATH):
            for line in open(EVENTS_PATH):
                e = json.loads(line)
                if e["arm"] == "adaptive" and "record_after" in e:
                    snapshots[e["fingerprint_id"]] = e["record_after"]
        if snapshots:
            policy.restore_records(snapshots)
        elif not os.path.exists(EVENTS_PATH):
            policy.load_state(state_path)   # no event log at all -> state file is the only record
        # else: the event log exists but holds no adaptive events yet (e.g. crash during the
        # baseline arm) -- this run's adaptive arm hasn't started, so a BLANK policy is correct;
        # a stale state file from an older run must NOT leak in here.
    done = _done_ids("adaptive") if resume else set()
    for t in tasks:
        if t["task_id"] in done: continue
        d = policy.route(t)
        # Crash-safety via SNAPSHOTS, not transition replay: every adaptive event embeds the full
        # post-route FingerprintRecord ("record_after"). replay_events.jsonl is the single source of
        # truth; resume RESTORES the last snapshot per fingerprint (idempotent by construction --
        # nothing is ever re-applied, so pass counts / cooldowns can't double). A crash after route()
        # but before _append re-runs that task on resume: a few redundant cents, and its retry's
        # snapshot/index rows simply supersede the orphaned ones (last-row-wins, see Task 3).
        _append({"arm": "adaptive", "run_id": run_id, "task_id": t["task_id"], "task_family": t["task_family"],
                  "prompt_hash": _hash(t["prompt"]), "fingerprint_id": d.fingerprint_id,
                  "state_before": d.state_before, "state_after": d.state_after, "route_model": d.route_model,
                  "shadow_model": d.shadow_model, "escalated": d.escalated, "output": d.output_text,
                  "passed": d.passed, "calls": d.calls,
                  "record_after": policy.record_snapshot(d.fingerprint_id),
                  "total_credits_est": sum(c.get("credits_est", 0) for c in d.calls), "ts": time.time()})
        policy.save_state(state_path)   # derived cache for api.py -- events remain the truth
    return policy

def snapshot_cases(policy, agent_id, out_dir):
    _, recall_fn = _bound_mem_fns()
    snapshot = [{"fingerprint_id": fp, "cases": recall_fn(fp.split(":", 1)[1], agent_id=agent_id, top_k=3)}
                for fp, r in policy._records.items() if r.state.value == "PROMOTED"]
    json.dump(snapshot, open(os.path.join(out_dir, "cases_snapshot.json"), "w"), indent=2)
    print(f"wrote cases_snapshot.json: {len(snapshot)} promoted fingerprints")

def main():
    global EVENTS_PATH
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="150-task stretch fixture, not the 30-task default")
    ap.add_argument("--no-resume", action="store_true")
    ap.add_argument("--state-path", default="policy_state.json",
                     help="promotion-state file. Acceptance reruns point this at a scratch dir "
                          "so the real pre-show run's policy_state.json is never touched.")
    ap.add_argument("--out-dir", default=".",
                     help="directory for ALL run artifacts (replay_events.jsonl, cases_snapshot.json, "
                          "benchmark_summary.json). Acceptance reruns use a /tmp scratch dir so no "
                          "production artifact is ever deleted or overwritten by a check.")
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    EVENTS_PATH = os.path.join(args.out_dir, "replay_events.jsonl")
    tasks = json.load(open("fixtures/tasks.json" if args.full else "fixtures/tasks_small.json"))
    resume = not args.no_resume
    run_id = (resume and _existing_run_id()) or f"benchmark-{uuid.uuid4().hex[:8]}"
    agent_id = f"broke-{run_id}"   # fresh EverOS agent namespace per run (Contract §10)

    print(f"Frontier baseline arm ({len(tasks)} tasks, run_id={run_id}, resume={resume})...")
    run_frontier_baseline_arm(tasks, run_id, resume)
    print(f"Adaptive arm ({len(tasks)} tasks, agent_id={agent_id})...")
    policy = run_adaptive_arm(tasks, run_id, agent_id, resume, args.state_path)
    policy.save_state(args.state_path)
    snapshot_cases(policy, agent_id, args.out_dir)

    all_events = [json.loads(l) for l in open(EVENTS_PATH)]
    frontier_events = [e for e in all_events if e["arm"] == "frontier_baseline"]
    adaptive_events = [e for e in all_events if e["arm"] == "adaptive"]
    frontier_total = sum(e["usage"]["credits_est"] for e in frontier_events)
    adaptive_total = sum(e["total_credits_est"] for e in adaptive_events)
    summary = {"run_id": run_id, "n_tasks": len(tasks),
        "frontier_total_credits_est": frontier_total, "adaptive_total_credits_est": adaptive_total,
        "savings_pct": 1 - (adaptive_total / frontier_total) if frontier_total else 0,
        "frontier_score": sum(1 for e in frontier_events if e["passed"]) / len(frontier_events),
        "adaptive_score": sum(1 for e in adaptive_events if e["passed"]) / len(adaptive_events)}
    json.dump(summary, open(os.path.join(args.out_dir, "benchmark_summary.json"), "w"), indent=2)
    print(json.dumps(summary, indent=2))

if __name__ == "__main__": main()
```

**Acceptance check** (FULLY isolated in a `/tmp` scratch dir — state AND all artifacts. It deletes and
rewrites nothing in the working directory, so running it after the real pre-show benchmark is safe by
construction; the real `policy_state.json`, `replay_events.jsonl`, `cases_snapshot.json`, and
`benchmark_summary.json` are never touched):
```bash
SCRATCH=/tmp/_broke_scratch && rm -rf $SCRATCH && mkdir -p $SCRATCH
python benchmark.py --state-path $SCRATCH/state.json --out-dir $SCRATCH   # DEFAULT 30-task run
wc -l $SCRATCH/replay_events.jsonl       # expect 60 (30 frontier + 30 adaptive)
python -c "
import json
e = json.loads(open('/tmp/_broke_scratch/replay_events.jsonl').readline())
for k in ('run_id','task_id','prompt_hash','output','ts','arm'): assert k in e, k
print('contract-complete: OK')"
python -c "import json; s=json.load(open('/tmp/_broke_scratch/state.json')); assert s['fingerprints']; print('state OK, agent_id=', s['agent_id'])"
python benchmark.py --state-path $SCRATCH/state.json --out-dir $SCRATCH   # resume: everything already done
wc -l $SCRATCH/replay_events.jsonl       # STILL 60 -- proves resume did not duplicate work
python -c "import json; s=json.load(open('/tmp/_broke_scratch/state.json')); assert s['fingerprints']; print('state STILL populated after no-op resume:', len(s['fingerprints']), 'fingerprints')"
```
Expected: first `wc -l` → `60 replay_events.jsonl`; `contract-complete: OK`; `state OK, agent_id= broke-benchmark-...`; second `wc -l` → `60 replay_events.jsonl` unchanged; final line → `state STILL populated after no-op resume: 6 fingerprints` (NOT 0 — this is the regression check: a resume that found nothing new to do must not erase prior promotion state).

---

### Task 5 — `/route` FastAPI endpoint (`api.py`)
**Lane B owns this file** (reassigned from an earlier draft's inconsistent Lane A/Lane B split — Lane B runs it in parallel with Lane A's Task 2/Task 4, and it only needs `router_policy.py`'s documented interface, not Lane A physically finishing first, since the acceptance check below doesn't depend on real promotion state). · **Est: 25 min**

`gold` is REQUIRED (Pinned decision #6) — every `/route` call in this build must be gradable so the state machine can run; there is no ungraded path. At startup, `api.py` loads `policy_state.json` (written by Task 4's `benchmark.py`) so a fingerprint promoted during the pre-show run is already `PROMOTED` when the live demo fires against it.

```python
# api.py — documented non-streaming /route endpoint. NOT claimed OpenAI-compatible. gold is
# REQUIRED and family-shape-validated (422 on mismatch, never a 500, never ungraded promotion).
import json as _json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Literal
import uuid
from dotenv import load_dotenv
load_dotenv()
from jsonschema import validate, ValidationError
import snow, mem
from router_policy import RouterPolicy

AGENT_MODE = True  # must match benchmark.py's setting (see risk table R1)
app = FastAPI(title="Broke /route")
_remember_fn, _recall_fn = (mem.remember_case, mem.recall_cases) if AGENT_MODE else \
                            (mem.remember_case_fallback, mem.recall_cases_fallback)
_run_id = f"live-{uuid.uuid4().hex[:6]}"   # fresh per server process start

# Read policy_state.json's OWN agent_id before constructing RouterPolicy, so live-call case
# writes land in the SAME EverOS namespace the pre-show benchmark used (benchmark.py mints a
# fresh agent_id = f"broke-{run_id}" per run -- api.py must match it, not hardcode "broke").
try:
    _state = _json.load(open("policy_state.json"))
    _agent_id = _state.get("agent_id", "broke")
except FileNotFoundError:
    _agent_id = "broke"  # benchmark.py hasn't run yet

_policy = RouterPolicy(snow.ai_complete, _remember_fn, _recall_fn, snow.mark_graded,
                        agent_id=_agent_id, run_id=_run_id)
_policy.load_state("policy_state.json")   # <-- this is what lets the live call route cheap

GOLD_SCHEMAS = {
    "json_extraction": {"type": "object", "required": ["field", "value"],
                         "properties": {"field": {"type": "string"}, "value": {}}},
    "classification": {"type": "object", "required": ["label"], "properties": {"label": {"type": "string"}}},
    "summarization": {"type": "object", "required": ["required_facts"],
                       "properties": {"required_facts": {"type": "array", "minItems": 1,
                                                           "items": {"type": "string"}}}},
}

class RouteRequest(BaseModel):
    task_family: Literal["json_extraction", "classification", "summarization"]  # REQUIRED
    prompt: str
    fingerprint_seed: str
    gold: dict   # REQUIRED — this build has no ungraded path (Pinned decision #6)

class RouteResponse(BaseModel):
    output: str; route_model: str; escalated: bool
    fingerprint_id: str; state_before: str; state_after: str; passed: bool | None; credits_est: float

@app.post("/route", response_model=RouteResponse)
def route(req: RouteRequest):
    try:
        validate(instance=req.gold, schema=GOLD_SCHEMAS[req.task_family])
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=f"gold does not match {req.task_family} schema: {e.message}")
    task = {"task_id": f"live-{uuid.uuid4().hex[:6]}", "task_family": req.task_family,
            "prompt": req.prompt, "fingerprint_seed": req.fingerprint_seed, "gold": req.gold}
    try:
        d = _policy.route(task)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return RouteResponse(output=d.output_text, route_model=d.route_model, escalated=d.escalated,
        fingerprint_id=d.fingerprint_id, state_before=d.state_before, state_after=d.state_after,
        passed=d.passed, credits_est=sum(c.get("credits_est", 0) for c in d.calls))
```

**Acceptance check:**
```bash
uvicorn api:app --port 8010 & sleep 2
curl -s -X POST localhost:8010/route -H 'Content-Type: application/json' -d '{
  "task_family": "classification",
  "prompt": "Classify this text as exactly one word from [\"positive\",\"negative\",\"neutral\"]. Respond with ONLY that one word. Text: '"'"'I love this product!'"'"'",
  "fingerprint_seed": "sentiment-demo-live",
  "gold": {"label": "positive"}}' | python -m json.tool
curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8010/route -H 'Content-Type: application/json' -d '{
  "task_family": "classification", "prompt": "x", "fingerprint_seed": "bad-gold-test", "gold": {}}'
kill %1
```
Expected: first `curl` returns JSON with `route_model`, `escalated`, `fingerprint_id`, `state_before`, `state_after`, `passed`, `credits_est` populated; a fresh `fingerprint_seed` never seen in `policy_state.json` shows `state_before: "NEW"` and `route_model: "claude-sonnet-5"`. Second `curl` (malformed `gold: {}`) returns `422` — never `500`, never a promotion decision. For the ON-STAGE live call, use a `fingerprint_seed` that IS a key in `policy_state.json` with `state: "PROMOTED"` (e.g. `invoice_total` or `sentiment` from the default fixture) — that call shows `state_before: "PROMOTED"` and `route_model: "openai-gpt-5-mini"`.

---

### Task 6 — Streamlit UI (`app.py`)
**Lane B** · **Est: 75 min**

Modes: `streamlit run app.py -- --replay` (default; playback is **PAUSED at frame 0** until the operator clicks "Start replay" — no autorefresh timer runs before that, so zero external calls happen just from opening the page) and `streamlit run app.py -- --live` (also shows a live-call panel that POSTs to `api.py` on `:8010` — run `uvicorn api:app --port 8010 &` first). ≤2 screens per contract, both on one page here (stacked, not tabs) since the content is short.

**Cost race (headline).** Two giant `st.metric` tickers: **"Frontier-only cost"** / **"Broke (adaptive) cost"**, advancing task-by-task only while `st.session_state.playing` is `True` (toggled by the Start/Pause button — this is the pause-at-frame-zero control the dry-run flagged as missing). Below: the cost-ratio curve — `st.line_chart` of **`adaptive_cost / frontier_cost`** (NOT `1 - ratio`; plotting the ratio directly is what bends DOWN as promotions accrue — the dry-run caught `1 - ratio` bending the wrong direction).

**Cases-learned panel.** "Cases learned" counter = fingerprints whose MOST RECENT state at the current frame is `PROMOTED` (not "ever reached PROMOTED" — a fingerprint that later cooled down must not still count; the dry-run caught this too). Below it, a table sourced from `cases_snapshot.json` (real EverOS `agent_cases` evidence captured by `benchmark.py`: `memory_id`, `session_id`, `score`, `task_intent` — actual retrieval evidence, not routing-decision rows relabeled).

**Receipts.** Gated behind an explicit `st.button` click — never called during autorefresh — so `--replay` truly issues zero external calls unless the operator asks for it.

**Live call.** Only rendered when `--live` is passed. A text input for `fingerprint_seed` (pre-fill with one already `PROMOTED` in `policy_state.json`) and a button that POSTs to `api.py`'s `/route`; the result is shown with an explicit **"LIVE"** badge and a caption that it is NOT included in the cost tickers above (those reflect only the replayed benchmark) — this is the replay-vs-live marker the contract requires.

**Three-cost-tier labels — rendered as literal `st.caption()` text in the code below, not just described in prose** (the dry-run found the prose-only version was never actually printed):
| Tier | Where | Label |
|---|---|---|
| (a) measured tokens | caption under the curve | "measured tokens (show_details=TRUE) → estimated credits" |
| (b) estimated credits/$ | caption under each ticker | "estimated credits/$ = measured tokens × published rate" |
| (c) billed credits | caption after the receipts button fires | "billed credits (Snowflake metering, ~2-5 min lag) — corroborates prior runs, not a live ticker" |

```python
# app.py
import argparse, json, requests
import streamlit as st, pandas as pd
from streamlit_autorefresh import st_autorefresh
import snow   # safe at module level -- snow.py makes no network calls on import, only inside functions

def usd(credits: float) -> float:
    """The ONE dollar-conversion helper -- no literal `* 2` anywhere, so changing
    snow.CREDIT_PRICE_USD (e.g. to $2.20 for home-region routing) propagates everywhere."""
    return credits * snow.CREDIT_PRICE_USD

st.set_page_config(page_title="Broke", layout="wide")
parser = argparse.ArgumentParser()
parser.add_argument("--replay", action="store_true", default=True)
parser.add_argument("--live", action="store_true", help="show the live-call panel (needs api.py on :8010)")
args, _ = parser.parse_known_args()

@st.cache_data
def load_events(): return [json.loads(l) for l in open("replay_events.jsonl")]
@st.cache_data
def load_cases_snapshot():
    try: return json.load(open("cases_snapshot.json"))
    except FileNotFoundError: return []

events = load_events()
adaptive = [e for e in events if e["arm"] == "adaptive"]
frontier = [e for e in events if e["arm"] == "frontier_baseline"]

st.title("Broke")
st.session_state.setdefault("frame", 0)
st.session_state.setdefault("playing", False)
c_start, c_reset, _ = st.columns([1, 1, 4])
if c_start.button("Pause" if st.session_state.playing else "Start replay"):
    st.session_state.playing = not st.session_state.playing
if c_reset.button("Reset to frame 0"):
    st.session_state.frame, st.session_state.playing = 0, False
if st.session_state.playing:
    st_autorefresh(interval=300, key="ticker_refresh")
    st.session_state.frame = min(st.session_state.frame + 1, len(adaptive))
frame = st.session_state.frame
st.caption(f"Frame {frame}/{len(adaptive)} — measured pre-show benchmark run (replayed)")

cum_a = sum(e["total_credits_est"] for e in adaptive[:frame])
cum_f = sum(e["usage"]["credits_est"] for e in frontier[:frame])
c1, c2 = st.columns(2)
c1.metric("Frontier-only cost", f"{cum_f:.4f} cr (${usd(cum_f):.2f})")
c1.caption("estimated credits/$ = measured tokens × published rate")
c2.metric("Broke (adaptive) cost", f"{cum_a:.4f} cr (${usd(cum_a):.2f})")
c2.caption("estimated credits/$ = measured tokens × published rate")

df = pd.DataFrame({"task": range(1, frame + 1), "cost ratio adaptive/frontier (lower=cheaper)": [
    (sum(e["total_credits_est"] for e in adaptive[:i+1]) /
     max(sum(e["usage"]["credits_est"] for e in frontier[:i+1]), 1e-9))
    for i in range(frame)]})
st.line_chart(df.set_index("task"))
st.caption("measured tokens (show_details=TRUE) → estimated credits")

latest_state = {}
for e in adaptive[:frame]: latest_state[e["fingerprint_id"]] = e["state_after"]
st.metric("Cases learned (fingerprints CURRENTLY promoted)",
          sum(1 for s in latest_state.values() if s == "PROMOTED"))

snapshot = load_cases_snapshot()
rows = [{"fingerprint_id": e["fingerprint_id"], "memory_id": c["id"], "session_id": c["session_id"],
         "score": c["score"], "task_intent": c["task_intent"]} for e in snapshot for c in e["cases"]]
st.dataframe(pd.DataFrame(rows) if rows else pd.DataFrame({"info": ["run benchmark.py to populate"]}))

# Frame-0 crash fix: pd.DataFrame([]) (an empty LIST of dicts, e.g. adaptive[:0]) has NO
# inferred columns at all -- selecting named columns from it raises KeyError. Pass columns=
# explicitly so the frame is well-formed even with 0 rows, THEN guard on .empty so the paused
# view (frame 0, before Start is clicked) renders a friendly message instead of a bare table.
ADAPTIVE_COLS = ["fingerprint_id", "task_family", "state_before", "state_after", "route_model", "escalated"]
df_adaptive = pd.DataFrame(adaptive[:frame], columns=ADAPTIVE_COLS)
if not df_adaptive.empty:
    st.dataframe(df_adaptive.tail(15))
else:
    st.info("No routing decisions yet — click Start replay above.")

if st.button("Load receipts (live Snowflake query — not part of replay)"):
    st.dataframe(pd.DataFrame(snow.billed_credits_since(60)))
    st.caption("billed credits (Snowflake metering, ~2-5 min lag) — corroborates prior runs, not a live ticker")

if args.live:
    st.subheader("LIVE routing decision")
    seed = st.text_input("fingerprint_seed (use one PROMOTED in policy_state.json)", value="invoice_total")
    if st.button("Fire live /route call"):
        resp = requests.post("http://localhost:8010/route", json={
            "task_family": "json_extraction", "fingerprint_seed": seed,
            "prompt": ("Extract the total_due from this text. Respond with ONLY a JSON object of the form "
                       '{"field": "total_due", "value": <value>}. '
                       "Text: 'Acme Corp record #4471. Total Due: $88.20.'"),
            "gold": {"field": "total_due", "value": 88.20}})
        data = resp.json()
        st.json(data)
        st.success(f"LIVE — routed to {data['route_model']}, {data['credits_est']:.5f} credits — "
                   f"NOT included in the replayed cost tickers above")
```

**Acceptance check:**
```bash
streamlit run app.py -- --replay & sleep 5
curl -s -o /dev/null -w "%{http_code}" localhost:8501; kill %1
```
Expected: `200`. Streamlit serves `200` even when the page script raises (the error renders client-side, not as an HTTP error), so this curl check does NOT catch the frame-0 crash — visually confirm on first load, BEFORE clicking Start, that the page shows the tickers at `0.0000 cr`, the "No routing decisions yet" info box (not a red traceback), and the Start button. Separately, with `uvicorn api:app --port 8010 &` running, `streamlit run app.py -- --live` must show the "LIVE routing decision" panel (manual visual check during rehearsal — no headless check for Streamlit interactivity in this build).

---

### Task 7 — `seed.py` and `check_demo.py`
**Lane B** · **Est: 20 min**

`seed.py` deletes the namespaces THIS plan actually writes (`benchmark-%` and `live-%`, not the never-used `demo-%` from an earlier draft), removes `policy_state.json`/`cases_snapshot.json`/`replay_events.jsonl`/`benchmark_summary.json`, and with `--full` also scoped-deletes ALL prior EverOS agent-case data for `agent_id="broke"` (via `mem.delete_agent_cases`) before re-running `benchmark.py` — this is the genuine "wifi died, rebuild everything" button, including a clean EverOS namespace, not just a Snowflake row wipe.
```python
# seed.py
import argparse, os, subprocess, sys
from dotenv import load_dotenv
load_dotenv()
import snow, mem

p = argparse.ArgumentParser()
p.add_argument("--full", action="store_true", help="also wipe EverOS agent cases and rerun benchmark.py")
args = p.parse_args()

conn = snow.get_conn(); cur = conn.cursor()
cur.execute("DELETE FROM llm_call_log WHERE run_id LIKE 'benchmark-%' OR run_id LIKE 'live-%'")
conn.commit()
print("Cleared benchmark-*/live-* llm_call_log rows.")

for f in ("policy_state.json", "cases_snapshot.json", "replay_events.jsonl", "benchmark_summary.json"):
    if os.path.exists(f):
        os.remove(f); print(f"Removed {f}")

if args.full:
    mem.delete_agent_cases("broke")
    print("Scoped-deleted all EverOS agent_id='broke' cases.")
    subprocess.run([sys.executable, "benchmark.py"], check=True)
print("Seed complete. Restart app.py/api.py to pick up fresh state.")
```

`check_demo.py` — the single end-to-end check. Task counts are read from the summary itself (works for either the 30-task default or the 150-task stretch, never hardcoded), and **"same measured score" is gated on an actual equality check** rather than asserted as always true — if frontier and adaptive scores diverge, this fails loudly and the demo copy must switch to reporting both numbers honestly (Pinned decision #8):
```python
# check_demo.py
import json
summary = json.load(open("benchmark_summary.json"))
assert 0 <= summary["savings_pct"] <= 1, summary
n = summary["n_tasks"]
events = [json.loads(l) for l in open("replay_events.jsonl")]
assert len(events) == 2 * n, (len(events), n)   # exactly one frontier + one adaptive event per task

f_score, a_score = summary["frontier_score"], summary["adaptive_score"]
parity = abs(f_score - a_score) < 0.001
print(f"frontier_score={f_score:.3f} adaptive_score={a_score:.3f} parity={parity}")
if not parity:
    print("WARNING: scores diverge — demo copy MUST say the two measured numbers, "
          "NOT 'same measured score' (copy guard, Pinned decision #8).")
print("check_demo OK:", json.dumps(summary, indent=2))
```
**Acceptance check:** `python check_demo.py` → prints the parity line, then `check_demo OK:` + summary JSON, exit 0 regardless of parity result (parity is a copy-guard signal, not a build failure) — but a human MUST read the `parity=` line before rehearsal and adjust the demo script's closing line if `False`.

---

## Hour-by-hour schedule (11:00 start, 16:00 HARD deadline)

The 30-task fixture (`tasks_small.json`) is the DEFAULT critical path. The 150-task fixture is a STRETCH attempted only if the schedule is ahead at 14:30. Task 2 keeps its full 90-minute slot — nothing else is allowed to compress it. 15 minutes before 16:00 are reserved for submission, not build work. Lane ownership: Lane A owns `router_policy.py`/`snow.py` exclusively; Lane B owns `mem.py`/`app.py`/`api.py`/`seed.py`/`check_demo.py` exclusively; Lane B never edits `router_policy.py`.

| Time | Lane A (backend/data) | Lane B (memory/UI/demo) |
|---|---|---|
| 11:00–11:30 | Phase 0 (0.1–0.7) together. **Gate: `python smoke.py` completes (exit 0 all-green, or exit 2 fallback — both are fine to build on). Exit 3 = Déjà Vu PIVOT decision point, decided now, not at 14:30 (risk table item 2: ~20 min to a task plan, Phase 0 fully reused).** | same |
| 11:30–12:15 | Task 1: fixtures + graders (45m) | Task 6 groundwork: Streamlit skeleton, Start/Pause control, on mock data (45m) |
| 12:15–12:30 | **Lunch (both lanes, 15m)** | **Lunch (both lanes, 15m)** |
| 12:30–14:00 | **Task 2: `router_policy.py` — the full 90 minutes, do not compress** | Task 5: `/route` API against the documented interface (25m) → Task 7: `seed.py`/`check_demo.py` (20m) → confirm `mem.py`'s real add/search adapter against the live EverOS key (buffer, remainder) |
| 14:00–14:10 | Task 3: verify payload contract (10m) | (continued EverOS adapter confirmation / buffer) |
| 14:10–14:30 | **Task 4 DEFAULT: `benchmark.py` on `tasks_small.json`** (30 tasks, ~72 real Cortex calls, ~15-20m wall clock) | Waiting on Lane A's output; keep polishing `app.py` against mock data |
| **14:30** | **CUT-LINE CHECK.** The 30-task `replay_events.jsonl`/`policy_state.json`/`benchmark_summary.json` MUST exist and pass `check_demo.py` by now — this is the floor. If ahead: start Task 4 STRETCH (`--full`, 150 tasks, ~35m, ~360 calls). If behind: stop adding scope, fix what's broken. | Same cut-line. Drop-first if behind: (1) live-call panel, (2) cases-snapshot table, (3) receipts button, (4) `seed.py --full`/EverOS wipe path. |
| 14:30–15:05 | Stretch 150-task run if ahead, else stabilize the 30-task artifacts | Wire `app.py` to the REAL `replay_events.jsonl`/`policy_state.json`/`cases_snapshot.json`; start `api.py` (`uvicorn api:app --port 8010 &`) |
| 15:05–15:30 | `python check_demo.py` green; verify the `/route` live-call acceptance check against a `PROMOTED` fingerprint | Joint integration pass — same |
| 15:30–15:45 | **Demo rehearsal, both lanes, timed against the 3-minute script** | same |
| 15:45–16:00 | **Submission buffer — reserved, no new build work.** `git commit`, push, close laptops. | same |

**Cut order if behind:** (1) never attempt the 150-task stretch — stay on the 30-task default, (2) drop the live-call panel and cases-snapshot table (keep the two cost tickers + curve, the core proof), (3) drop `seed.py --full`/EverOS-wipe path (keep the Snowflake-row-only reset), (4) drop `/route`'s response-model polish (keep it functionally correct), (5) last resort — **pivot to Déjà Vu** (not a cut, a different build: reuse Phase 0 wholesale, spend ~20 min building its task plan from `docs/idea-slate-v3.md` T1-2 + `docs/slate-v31-pins.md`, per risk table item 2), decided at 11:30 if the Phase-0 gate exits 3, never at 14:30.

---

## Fixtures spec

DEFAULT: 30 tasks (`fixtures/tasks_small.json`), 6 `fingerprint_seed` slugs (`invoice_total, ticket_id` / `sentiment, priority` / `meeting_notes, incident_report`) × 5 reps, mechanically generated by `fixtures/generate.py` (Task 1). STRETCH: 150 tasks (`fixtures/tasks.json`), all 30 slugs × 5 reps. The 9 examples below illustrate the exact shape `generate.py` produces for the first rep or two of each default slug — actual generation is template + seeded-substitution (Task 1), not hand-typed into the JSON files. Note `json_extraction` gold now carries BOTH `field` and `value` (grader bug fix — see Task 1).

### Family 1 — JSON extraction (expected values)
Gold: `{"field": <expected field name>, "value": <exact value>}`. Grader: parse `{...}` block, validate schema, compare BOTH `field` and `value` (normalized).

```json
{"task_id": "jx-001", "task_family": "json_extraction", "fingerprint_seed": "invoice_total",
 "prompt": "Extract the total_due from this text. Respond with ONLY a JSON object of the form {\"field\": \"total_due\", \"value\": <value>}. Text: 'Acme Corp record #4471. Total Due: $102.06.'",
 "gold": {"field": "total_due", "value": 102.06}}
```
```json
{"task_id": "jx-002", "task_family": "json_extraction", "fingerprint_seed": "invoice_total",
 "prompt": "Extract the total_due from this text. Respond with ONLY a JSON object of the form {\"field\": \"total_due\", \"value\": <value>}. Text: 'Bolt Supply document #9982. Total Due: $45.36.'",
 "gold": {"field": "total_due", "value": 45.36}}
```
```json
{"task_id": "jx-006", "task_family": "json_extraction", "fingerprint_seed": "ticket_id",
 "prompt": "Extract the ticket_id from this text. Respond with ONLY a JSON object of the form {\"field\": \"ticket_id\", \"value\": <value>}. Text: 'Vertex Labs entry #7734. Ticket reference: SUP-88214.'",
 "gold": {"field": "ticket_id", "value": "SUP-88214"}}
```

### Family 2 — Classification (gold labels)
Gold: `{"label": <fixed label set per fingerprint_seed>}`. Grader: ONE combined `strip()` call (punctuation + whitespace together, fixes the dry-run's order-dependent strip bug), lowercase, exact match.

```json
{"task_id": "cl-001", "task_family": "classification", "fingerprint_seed": "sentiment",
 "prompt": "Classify this text as exactly one word from ['positive', 'negative', 'neutral']. Respond with ONLY that one word. Text: 'This blender broke on day two and support never responded.'",
 "gold": {"label": "negative"}}
```
```json
{"task_id": "cl-002", "task_family": "classification", "fingerprint_seed": "sentiment",
 "prompt": "Classify this text as exactly one word from ['positive', 'negative', 'neutral']. Respond with ONLY that one word. Text: 'Solid build quality, does what it says, arrived early.'",
 "gold": {"label": "positive"}}
```
```json
{"task_id": "cl-006", "task_family": "classification", "fingerprint_seed": "priority",
 "prompt": "Classify this text as exactly one word from ['low', 'medium', 'high']. Respond with ONLY that one word. Text: 'Production database returning 500s for all customers right now.'",
 "gold": {"label": "high"}}
```

### Family 3 — Structured summarization (required-fact checklist)
Gold: `{"required_facts": [<literal substrings, case-insensitive, ALL must appear>]}`.

```json
{"task_id": "sm-001", "task_family": "summarization", "fingerprint_seed": "meeting_notes",
 "prompt": "Summarize this note in 2 sentences. Your summary MUST mention all of: api rewrite, sarah, september 15-relevant details. Note: 'Team discussed Q3 roadmap. Decided to delay mobile launch to prioritize the API rewrite. Sarah owns the API rewrite. Target: September 15.'",
 "gold": {"required_facts": ["api rewrite", "sarah", "september 15"]}}
```
```json
{"task_id": "sm-002", "task_family": "summarization", "fingerprint_seed": "meeting_notes",
 "prompt": "Summarize this note in 2 sentences. Your summary MUST mention all of: social-first, devon, october 1-relevant details. Note: 'Marketing sync on launch campaign. Decided social-first over email. Devon owns the campaign. Must go live by October 1.'",
 "gold": {"required_facts": ["social-first", "devon", "october 1"]}}
```
```json
{"task_id": "sm-006", "task_family": "summarization", "fingerprint_seed": "incident_report",
 "prompt": "Summarize this note in 2 sentences. Your summary MUST mention all of: connection pool leak, payments, restart-relevant details. Note: 'At 14:02 UTC checkout began timing out. Root cause: a connection pool leak in payments. Resolved by restarting the pool at 14:41 UTC.'",
 "gold": {"required_facts": ["connection pool leak", "payments", "restart"]}}
```

## benchmark.py spec (recap)
Full code in Task 4. Reads `fixtures/tasks_small.json` (30, DEFAULT) or `fixtures/tasks.json` (150, `--full` STRETCH), fixed order → runs frontier-baseline arm (always `claude-sonnet-5`, `purpose="baseline_frontier"`) and adaptive arm (`RouterPolicy.route()`, 1-2 calls/task) → every call through `snow.ai_complete()` → `llm_call_log` (measured tokens via `show_details=TRUE`) + `snow.mark_graded(call_id, passed)` → writes `replay_events.jsonl` INCREMENTALLY, one contract-complete line per task (`run_id, task_id, prompt_hash, output, usage/calls, route/state, passed, ts` — the ONLY input `app.py --replay` reads, `2 × n_tasks` lines total) + `policy_state.json` (promotion/cooldown state, loaded by `api.py`) + `cases_snapshot.json` (real EverOS case evidence for the UI) + `benchmark_summary.json` (`savings_pct`, `frontier_score`, `adaptive_score`, `n_tasks`). Resumable: rerunning the same command skips already-completed `task_id`s per arm. Run once pre-show; never re-run live during the demo.

---

## 3-minute demo script

*(Before curtain: confirm `check_demo.py`'s `parity=` line — it decides which closing line variant below to use.)*

**[0:00–0:20] App open, replay PAUSED at frame 0 (operator has not clicked Start yet).**
> "This is Broke — a router over Snowflake Cortex models that gets cheaper the more you use it. We ran [N from `benchmark_summary.json`'s `n_tasks`] real graded tasks through two arms: always-frontier, and our adaptive router." [Click "Start replay."] "Watch the tickers."

**[0:20–1:10] Replay animates. Tickers climb; the adaptive/frontier cost-ratio curve bends DOWN.**
> "Every task here is graded — JSON extraction against an exact value and field name, classification against a gold label, summarization against a required-fact checklist. No LLM judging itself. [point at curve] Every new task type gets a frontier answer AND a silent cheap-model shadow call, graded against the same gold. Once a task type proves out twice, we promote it — cheap model only, frontier retired for that fingerprint. That's the curve bending down: adaptive cost divided by frontier cost, falling as promotions land."
> Read the on-screen label once: **"measured pre-show benchmark run — replayed."**

**[1:10–1:40] Cases-learned panel.**
> "This is real EverOS agent-case memory — not a routing-decision table relabeled. [point at the evidence table] Those are actual memory IDs, session IDs, and match scores EverOS returned when we queried it, captured before the show. [point at counter] We've promoted N fingerprints out of 6 seen — cheap-model-only from here forward."

**[1:40–2:30] THE ONE LIVE ROUTING DECISION — "LIVE" badge on screen.**
> "Now, live, one real call." [Type the pre-staged `fingerprint_seed` — one already `PROMOTED` in `policy_state.json` — and click "Fire live /route call."]
> "Watch — it loads the promotion state from our pre-show run, routes straight to gpt-5-mini, skips the frontier call entirely." [Response in ~1-2s; `route_model: "openai-gpt-5-mini"`, `escalated: false`, the green "LIVE" success banner visible, explicitly marked as NOT part of the ticker totals above.]
> "That's real, that's now, priced at Snowflake's own $2.00-per-credit cross-region rate."

**[2:30–2:50] Back to the tickers, final numbers frozen.**
> IF parity (`check_demo.py` showed `parity=True`): "Across the full measured run: same measured score on our fixed benchmark, N% cheaper — and that curve only bends further tomorrow, because every task it sees becomes a case it can reuse."
> IF NOT parity: "Across the full measured run: frontier scored X%, adaptive scored Y% — [state the honest reason, e.g. escalation caught it] — at N% lower cost."

**[2:50–3:00] Closing line (exact, ONLY if parity held):**
> **"Identical accuracy isn't the pitch — same measured score, N% cheaper, and cheaper tomorrow than today."**
> (If parity did not hold, close instead with: **"N% cheaper, honestly scored — X% versus Y%, and we show you the difference, not just the savings."**)

*(N/X/Y are read from `benchmark_summary.json` at rehearsal time — never precommit a number in the script text.)*

---

## Risk table (top 5)

| # | Risk | Trigger | Fallback |
|---|---|---|---|
| 1 | EverOS agent-case `add`/`search` still misbehaves even with the corrected v2 adapter (young API, reported silent-write-failure bug) | `smoke.py` exits 2, or `recall_cases_from_session` returns 0 results from the fresh session during Task 2/4 | Set `AGENT_MODE = False` at the top of `benchmark.py` and `api.py` (both must match — dry-run caught a prior version where write and read paths disagreed). This swaps `remember_case`/`recall_cases` for `mem.remember`/`mem.recall` under `user_id="agent:broke"` — still real EverOS retrieval, just user-mode. `router_policy.py` itself never branches on this; only the caller-supplied functions change. Copy guard: strike "agent-side memory used as designed." |
| 2 | Both EverOS round trips (user-mode AND agent-case) fail outright at Phase 0 | `smoke.py` exits 3 (both round trips failed) | **Honest framing: this is a PIVOT, not a "swap."** No pre-written task plan for Déjà Vu exists in this repo. If triggered at the 11:30 gate: (1) reuse Phase 0 wholesale — `snow.py`, `mem.py`, `smoke.py` are unchanged, since the failure is EverOS-shaped either way and the same modules apply; (2) spend ~20 minutes building a minimal task plan directly from `docs/idea-slate-v3.md`'s "T1-2 Déjà Vu" section + `docs/slate-v31-pins.md`'s Déjà Vu pins (both already fully spec'd — this is transcription/sequencing work, not design work); (3) start Déjà Vu's own Task 1 no later than 11:50. **Decision time: 11:30, immediately after the Phase-0 gate — never 14:30.** |
| 3 | `benchmark.py`'s real Cortex calls (~72 default, ~360 stretch) run long / hit rate limits, artifacts incomplete by 14:30 | 14:30 wall-clock cut-line check | Nothing to cut here anymore — the 30-task default IS the floor (this is why it was made the default, not the stretch). If even the 30-task run is incomplete, rerun `python benchmark.py` (resumable: it skips already-done `task_id`s) rather than starting over. |
| 4 | The live demo call doesn't land on a `PROMOTED` fingerprint | `policy_state.json` missing/stale (Task 4 didn't finish, or `api.py` started before it was written), or the `/route` call returns `claude-sonnet-5` for the pre-staged `fingerprint_seed` | Reconfirm `policy_state.json` exists and contains the exact `fingerprint_seed` string with `"state": "PROMOTED"` before rehearsal (`python -c "import json; print(json.load(open('policy_state.json'))['fingerprints'])"`). Restart `api.py` after any fresh `benchmark.py` run — it only loads state at startup. Last resort: skip live, replay the captured rehearsal call instead — the contract permits "one or two scripted live calls as garnish." |
| 5 | `openai-gpt-5-mini` unavailable in trial region/cross-region config | `ai_complete("openai-gpt-5-mini", ...)` errors as unavailable during Phase 0 or Task 4 | Switch `CHEAP_MODEL` in `router_policy.py` to `mistral-7b` (pinned fallback), globally, once — then rerun `benchmark.py --no-resume` so both arms stay internally consistent (a partial resume with a mixed cheap-model history would corrupt the promotion counts). |

---

## Q&A cheat sheet

**Q1: "Isn't this just picking a cheaper model every time? Where's the actual learning?"**
A: No — every new task type gets BOTH a frontier answer (what the user sees) AND a silent graded shadow call to the cheap model. Only after two verified cheap passes on that specific fingerprint do we retire the frontier call. If the cheap model ever fails on a promoted fingerprint, we escalate that single request back to frontier immediately and cool down for 3 requests before retrying. That's a measured state machine over EverOS agent-case memory, not a static model pick — which is why the cost-per-task curve actually bends over the benchmark instead of being flat.

**Q2: "Your fixture tasks are pretty easy — extraction, classification, summarization with checklists. What about genuinely hard, ambiguous tasks?"**
A: Honest answer: this router is scoped to exactly the task shapes where objective grading is possible without an LLM judge — a deliberate constraint (we explicitly cut code-execution and open-ended tasks). On ambiguous tasks, the grader marks the cheap model's output as failing more often, which is the state machine working as designed — more escalations, longer cooldowns, less promotion. It gets less cheap on hard tasks, not silently wrong. A fourth, murkier task family with a fail-closed structured verifier (like Déjà Vu's or Dividend's) instead of exact-match grading is the natural next step, not something we're claiming already works.

**Q3: "Is your savings percentage including every shadow call, retry, and escalation — or just counting the wins?"**
A: Every call counts. Shadow calls, retries, escalations, cooldown-period frontier calls all hit `llm_call_log` through the same `ai_complete()` path with distinct purpose tags, and the adaptive arm's total in the savings ratio sums ALL of them, not just cheap-model successes. That's why the curve doesn't start at some fake 90% savings on task 1 — early on, shadow-call overhead can briefly make the adaptive arm cost MORE than pure frontier per-task, and the curve only nets positive once enough fingerprints are promoted. We show that honestly; it's in the same measured JSON that produces the headline number.

**Q4: "You said EverOS agent-case memory is the routing brain — but the actual state transitions look like they're keyed on a plain string, not a memory lookup. Is EverOS doing anything real here?"**
A: Fair catch, and we changed this after testing against the real API. EverOS's `agent_cases` search returns LLM-extracted fields (`task_intent`, `approach`, `key_insight`) — there's no caller-supplied exact-match ID field, so we can't safely use semantic search as the identity key for a state machine that has to be exactly reproducible run over run. So identity is deterministic (`task_family:fingerprint_seed`), and EverOS does two real jobs instead: it's the WRITE-side record of every graded routing decision (an actual `agent_case` per event, queryable, with real memory IDs/session IDs/scores — you can see them in the cases-learned panel), and it's what would let a smarter future version of this router do fuzzy matching across *differently-worded* requests that are really the same underlying task — which the current deterministic scheme intentionally doesn't attempt yet. We'd rather ship the honest, reproducible version than claim semantic matching we couldn't verify against the real schema in a 5-hour window.
