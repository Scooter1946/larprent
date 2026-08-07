# Regulars — Implementation Plan

## Goal
Build a counter-top kiosk agent that remembers every small-business customer across visits — proven
live with a real cross-session EverOS memory round trip, closed with a Snowflake-measured cost/margin
dashboard and a clearly-labeled simulated 56-day (8-week) cohort model.

## Why this wins
- **The reveal is un-fakeable in the room**: a volunteer taps in once, taps in again about a minute
  later under a brand-new `session_id`, and the kiosk greets them by name with their order, allergy
  note, and a follow-up on something they said — cross-session memory, not Streamlit session state.
- **The economics are honestly layered**: (a) real measured Cortex cost/interaction from
  `llm_call_log` shown in three labeled tiers (measured tokens, estimated $, billed Snowflake
  receipts), (b) real location-margin math vs. a real comparable price (Fivestars/Thanx
  ~$150–300/mo), (c) a seeded, watermarked-SIMULATED 56-day (8-week) cohort model — the pitch says
  "simulated cohort, real cost data" out loud instead of hiding the seam.
- **The reveal cannot whiff**: every greeting field is either a deterministic template slot filled from
  a direct profile `edit()`/read (no LLM in the loop) or a pre-cached, schema-validated flourish line —
  no live-generation step sits on the demo's critical path.

## Architecture
- Two-screen local Streamlit app: **Customer Kiosk** (explicit state machine: `idle →
  first_visit_form → saved → idle → return_greeting`) and **Owner Dashboard** (three-tier cost +
  margin math + cohort simulation), switched by a sidebar radio. A `REGULARS_REPLAY` flag puts the
  whole app in zero-external-call replay mode (outage fallback).
- Identity: `user_id = cust:{phone_last4}` (or `cust:name:{slug}`); every tap-in independently
  mints a fresh `session_id` (uuid4-based, never derived from any DB return value) — same
  customer, new session, is the whole cross-session proof, and the memory panel shows the new
  session_id NEXT TO the older originating one so the proof is visible, not just true.
- Writes: structured facts (name/usual_order, and allergy-vs-dietary as separate profile
  categories) go straight into the EverOS **profile** via `edit()` — never inferred from chat, no
  undocumented fields relied on to round-trip. The personal-detail line goes in as an **episode**
  via `add()`+`flush()`.
- A `claude-haiku-4-5` call extracts `{topic, followup_question}` from the personal detail and
  caches it in Snowflake — this runs at first-visit capture, AND (in production steady state,
  optionally, if the customer shares something new) again on later visits, which is what
  `location_margin()`'s "~4 calls/month" assumption models. The SCRIPTED 2-visit stage demo's
  visit 2 never re-triggers it, so the on-stage reveal stays the zero-LLM-call, can't-whiff render.
- Reads: profile fields read live from EverOS at greeting time (direct structured read, low risk).
  Flourish/upsell lines are pure Python over cached data — no LLM call on the reveal's critical path.
- `snow.py` gives three labeled cost tiers (measured tokens / estimated $ / billed Snowflake
  receipts) to `economics.py`, which produces the location margin numbers and the seeded cohort
  simulation shown on the Owner Dashboard.

```
 ┌────────────┐  tap-in (name/phone)   ┌───────────────────────┐
 │  Customer  │ ─────────────────────▶ │      app.py            │
 └────────────┘                        │  Kiosk  |  Owner View  │
                                        └────┬──────────┬───────┘
                    profile_store.py         │          │        economics.py
                    write_profile_facts()    │          │        simulate_cohort()
                    flourish.py              │          │        location_margin()
                    extract_and_store_...    ▼          ▼
                                        ┌─────────┐  ┌─────────┐
                                        │ mem.py  │  │ snow.py │
                                        │(EverOS) │  │(Snowfl.)│
                                        └────┬────┘  └────┬────┘
                                   edit()/add()/flush()  AI_COMPLETE (haiku,
                                   recall()/get()        flourish only),
                                             │           llm_call_log,
                                             ▼           regulars_* tables
                                     EverOS Cloud API    Snowflake HACKDB
```

## Kiosk UI Spec
- **Palette — "Terracotta & Oat"** (warm café branding, not generic dark-mode SaaS). **This is a
  DELIBERATE, explicit override of the shared contract's default dark-theme convention**, scoped
  ONLY to the customer-facing Kiosk view — a warm, legible, in-person counter-top screen is the
  right call for a product that's pitched as "a café's own kiosk," and a dark SaaS dashboard would
  undercut that pitch on stage. The Owner Dashboard view (internal, analyst-facing) stays on
  Streamlit's default dark theme per the contract's convention — the override applies to the Kiosk
  view alone:

  | Role | Name | Hex |
  |---|---|---|
  | Background | Warm Cream | `#FAF3E8` |
  | Headline text | Espresso | `#3A2317` |
  | Primary accent / buttons | Terracotta | `#C1592A` |
  | Confirm / success | Sage Green | `#7C9070` |
  | Allergy alert | Cranberry | `#A63446` |
  | Muted / secondary text | Latte Tan | `#8B7355` |

- **Big greeting**: one `st.markdown(..., unsafe_allow_html=True)` block, inline CSS
  `font-size:84px; font-weight:800; color:#3A2317; text-align:center;` on Cream — readable from the
  back of a room.
- **Memory panel**: card titled **"What I remember about you"** under the greeting, showing the
  CURRENT new `session_id` next to the OLDER originating `session_id` (the cross-session proof —
  see Task 6), plus: Name, Usual order, Allergy (Cranberry "⚠ confirmed allergy" badge if present)
  or Dietary preference, and the episode snippet with its originating `session_id` + timestamp
  inline (e.g. *"from session `cust:4471:8f2a91c3`, Aug 7 — 'training for the marathon this
  Sunday'"*).
- **Allergy CONFIRM toggle**: `st.toggle` ("This is an ALLERGY, not just a preference") reveals a
  second `st.checkbox` ("I confirm this allergy information"); Save stays disabled until confirmed —
  contract amendment #11 (never write safety facts from inferred chat).
- **Owner-view margin dashboard**: sidebar-switched view (dark theme), big `st.metric` tiles across
  all three cost tiers — measured tokens, estimated $/customer/mo, and a billed-receipts expander
  (Snowflake's own metering, always visible, not cuttable) — plus $49/mo price, gross margin %,
  comparable callout ("Fivestars/Thanx-class: $150–300/mo, no memory"), and the cohort chart,
  watermarked "SIMULATED" in Cranberry.
- **Auto-refresh**: used ONLY on the Owner Dashboard's activity feed (a light `st_autorefresh` every
  10–15s is fine there); the Kiosk view never auto-refreshes — it is state-machine-driven by
  explicit taps/clicks only, so an unexpected background rerun can never interrupt mid-form entry
  or the reveal.

## Phase 0 — Environment & Accounts (embedded from shared contract; target ≤ 30 min)

All paths are absolute; the project lives at `/Users/jaydenl/Dev/Hackathon/Snowflake2026/regulars/`.

1. **[HUMAN] Snowflake trial**: signup.snowflake.com, AWS US region. $400 credits, no card. In
   Snowsight: Admin → Users → your user → Programmatic access tokens → create one; use it as the
   connector `password` field. No key-pair auth, no plain password (MFA friction).
2. **[HUMAN] EverOS Cloud key**: sign up at https://everos.evermind.ai → create an API key (grab
   event-provided credits if offered). Use `everos-cloud` (managed SDK) — NOT self-hosted `everos`.
3. Create the project:
   ```bash
   mkdir -p /Users/jaydenl/Dev/Hackathon/Snowflake2026/regulars
   cd /Users/jaydenl/Dev/Hackathon/Snowflake2026/regulars
   python3 -m venv .venv && source .venv/bin/activate
   pip install "everos-cloud>=1.2,<2" snowflake-connector-python streamlit jsonschema python-dotenv numpy
   pip freeze | grep -iE "everos-cloud|snowflake-connector-python|streamlit|jsonschema|python-dotenv|numpy" > requirements.txt
   cat requirements.txt   # MUST show a line like "everos-cloud==X.Y.Z" -- that resolved version is
                           # now the exact tested pin for this build; re-install from this file if rebuilding
   ```
   `>=1.2,<2` constrains to the tested 1.x line (targets the v2 API per the contract) while still
   letting `pip` resolve the latest patch; the `pip freeze` line above then locks that resolved
   patch exactly.
   No `fastapi`/`uvicorn`/`tiktoken` — this product has no separate API server and gets exact token
   counts from `AI_COMPLETE(..., show_details => TRUE)`, so none are needed.
4. Create `.gitignore` containing `.env` and `.venv/` (both must never be committed).
5. Create `.env` (git-ignored):
   ```
   SNOWFLAKE_USER=<your_user>
   SNOWFLAKE_PAT=<programmatic_access_token>
   SNOWFLAKE_ACCOUNT=<account_locator>
   SNOWFLAKE_WAREHOUSE=COMPUTE_WH
   SNOWFLAKE_DATABASE=HACKDB
   SNOWFLAKE_SCHEMA=PUBLIC
   EVEROS_API_KEY=<everos_key>
   ```
6. Create `snow.py` (shared infra; Lane A owns after Phase 0):
   ```python
   import hashlib, json, os, time
   from datetime import datetime
   from dotenv import load_dotenv
   import snowflake.connector

   load_dotenv()
   MODEL_RATES = {"mistral-7b": 0.12, "claude-haiku-4-5": 0.35, "openai-gpt-5-mini": 0.32,
                   "claude-sonnet-5": 2.6, "claude-opus": 12.0}   # credits / 1M tokens, published rates
   CREDIT_USD = 2.00
   SMALL_TIER_FALLBACK = ["claude-haiku-4-5", "openai-gpt-5-mini", "mistral-7b"]  # contract order

   def get_conn(bootstrap: bool = False):
       kw = dict(user=os.environ["SNOWFLAKE_USER"], password=os.environ["SNOWFLAKE_PAT"],
                 account=os.environ["SNOWFLAKE_ACCOUNT"], warehouse=os.environ["SNOWFLAKE_WAREHOUSE"])
       if not bootstrap:
           kw["database"] = os.environ["SNOWFLAKE_DATABASE"]; kw["schema"] = os.environ["SNOWFLAKE_SCHEMA"]
       return snowflake.connector.connect(**kw)

   def bootstrap():
       conn = get_conn(bootstrap=True)
       conn.cursor().execute("CREATE DATABASE IF NOT EXISTS HACKDB")
       conn.close()
       conn = get_conn(bootstrap=False)
       conn.cursor().execute("""CREATE TABLE IF NOT EXISTS llm_call_log (
           call_id STRING DEFAULT UUID_STRING(), ts TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
           model STRING, purpose STRING, prompt_tokens INT, completion_tokens INT,
           latency_ms INT, credits_est FLOAT, user_id STRING, session_id STRING, extra VARIANT)""")
       conn.commit()

   def new_run_id(tag: str) -> str:
       """Fresh, timestamped run_id -- call ONCE per process at startup, never hardcode a shared
       literal (a shared constant mixes seed/check/live runs together in Snowflake cost logs,
       violating the contract's fresh-namespace rule)."""
       return f"regulars-{tag}-{datetime.now():%Y%m%d-%H%M%S}"

   def ai_complete(model, prompt, purpose, run_id, user_id=None, session_id=None,
                    agent_tag=None, extra=None, **params):
       """model_parameters is bound as a SERIALIZED JSON STRING via PARSE_JSON -- the connector
       cannot bind a Python dict directly into an OBJECT parameter. AI_COMPLETE's show_details
       response is itself a serialized JSON string, not a pre-parsed dict -- json.loads() it."""
       conn = get_conn(); cur = conn.cursor()
       cur.execute("ALTER SESSION SET QUERY_TAG = %s", (f"{run_id}:{agent_tag or purpose}",))
       t0 = time.time()
       cur.execute(
           "SELECT AI_COMPLETE(%s, %s, model_parameters => PARSE_JSON(%s), show_details => TRUE)",
           (model, prompt, json.dumps(params or {})))
       raw = cur.fetchone()[0]
       details = json.loads(raw) if isinstance(raw, str) else raw
       text = details["choices"][0]["messages"]
       usage = details.get("usage", {})
       pt, ct = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
       credits_est = (pt + ct) / 1e6 * MODEL_RATES.get(model, MODEL_RATES["claude-sonnet-5"])
       extra_full = dict(extra or {}); extra_full["run_id"] = run_id
       extra_full["agent_tag"] = agent_tag or purpose
       cur.execute("INSERT INTO llm_call_log (model, purpose, prompt_tokens, completion_tokens, "
                   "latency_ms, credits_est, user_id, session_id, extra) "
                   "SELECT %s,%s,%s,%s,%s,%s,%s,%s,PARSE_JSON(%s)",
                   (model, purpose, pt, ct, int((time.time()-t0)*1000), credits_est,
                    user_id, session_id, json.dumps(extra_full)))
       conn.commit(); cur.close(); conn.close()
       return text, {"prompt_tokens": pt, "completion_tokens": ct, "credits_est": credits_est}

   def ai_complete_small(prompt, purpose, run_id, **kw):
       """Executable small-tier fallback, contract order: haiku -> gpt-5-mini -> mistral-7b.
       Tries each in turn; raises the LAST error only if all three fail. Returns
       (text, usage, model) -- the THIRD element is the route/decision: whichever model ACTUALLY
       served the request, never assumed to be the first choice. Callers that log/capture this
       call (flourish.py) MUST record this returned model, never a hardcoded "claude-haiku-4-5"."""
       last_exc = None
       for model in SMALL_TIER_FALLBACK:
           try:
               text, usage = ai_complete(model, prompt, purpose, run_id, **kw)
               return text, usage, model
           except Exception as exc:
               last_exc = exc
       raise last_exc

   def prompt_hash(prompt: str) -> str:
       return "sha256:" + hashlib.sha256(prompt.encode()).hexdigest()[:16]

   def append_replay_event(event: dict, path: str = "fixtures/replay_events.jsonl") -> None:
       """Appends one contract-schema captured event (prompt hash, model ACTUALLY served,
       route/decision, output, usage, grader/verify result, run_id, timestamp) -- the raw
       material for --replay mode. Called by flourish.py after every real call, from benchmark.py."""
       with open(path, "a") as f:
           f.write(json.dumps(event) + "\n")
   ```
7. Create `mem.py` (shared infra; Lane B owns after Phase 0):
   ```python
   import os
   from dotenv import load_dotenv
   from everos_cloud import EverOS

   load_dotenv()
   APP_ID, PROJECT_ID = "regulars", "regulars-hackathon"
   # app_id/project_id are set ONCE here as constructor defaults so every method (add, search,
   # get, flush, edit, delete) shares the identical scope automatically -- no per-call kwargs,
   # no risk of one method drifting to a different namespace than another.
   _client = EverOS(api_key=os.environ["EVEROS_API_KEY"], app_id=APP_ID, project_id=PROJECT_ID)

   def remember(session_id: str, messages: list[dict]) -> None:
       """add() + immediate flush() — never skip flush, async extraction breaks live demos."""
       _client.add(session_id=session_id, messages=messages)
       _client.flush(session_id)

   def recall(query: str, user_id: str, top_k: int = 10):
       return _client.search(query, user_id=user_id, top_k=top_k, include_profile=True)

   def list_profile(user_id: str) -> dict[str, str]:
       """
       Normalizes EverOS's TYPED profile response ONCE, here -- no other module parses raw SDK
       objects. Per the everos-cloud-sdk-python quickstart, get("profile", ...) returns a page
       exposing `.profiles`, each item's structured content under `.profile_data` (itself exposing
       `.category`/`.description`) -- we defensively also accept a plain-dict shape in case the
       installed SDK version serializes differently. Returns the LATEST value per category
       (name/usual_order/dietary/allergy); a category with no stored item is simply absent --
       callers MUST treat a missing key as "unknown", never guess.
       """
       page = _client.get("profile", user_id=user_id)
       items = getattr(page, "profiles", None)
       if items is None:
           items = page.get("profiles", []) if isinstance(page, dict) else []
       fields, timestamps = {}, {}
       for item in items:
           data = getattr(item, "profile_data", None)
           if data is None:
               data = item.get("profile_data", item) if isinstance(item, dict) else item
           category = getattr(data, "category", None) or (data.get("category") if isinstance(data, dict) else None)
           description = getattr(data, "description", None) or (data.get("description") if isinstance(data, dict) else None)
           ts = str(getattr(item, "created_at", None) or (item.get("created_at") if isinstance(item, dict) else "") or "")
           if category and description and ts >= timestamps.get(category, ""):
               fields[category] = description
               timestamps[category] = ts
       return fields

   def is_known_customer(user_id: str) -> bool:
       """Reliable known/unknown classification via the NORMALIZED fields dict (never raw page
       truthiness, which can be non-empty even for a page with zero usable items)."""
       return bool(list_profile(user_id))

   def edit_profile(user_id: str, operations: list[dict]) -> None:
       _client.edit(user_id, operations=operations)

   def delete_user(user_id: str) -> None:
       """Scoped soft-delete — used by seed.py to rebuild the world idempotently."""
       _client.delete(user_id=user_id)
   ```
   This is the stable interface every other module imports against — `remember`, `recall`,
   `list_profile`, `is_known_customer`, `edit_profile`, `delete_user`. No product module edits
   `mem.py` after Phase 0. If `EverOS(...)` rejects `app_id`/`project_id` as constructor kwargs on
   the installed SDK version, pass them identically on every `add`/`search`/`get` call instead
   (`flush`/`edit`/`delete` are user/session-scoped only and take no `app_id`/`project_id`) — the
   goal is IDENTICAL scope on every call, however it's expressed; confirm which shape your
   installed version needs during the Task 1 smoke run and adjust here once.
8. Bootstrap: `python -c "import snow; snow.bootstrap()"` (no output = success). Verify:
   `python -c "import snow; print(snow.get_conn().cursor().execute('SELECT 1').fetchone())"` → `(1,)`.
9. **Smoke test gate** — create `smoke.py`:
   ```python
   import snow, mem

   RUN_ID = snow.new_run_id("smoke")

   def main():
       snow.get_conn()
       print("[smoke] Snowflake connection: OK")

       text, usage, model_used = snow.ai_complete_small("say ok", "smoke", run_id=RUN_ID)
       assert "ok" in text.lower()
       assert usage["prompt_tokens"] > 0 and usage["completion_tokens"] > 0, \
           f"AI_COMPLETE returned zero measured tokens -- logging is broken: {usage}"
       print(f"[smoke] AI_COMPLETE (small-tier fallback, served by {model_used}): OK "
             f"({usage['prompt_tokens']}+{usage['completion_tokens']} tokens)")

       uid = "cust:smoketest"
       try:
           mem.remember("smoke-session-1", [{"sender_id": uid, "role": "user",
                                              "content": "I love oat milk lattes."}])
       except Exception as exc:
           if "VERSION_NOT_ALLOWED" in str(exc) or "403" in str(exc):
               print("[smoke] FAILED: EverOS key is v1-only -- regenerate at "
                     "everos.evermind.ai console -> API keys -> create v2 key, "
                     "then update EVEROS_API_KEY in .env and re-run python smoke.py.")
               raise SystemExit(1)
           raise
       result = mem.recall("oat milk", user_id=uid, top_k=5)
       assert result.episodes, "EverOS remember->recall round trip returned nothing"
       print(f"[smoke] EverOS remember->recall: OK ({len(result.episodes)} episode(s))")

       mem.edit_profile(uid, operations=[{"action": "add", "type": "explicit_info",
           "data": {"category": "name", "description": "Smoke Test"}, "reason": "smoke.py"}])
       fields = mem.list_profile(uid)
       assert fields.get("name") == "Smoke Test", f"EverOS profile edit->get round trip failed: {fields}"
       print(f"[smoke] EverOS profile edit->get: OK ({fields})")

       # Allergy round trip -- separate category, must read back exactly (contract amendment #11:
       # safety facts are explicitly confirmed structured data, so this path must be provably real).
       mem.edit_profile(uid, operations=[{"action": "add", "type": "explicit_info",
           "data": {"category": "allergy", "description": "Peanut allergy (smoke test)"},
           "reason": "smoke.py"}])
       fields = mem.list_profile(uid)
       assert fields.get("allergy") == "Peanut allergy (smoke test)", \
           f"EverOS allergy category did not round-trip: {fields}"
       print(f"[smoke] EverOS allergy category round trip: OK ({fields['allergy']!r})")

       mem.delete_user(uid)
       print("ALL SMOKE CHECKS PASSED")

   if __name__ == "__main__":
       main()
   ```
   Run `python smoke.py` → all `[smoke] ... OK` lines + `ALL SMOKE CHECKS PASSED`. Remediation steps
   if it fails:
   - **Claude models unavailable**: run `ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';`
     in Snowsight, then re-run `python smoke.py`.
   - **`everos_cloud` raises `403 VERSION_NOT_ALLOWED`** (key is v1-only, SDK targets v2):
     1. Go to https://everos.evermind.ai/console → API Keys.
     2. Confirm the key's version badge reads "v2". If it reads "v1", click "Create new key" (or
        "Rotate") and select v2 explicitly if prompted.
     3. Replace `EVEROS_API_KEY` in `.env` with the new key.
     4. Re-run `python smoke.py`. Do not attempt to code around a v1 key.
   - **Profile/allergy assertions fail with a shape mismatch** (e.g. `AttributeError` on `.profiles`
     or `.profile_data`): print `repr(page)` for one `_client.get("profile", user_id=uid)` call,
     inspect the actual shape, and adjust `mem.list_profile()`'s parsing branch accordingly — this is
     the ONE place in the codebase allowed to touch raw SDK response shapes.

**Do not start Task 1 until `python smoke.py` prints `ALL SMOKE CHECKS PASSED`.**

---

## Tasks

Lane A owns: `snow.py` extensions, `profile_store.py`, `flourish.py`, `economics.py`, `fixtures/`,
`seed.py`, `check_demo.py`. Lane B owns: `greeting.py`, `app.py`. Both import the stable `mem.py`
interface fixed in Phase 0 but never edit it — different files only, no merge conflicts.

### Task 1 — Regulars Snowflake schema + smoke extension [Lane A, 30 min]
**Files**: `snow.py` (append). Bootstrap the product tables, the idempotent-delete helper, the
first-visit-session lookup (used for the memory panel's cross-session proof), and the three
measured-cost queries (tokens / estimated $ / billed receipts). Also defines — but does not yet
call — a Regulars-specific smoke check; Task 3 wires the call in once `flourish.py` exists.
```python
def bootstrap_regulars():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS regulars_customers (
        user_id STRING PRIMARY KEY, display_name STRING, phone_last4 STRING,
        first_seen TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(), visit_count INT DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS regulars_visits (
        visit_id STRING DEFAULT UUID_STRING(), user_id STRING, session_id STRING,
        ts TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(), order_text STRING)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS regulars_episode_cache (
        user_id STRING, session_id STRING, episode_text STRING,
        topic STRING, followup_question STRING, created_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP())""")
    conn.commit()

def record_visit(user_id, display_name, phone_last4, session_id, order_text=None) -> int:
    """Upserts regulars_customers, inserts regulars_visits, returns visit_seq (1-indexed).
    session_id is minted by the CALLER before this runs (uuid4-based, independent every tap-in) --
    this function never derives or requires a session_id from visit_seq, so there is no ordering
    cycle between callers. order_text is optional: a return visit that doesn't fill a fresh order
    form still gets logged (with the customer's last-known usual_order, passed in by the caller)."""
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT visit_count FROM regulars_customers WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    if row is None:
        cur.execute("INSERT INTO regulars_customers (user_id, display_name, phone_last4, visit_count) "
                     "VALUES (%s,%s,%s,1)", (user_id, display_name, phone_last4))
        visit_seq = 1
    else:
        visit_seq = row[0] + 1
        cur.execute("UPDATE regulars_customers SET visit_count = %s WHERE user_id = %s",
                     (visit_seq, user_id))
    cur.execute("INSERT INTO regulars_visits (user_id, session_id, order_text) VALUES (%s,%s,%s)",
                (user_id, session_id, order_text))
    conn.commit()
    return visit_seq

def first_visit_session(user_id: str) -> str | None:
    """The OLDEST session_id on file for this customer -- the 'originating session' the memory
    panel contrasts against the brand-new session_id minted at the current tap-in."""
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT session_id FROM regulars_visits WHERE user_id = %s ORDER BY ts ASC LIMIT 1",
                (user_id,))
    row = cur.fetchone()
    return row[0] if row else None

def delete_customer(user_id: str) -> None:
    """Snowflake half of idempotent reseeding -- mem.delete_user() only clears EverOS; without
    this, every seed.py rerun would append duplicate visit/cache rows and inflate visit_count."""
    conn = get_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM regulars_visits WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM regulars_episode_cache WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM regulars_customers WHERE user_id = %s", (user_id,))
    conn.commit()

def insert_flourish_row(user_id, session_id, episode_text, topic, followup_question):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("INSERT INTO regulars_episode_cache "
                "(user_id, session_id, episode_text, topic, followup_question) VALUES (%s,%s,%s,%s,%s)",
                (user_id, session_id, episode_text, topic, followup_question))
    conn.commit()

def purge_stale_call_log(prefixes=("regulars-seed-", "regulars-check-")) -> int:
    """Deletes PRIOR rehearsal rows (seed/check run_id families only, never regulars-live-* --
    those are real demo activity) before reseeding, so llm_call_log reflects only the LATEST
    rebuild instead of accumulating every rehearsal of the day. Called by seed.py before it seeds.
    Returns rows deleted."""
    conn = get_conn(); cur = conn.cursor()
    deleted = 0
    for prefix in prefixes:
        cur.execute("DELETE FROM llm_call_log WHERE extra:run_id::string LIKE %s", (prefix + "%",))
        deleted += cur.rowcount or 0
    conn.commit()
    return deleted

def avg_flourish_cost(run_id_prefix: str = "regulars-seed-") -> dict:
    """Cost tiers 1 and 2 (measured tokens; estimated $ = tokens x published rate) — exact SQL
    for the margin panel. Filtered to the CURRENT seed run_id family (representative production-
    path calls from the 6 background customers), NOT an all-history aggregation across every
    rehearsal -- purge_stale_call_log() is the first line of defense, this filter is the second.
    n_calls==0 means logging is broken (or seed.py hasn't run yet), not that cost is free; callers
    must check n_calls before trusting avg_usd_per_call (see check_demo.py, Task 9)."""
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""SELECT COUNT(*), AVG(prompt_tokens + completion_tokens),
                          AVG(credits_est), AVG(credits_est) * 2.00
                   FROM llm_call_log
                   WHERE purpose = 'regulars_flourish_extract'
                     AND extra:run_id::string LIKE %s""", (run_id_prefix + "%",))
    n, avg_tokens, avg_credits, avg_usd = cur.fetchone()
    return {"n_calls": n or 0, "avg_tokens_per_call": float(avg_tokens or 0),
            "avg_credits_per_call": float(avg_credits or 0), "avg_usd_per_call": float(avg_usd or 0)}

def billed_receipts(limit: int = 20) -> list[dict]:
    """Cost tier 3: Snowflake's OWN metering, not our self-tracked log — corroborates tier 2 with
    a ~5-min lag. Never drives a live ticker (per contract amendment #5); shown as a labeled
    'receipts' panel, always-on (not cuttable)."""
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""SELECT start_time, model_name, credits, metrics
                   FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY
                   WHERE query_tag LIKE 'regulars%%' ORDER BY start_time DESC LIMIT %s""", (limit,))
    cols = [c[0].lower() for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]

def recent_activity(limit: int = 10) -> list[dict]:
    """Owner Dashboard activity feed — most recent visits across all customers."""
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""SELECT c.display_name, c.phone_last4, v.ts, v.order_text
                   FROM regulars_visits v JOIN regulars_customers c ON c.user_id = v.user_id
                   ORDER BY v.ts DESC LIMIT %s""", (limit,))
    cols = [c[0].lower() for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
```
Also append this function to `smoke.py` now (defined but NOT yet called — `flourish.py` doesn't
exist until Task 3, which adds the one-line call and re-verifies the acceptance check below):
```python
def check_regulars():
    import flourish
    run_id = snow.new_run_id("smoke-regulars")
    d = flourish.extract_and_store_flourish("cust:smoketest2", "smoke-visit-1",
                                              "Training for a marathon this Sunday.", run_id)
    assert "topic" in d and "followup_question" in d
    print(f"[smoke] Regulars flourish extraction: OK ({d['topic']!r})")
```
**Acceptance**: `python -c "import snow; snow.bootstrap_regulars(); print('OK')"` → prints `OK`;
`SHOW TABLES LIKE 'regulars_%'` in Snowsight lists 3 tables. (Task 3 owns adding the
`check_regulars()` call to `smoke.py`'s `main()` and re-verifying `python smoke.py` end-to-end.)

### Task 2 — profile_store.py [Lane A, 30 min] — MANDATORY full sketch
**Files**: `profile_store.py` (new; named to avoid shadowing the stdlib `profile` module).
```python
import re
import mem

def make_user_id(name: str | None, phone_last4: str | None) -> str:
    if phone_last4:
        digits = re.sub(r"\D", "", phone_last4)[-4:]
        return f"cust:{digits}"
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "guest").strip().lower()).strip("-")
    return f"cust:name:{slug}"

def write_profile_facts(user_id: str, *, name: str | None, usual_order: str | None,
                         dietary_note: str | None, allergy_confirmed: bool,
                         source_session_id: str) -> list[dict]:
    """
    Writes ONLY explicitly-confirmed structured facts to the EverOS profile via edit(). Every
    value here came from a structured kiosk form field, never casual chat text. Allergy vs. a
    plain dietary preference is distinguished by PROFILE CATEGORY ("allergy" vs "dietary") --
    both are documented explicit_info shapes (category + description only); no undocumented
    field (e.g. a "confirmed_allergy" flag) is invented or relied on to round-trip. Returns the
    exact operations sent (memory panel / audit trail). Per contract amendment #11, category
    "allergy" is written ONLY after the UI's explicit CONFIRM checkbox was checked; otherwise
    the same text is written as a plain "dietary" preference note.
    """
    ops = []
    if name:
        ops.append({"action": "add", "type": "explicit_info",
                     "data": {"category": "name", "description": name.strip()},
                     "reason": f"Entered at kiosk tap-in, session {source_session_id}"})
    if usual_order:
        ops.append({"action": "add", "type": "explicit_info",
                     "data": {"category": "usual_order", "description": usual_order.strip()},
                     "reason": f"Stated at first visit, session {source_session_id}"})
    if dietary_note:
        category = "allergy" if allergy_confirmed else "dietary"
        reason = (f"Explicitly confirmed allergy by customer, session {source_session_id}"
                   if allergy_confirmed else f"Stated at first visit, session {source_session_id}")
        ops.append({"action": "add", "type": "explicit_info",
                     "data": {"category": category, "description": dietary_note.strip()},
                     "reason": reason})
    if ops:
        mem.edit_profile(user_id, operations=ops)
    return ops

def get_profile_fields(user_id: str) -> dict[str, str]:
    """
    Thin delegate to mem.list_profile() -- the EverOS typed-response parsing lives in EXACTLY
    ONE place (mem.py), so this module never touches raw SDK shapes. A category with no stored
    item is simply absent; callers (greeting.render_greeting) MUST treat a missing key as
    "unknown" and omit that slot, never guess or hardcode a value.
    """
    return mem.list_profile(user_id)
```
**Acceptance**:
```
python -c "
import profile_store as p
ops = p.write_profile_facts('cust:9999', name='Test User', usual_order='Drip coffee',
    dietary_note='Peanut allergy', allergy_confirmed=True, source_session_id='cust:9999:visit1')
print(len(ops), 'ops written'); print(p.get_profile_fields('cust:9999'))
"
```
Expected: `3 ops written` then a dict with keys `name`, `usual_order`, `allergy` (NOT `dietary`,
since `allergy_confirmed=True`) matching the values above (retry once with `time.sleep(1)` if
EverOS propagation lags).

### Task 3 — flourish.py [Lane A, 40 min]
**Files**: `flourish.py` (new). Makes the return-visit reveal LLM-call-free and whiff-proof.
```python
import datetime as dt
import json
import jsonschema
import mem, snow

FLOURISH_SCHEMA = {"type": "object", "properties": {
    "topic": {"type": "string", "minLength": 1, "maxLength": 40},
    "followup_question": {"type": "string", "minLength": 1, "maxLength": 120}},
    "required": ["topic", "followup_question"]}
DEFAULT_FLOURISH = {"topic": "catching up", "followup_question": "Good to see you again!"}

def extract_and_store_flourish(user_id: str, session_id: str, personal_detail_text: str,
                                run_id: str) -> dict:
    """
    Called at first-visit capture, AND optionally again on any later visit where the customer
    shares something new (see Task 6's return-greeting "anything new?" field) -- this is what
    the location_margin() economics model assumes happens ~once per visit in steady state. The
    reveal used in the SCRIPTED 2-visit stage demo never calls this a second time (nothing new is
    entered), so the on-stage reveal stays the zero-LLM-call, can't-whiff path either way.

    run_id is REQUIRED (never a hardcoded module constant) -- callers generate one fresh
    timestamped id per process via snow.new_run_id(), so seed/check/live runs never share
    attribution in Snowflake cost logs.

    The EverOS episode write and the Cortex extraction are independently fault-tolerant: an
    EverOS timeout must NOT prevent the Snowflake cache (the greeting's real source of truth)
    from being written, and a bad/non-JSON model response must NOT prevent the episode from
    having been stored. Stores the raw text as an EverOS episode (add+flush) so EverOS stays
    memory-of-record, then extracts+schema-validates a {topic, followup_question} pair and
    caches it in Snowflake -- the greeting NEVER re-reads the episode from EverOS live, which
    sidesteps EverOS's documented silent-write-failure bug on the demo's critical path. Every
    real call is also appended to fixtures/replay_events.jsonl for --replay mode (Task 6/8).
    """
    try:
        mem.remember(session_id, [{"sender_id": user_id, "role": "user", "content": personal_detail_text}])
    except Exception:
        pass  # EverOS write failure: the Snowflake cache below is still written regardless

    prompt = ('Extract a short topic (2-4 words) and a warm one-sentence follow-up question a '
              'barista could ask this customer next time they visit. Respond with ONLY JSON: '
              '{"topic": "...", "followup_question": "..."}\n\n'
              f'Customer note: {personal_detail_text}')
    usage = None
    model_used = None
    schema_valid = False
    try:
        text, usage, model_used = snow.ai_complete_small(prompt, purpose="regulars_flourish_extract",
                                                           run_id=run_id, user_id=user_id, session_id=session_id)
        data = json.loads(text)
        jsonschema.validate(data, FLOURISH_SCHEMA)
        schema_valid = True
    except Exception:
        data = dict(DEFAULT_FLOURISH)

    snow.insert_flourish_row(user_id, session_id, personal_detail_text,
                              data["topic"], data["followup_question"])
    if usage is not None:
        snow.append_replay_event({
            "event_id": f"{user_id}:{session_id}:{dt.datetime.utcnow().isoformat()}",
            "ts": dt.datetime.utcnow().isoformat(), "run_id": run_id, "kind": "flourish_extract",
            "user_id": user_id, "session_id": session_id,
            "model": model_used,  # the ACTUAL model that served this call -- never hardcoded
            "route_decision": {"requested_tier": "small", "served_by": model_used},
            "prompt_hash": snow.prompt_hash(prompt), "output": data, "usage": usage,
            "grader_result": {"schema_valid": schema_valid},
        })
    return data

def get_flourish(user_id: str) -> dict | None:
    """Source of truth for the GREETING — always the Snowflake cache written at capture time."""
    conn = snow.get_conn(); cur = conn.cursor()
    cur.execute("SELECT session_id, episode_text, topic, followup_question, created_at "
                "FROM regulars_episode_cache WHERE user_id = %s "
                "ORDER BY created_at DESC LIMIT 1", (user_id,))
    row = cur.fetchone()
    if row is None:
        return None
    return {"session_id": row[0], "episode_text": row[1], "topic": row[2],
            "followup_question": row[3], "created_at": str(row[4])}

def verify_everos_has_episode(user_id: str, query: str, expected_session_id: str) -> bool:
    """Secondary, NON-BLOCKING confirmation badge only ("confirmed in EverOS" vs "pending").
    Matches against the EXPECTED ORIGINATING session_id (not just any episode for this user) --
    a stale unrelated episode must not read as confirmation of THIS fact. Any failure/timeout/
    empty result degrades gracefully — greeting rendering never depends on this call."""
    try:
        result = mem.recall(query, user_id=user_id, top_k=5)
        episodes = getattr(result, "episodes", None) or []
        for ep in episodes:
            ep_session = getattr(ep, "session_id", None)
            if ep_session is None and isinstance(ep, dict):
                ep_session = ep.get("session_id")
            if ep_session == expected_session_id:
                return True
        return False
    except Exception:
        return False
```
**Acceptance**:
```
python -c "
import flourish, snow
run_id = snow.new_run_id('task3check')
d = flourish.extract_and_store_flourish('cust:8001', 'cust:8001:visit1', 'Just adopted a puppy named Waffles!', run_id)
print(d); print(flourish.get_flourish('cust:8001'))
"
```
Expected: a dict with `topic`/`followup_question` (real extraction or `DEFAULT_FLOURISH`), and
`get_flourish` returns a matching cached row — never `None`, never an exception. Then add the one
line `check_regulars()` to `smoke.py`'s `main()` (after the allergy check, before
`mem.delete_user(uid)`) and re-run `python smoke.py` — it now ends with
`[smoke] Regulars flourish extraction: OK (...)`.

### Task 4 — economics.py [Lane A, 30 min] — MANDATORY full sketch
**Files**: `economics.py` (new). Cohort simulator + location margin, both fully pinned per the slate.
```python
import numpy as np

N_CUSTOMERS = 200
WEEKS = 60 // 7                 # = 8. NOTE: 8 x 7 = 56 days, not 60 -- every UI label below says
                                 # "56-day (8-week)" honestly, never "60-day", to match this exactly.
P_BASELINE = 0.30               # weekly visit probability, no-memory arm
LIFT_RELATIVE_DEFAULT = 0.10    # +10% relative lift; UI sensitivity slider overrides 0.05-0.20
AOV = 6.50
GROSS_MARGIN = 0.70

def simulate_cohort(lift_relative: float = LIFT_RELATIVE_DEFAULT, seed: int = 42) -> dict:
    """
    SEEDED, DISCLOSED SIMULATION — not measured data; watermark "SIMULATED" wherever shown.
    Covers WEEKS=8 weekly cycles (56 days) -- always labeled "56-day (8-week)" on screen, never
    "60-day" (the pins' 60-day figure divides into 8 clean weekly cycles with 4 days left over,
    which this model drops rather than simulate a partial week). Each week, each customer visits
    independently with probability p (Bernoulli trial): p_baseline=0.30, p_memory=0.30*(1+lift).
    A "remembered" customer = one who visited >=1 time in the memory arm (their first visit is
    exactly when name/usual/dietary get captured and an episode gets stored). Bain's "5%
    retention lift -> 25-95% profit lift" is cited ELSEWHERE as profit-sensitivity context only
    — never as an input here.
    """
    rng = np.random.default_rng(seed)
    p_memory = P_BASELINE * (1 + lift_relative)
    visits_baseline = rng.binomial(1, P_BASELINE, size=(N_CUSTOMERS, WEEKS))
    visits_memory = rng.binomial(1, p_memory, size=(N_CUSTOMERS, WEEKS))

    tv_b, tv_m = int(visits_baseline.sum()), int(visits_memory.sum())
    rev_b, rev_m = tv_b * AOV, tv_m * AOV
    prof_b, prof_m = rev_b * GROSS_MARGIN, rev_m * GROSS_MARGIN
    remembered = int((visits_memory.sum(axis=1) >= 1).sum())

    return {"weeks": WEEKS, "n_customers": N_CUSTOMERS, "p_baseline": P_BASELINE,
            "p_memory": round(p_memory, 4), "lift_relative": lift_relative,
            "total_visits_baseline": tv_b, "total_visits_memory": tv_m,
            "revenue_baseline": round(rev_b, 2), "revenue_memory": round(rev_m, 2),
            "profit_baseline": round(prof_b, 2), "profit_memory": round(prof_m, 2),
            "profit_lift_dollars": round(prof_m - prof_b, 2),
            "profit_lift_pct": round((prof_m - prof_b) / prof_b * 100, 2),
            "remembered_customers": remembered, "remembered_pct": round(remembered / N_CUSTOMERS * 100, 1)}

LOCATION_CUSTOMERS = 250
REGULARS_PRICE_MO = 49.00
VISITS_PER_MONTH = 4
COMPARABLE_LOW, COMPARABLE_HIGH = 150.00, 300.00   # Fivestars/Thanx-class, no memory

def location_margin(avg_usd_per_call: float) -> dict:
    """
    avg_usd_per_call = snow.avg_flourish_cost()['avg_usd_per_call'] (measured, tier-2 estimated $
    = tier-1 measured tokens x published rate). VISITS_PER_MONTH=4 reconciles exactly with the
    architecture: extract_and_store_flourish() runs at first-visit capture AND, in production
    steady state, again on any later visit where the customer shares something new (Task 6's
    optional "anything new?" field on the return-greeting screen) -- modeled here as ~1 call per
    visit. This is a steady-state MODELING assumption, distinct from the specific 2-visit stage
    demo, where visit 2 is scripted to add nothing new (so the on-stage reveal is the zero-call,
    can't-whiff path) -- both are true at once and neither contradicts the other. EverOS Cloud
    usage is sponsor-credited for this event and excluded from this math — labeled explicitly in
    the UI.
    """
    cost_per_customer_month = avg_usd_per_call * VISITS_PER_MONTH
    total_monthly_cost = cost_per_customer_month * LOCATION_CUSTOMERS
    margin_dollars = REGULARS_PRICE_MO - total_monthly_cost
    return {"cost_per_customer_month": round(cost_per_customer_month, 4),
            "total_monthly_cost_250_customers": round(total_monthly_cost, 4),
            "price_mo": REGULARS_PRICE_MO, "location_customers": LOCATION_CUSTOMERS,
            "gross_margin_dollars": round(margin_dollars, 2),
            "gross_margin_pct": round(margin_dollars / REGULARS_PRICE_MO * 100, 1),
            "comparable_low": COMPARABLE_LOW, "comparable_high": COMPARABLE_HIGH,
            "undercut_pct_low": round((1 - REGULARS_PRICE_MO / COMPARABLE_LOW) * 100, 1),
            "undercut_pct_high": round((1 - REGULARS_PRICE_MO / COMPARABLE_HIGH) * 100, 1)}
```
**Acceptance**: `python -c "import economics as e; print(e.simulate_cohort()); print(e.location_margin(0.00004))"`
→ two dicts, no exceptions; `weeks==8`, `n_customers==200`; `location_margin()['gross_margin_pct']` a
large positive number (cost/call is fractions of a cent → margin prints > 99%).

### Task 5 — greeting.py [Lane B, 20 min] — MANDATORY full sketch
**Files**: `greeting.py` (new). Pure Python, zero LLM calls, zero network calls.
```python
PREFERENCE_UPSELL_MAP = {
    "gluten": "Heads up — we've got a GF cookie on the counter today.",
    "celiac": "Heads up — we've got a GF cookie on the counter today.",
    "vegan": "Heads up — the blueberry muffin's vegan today.",
    "dairy": "Heads up — our oat-milk options are dairy-free.",
}

def build_upsell(dietary_note: str | None, is_allergy: bool = False) -> str | None:
    """
    NEVER asserts menu safety ("nut-free", "safe for X allergy") and NEVER claims an action the
    system hasn't actually performed (e.g. "kitchen's been notified" -- nothing here notifies a
    kitchen). For a CONFIRMED ALLERGY (is_allergy=True), the line only states that the fact is
    noted on this order and explicitly defers the safety judgment to a human staff member; it is
    grounded in what was actually typed and confirmed, not a claim about any dish or any action
    taken. For a plain preference (is_allergy=False), a soft, non-safety-critical suggestion is fine.
    """
    if not dietary_note:
        return None
    if is_allergy:
        return f"Allergy noted on this order ({dietary_note.lower()}) — please confirm with staff."
    lowered = dietary_note.lower()
    for key, line in PREFERENCE_UPSELL_MAP.items():
        if key in lowered:
            return line
    return None

def render_greeting(profile_fields: dict[str, str], flourish_line: str | None,
                     upsell_line: str | None) -> str:
    """
    Renders the big kiosk greeting from already-retrieved data. Every slot is OPTIONAL: a
    missing field is OMITTED entirely (never an empty placeholder, "None", or a hallucinated
    guess), so the reveal degrades gracefully for a first-time or partially-remembered
    customer instead of breaking on stage. Zero calls of any kind — pure string formatting.
    Template: "{salutation}{usual_clause}{flourish_clause}{upsell_clause}"
    """
    name = profile_fields.get("name")
    usual = profile_fields.get("usual_order")
    salutation = f"Hey {name}!" if name else "Hey there!"
    usual_clause = f" The usual {usual}?" if usual else ""
    flourish_clause = f" {flourish_line}" if flourish_line else ""
    upsell_clause = f" {upsell_line}" if upsell_line else ""
    return f"{salutation}{usual_clause}{flourish_clause}{upsell_clause}".strip()
```
**Acceptance**:
```
python -c "
import greeting as g
print(g.render_greeting({'name':'Jordan','usual_order':'oat-milk cortado'}, \"How'd the marathon go?\", g.build_upsell('Gluten-free — celiac', is_allergy=True)))
print(g.render_greeting({}, None, None))
"
```
Line 1 expected: `Hey Jordan! The usual oat-milk cortado? How'd the marathon go? Allergy noted on
this order (gluten-free — celiac) — please confirm with staff.`. Line 2 expected:
`Hey there!` (no crash on an empty profile). Note this is the exact call site's `is_allergy=True`
path — callers pass `fields.get("allergy")` with `is_allergy=True` when an allergy category is
present, else `fields.get("dietary")` with `is_allergy=False` (see Task 6).

### Task 6 — app.py: Kiosk + Owner Dashboard [Lane B, 130 min]
**Files**: `app.py` (new; imports `streamlit as st`, `profile_store`, `flourish`, `greeting`,
`economics`, `snow`, `mem`, `uuid`, `json`, `os`, `sys`). Sidebar `st.radio("View", ["Customer Kiosk", "Owner
Dashboard"])` switches the two views. `REGULARS_REPLAY=1` env var (or
`streamlit run app.py -- --replay`) puts the WHOLE app in **replay mode**: zero external calls,
everything rendered from `fixtures/replay_snapshot.json` (see Task 8) — check this flag once at
the top of the script:
```python
REPLAY = bool(os.environ.get("REGULARS_REPLAY")) or "--replay" in sys.argv
```

**Explicit kiosk state machine** — `st.session_state.kiosk_state`, one of `"idle"`,
`"first_visit_form"`, `"saved"`, `"return_greeting"`. Every tap-in mints a **brand-new**
`session_id` independently (never derived from `record_visit()`'s return value — that circularity
is exactly what broke the prior draft):
```python
import uuid

def tap_in(name, phone) -> bool:
    """Validates identity input BEFORE minting anything: strips whitespace, requires at least one
    of name/phone with length >= 2 after stripping, rejects a blank/whitespace-only tap-in with
    st.error and returns False (caller must not proceed to mint a session_id or call
    make_user_id on garbage input). Returns True once a session was actually minted."""
    name = (name or "").strip()
    phone = (phone or "").strip()
    if len(name) < 2 and len(phone) < 2:
        st.error("Enter your name or phone (last 4 digits) — at least 2 characters.")
        return False
    user_id = profile_store.make_user_id(name or None, phone or None)
    session_id = f"{user_id}:{uuid.uuid4().hex[:8]}"          # fresh every tap-in, unconditionally
    st.session_state.user_id = user_id
    st.session_state.session_id = session_id                   # THE current, new session_id
    st.session_state.tap_in_name, st.session_state.tap_in_phone = name, phone
    if REPLAY:
        st.session_state.kiosk_state = "return_greeting"        # replay only ever shows Sam
        return True
    if mem.is_known_customer(user_id):
        fields = profile_store.get_profile_fields(user_id)
        snow.record_visit(user_id, fields.get("name", name), phone, session_id,
                           order_text=fields.get("usual_order"))
        st.session_state.kiosk_state = "return_greeting"
    else:
        st.session_state.kiosk_state = "first_visit_form"
    return True

def reset_to_idle():
    """The explicit RESET action between visits -- clears kiosk state so the next tap-in starts clean."""
    for key in ("user_id", "session_id", "tap_in_name", "tap_in_phone"):
        st.session_state.pop(key, None)
    st.session_state.kiosk_state = "idle"
```
- **`idle`**: Terracotta & Oat idle screen, big "Tap in" button, `st.text_input` for name and/or
  phone last-4. Submit calls `if tap_in(name, phone): st.rerun()` — a blank/too-short entry shows
  the `st.error` from `tap_in()` and stays on `idle` without minting a `user_id`/`session_id`.
- **`first_visit_form`**: `name`, `usual_order`, `dietary_note` text inputs; allergy toggle +
  CONFIRM checkbox per the Kiosk UI Spec (Save disabled until confirmed when the toggle is on); a
  `personal_detail` text area ("Tell us something — we'll remember it for next time"). On Save:
  ```python
  run_id = st.session_state.setdefault("run_id", snow.new_run_id("live"))
  profile_store.write_profile_facts(user_id, name=name, usual_order=usual_order,
      dietary_note=dietary_note, allergy_confirmed=is_allergy, source_session_id=session_id)
  flourish.extract_and_store_flourish(user_id, session_id, personal_detail, run_id)
  snow.record_visit(user_id, name, phone, session_id, order_text=usual_order)
  st.session_state.kiosk_state = "saved"          # NOT "return_greeting" -- no spoiler render
  ```
- **`saved`**: a plain confirmation card — *"Thanks, {name}! Profile saved."* — plus one button,
  **"Next customer"**, calling `reset_to_idle()`. This state deliberately does NOT render the
  greeting/memory panel (that would spoil the reveal on visit 2) and is the reset action the
  review flagged as missing.
- **`return_greeting`** (the reveal, known-customer path): builds and shows the greeting, then
  offers its OWN "Next customer" button calling `reset_to_idle()` (this is how the demo loops back
  to `idle` for Jordan's actual second tap-in). Also offers the "anything new since last time?"
  optional text field (see economics reconciliation note in Task 4) — blank by default, and if
  submitted, calls `extract_and_store_flourish` again to refresh the cache for next time.
  ```python
  fields = profile_store.get_profile_fields(user_id)
  flourish_row = flourish.get_flourish(user_id)
  flourish_line = flourish_row["followup_question"] if flourish_row else None
  if fields.get("allergy"):
      upsell_line = greeting.build_upsell(fields["allergy"], is_allergy=True)
  else:
      upsell_line = greeting.build_upsell(fields.get("dietary"), is_allergy=False)
  greeting_text = greeting.render_greeting(fields, flourish_line, upsell_line)
  # render greeting_text at 84px per the Kiosk UI Spec
  ```
  **Memory panel** ("What I remember about you") — the on-stage cross-session proof. It MUST show
  the CURRENT new session_id side-by-side with the OLDER originating session_id, not just one:
  ```python
  originating_session = snow.first_visit_session(user_id)
  st.markdown(f"**Current session (this tap-in):** `{session_id}`")
  st.markdown(f"**Originating session (when we first learned this):** `{originating_session}`")
  # Name / Usual order / Allergy (⚠ badge, from fields["allergy"] if present) / Dietary
  # / episode snippet (flourish_row["episode_text"]) + flourish_row["session_id"] + created_at
  confirmed = flourish.verify_everos_has_episode(
      user_id, flourish_row["episode_text"][:40], flourish_row["session_id"]) if flourish_row else False
  st.caption("✓ confirmed in EverOS" if confirmed else "EverOS confirmation pending (non-blocking)")
  ```
  In **replay mode**, this entire state instead loads `snapshot = json.load(open("fixtures/replay_snapshot.json"))["sam"]` and renders `snapshot["greeting_text"]` plus the same panel fields directly from the snapshot — zero calls, and a persistent banner reads **"REPLAY MODE — captured pre-show run, zero live calls."**

**Owner Dashboard** — three cost tiers, ALL always shown (none of this panel is cuttable):
```python
if REPLAY:
    snap = json.load(open("fixtures/replay_snapshot.json"))
    costs, margin, feed = snap["costs"], snap["margin"], snap["activity_feed"]
else:
    costs = snow.avg_flourish_cost()
    margin = economics.location_margin(costs["avg_usd_per_call"])
    feed = snow.recent_activity()  # SQL below
```
- *Tier 1 — measured tokens*: `st.metric("Measured tokens / call", costs["avg_tokens_per_call"])`.
- *Tier 2 — estimated $*: `st.metric("Estimated $ / customer / mo (tokens × published rate)",
  f"${margin['cost_per_customer_month']:.4f}")`, plus "Regulars price" (`$49/mo`) and "Gross
  margin" (`{margin['gross_margin_pct']}%`) tiles. Caption: *"vs. Fivestars/Thanx-class tools at
  $150–300/mo — which don't remember conversations. EverOS Cloud usage is sponsor-credited for
  this event and excluded from this math."*
- *Tier 3 — billed credits (receipts, NOT cuttable)*: an always-visible expander titled **"Snowflake
  receipts (billed credits, ~5 min lag)"** rendering `snow.billed_receipts()` (or
  `snap["receipts"]` in replay mode) via `st.dataframe` — corroborates tiers 1–2, never drives a
  live number.
- *Cohort simulation*: `st.slider("Retention lift assumption (sensitivity)", 5, 20, 10)` (%) →
  `sim = economics.simulate_cohort(lift_relative=slider/100)`; `st.bar_chart` of baseline vs.
  memory total visits and profit; Cranberry `st.caption("SIMULATED — seeded RNG(42), 200
  customers, 56-day (8-week) window. Not measured data.")`; static line: *"For context only (not
  our lift assumption): Bain/HBR find a 5-point retention increase can correspond to a 25–95%
  profit increase — we use a conservative, disclosed +10% relative visit-lift assumption
  instead."*
- *Recent activity feed* (skippable under the cut line — add `snow.recent_activity()`):
  ```sql
  SELECT c.display_name, c.phone_last4, v.ts, v.order_text
  FROM regulars_visits v JOIN regulars_customers c ON c.user_id = v.user_id
  ORDER BY v.ts DESC LIMIT 10;
  ```
  rendered via `st.dataframe`.

**Acceptance**: `streamlit run app.py` → idle → tap in as a new name → `first_visit_form` → fill
with allergy toggle ON but confirm unchecked → Save disabled → check confirm → Save enables →
click → lands on `saved` (confirmation only, NOT the greeting) → click "Next customer" → back to
`idle` → tap in again with the SAME name/phone → `return_greeting` shows the just-entered data,
with a visibly DIFFERENT `session_id` than visit 1 shown in the memory panel next to the
unchanged originating session_id. Separately: `REGULARS_REPLAY=1 streamlit run app.py` (after
Task 8 has produced `fixtures/replay_snapshot.json`) renders Sam's greeting, memory panel, and the
full Owner Dashboard with the REPLAY MODE banner visible and zero exceptions. With `seed.py`
already run (Task 8, live mode), Owner Dashboard shows all cost tiers non-zero, the receipts
expander lists rows (or an empty-but-present table if the 5-min metering lag hasn't caught up
yet), and the cohort chart renders with its SIMULATED caption.

### Task 7 — fixtures/regulars_fixtures.json [Lane A, 20 min]
**Files**: `fixtures/regulars_fixtures.json` (new). Content is specified verbatim in **Fixtures spec**
below — write it exactly as shown there (three top-level keys: `background_customers`,
`fallback_persona`, `volunteer_script`).
**Acceptance**: `python -c "import json; d=json.load(open('fixtures/regulars_fixtures.json')); print(len(d['background_customers']), d['fallback_persona']['name'], d['volunteer_script']['display_name_on_stage'])"`
→ `6 Sam Jordan`.

### Task 8 — seed.py [Lane A, 35 min]
**Files**: `seed.py` (new). The "wifi died, rebuild everything" button — rebuilds all demo state
from the fixture file in under 2 minutes, IDEMPOTENT ACROSS BOTH EverOS AND Snowflake (deleting
both before reseeding each identity — a Snowflake-only delete was the prior draft's bug: reruns
appended duplicate visit rows and inflated visit_count forever). Also purges stale `llm_call_log`
rows from prior seed/check rehearsals via `snow.purge_stale_call_log()` (so the Owner Dashboard's
cost numbers reflect the LATEST rebuild, not an all-history aggregation across every rehearsal of
the day), seeds Sam **deterministically** (no LLM call for her flourish — the fixture's
pre-authored text is used verbatim, then read back and asserted), and writes
`fixtures/replay_events.jsonl` / `fixtures/replay_snapshot.json` for `--replay` mode.
```python
import datetime as dt
import json
import economics, flourish, greeting, mem, profile_store, snow

def seed_customer(entry: dict, run_id: str) -> str:
    """Real (non-deterministic) LLM extraction path -- used for the 6 background customers."""
    user_id = profile_store.make_user_id(entry["name"], entry.get("phone_last4"))
    try:
        mem.delete_user(user_id)
    except Exception:
        pass
    snow.delete_customer(user_id)                      # Snowflake half of idempotent reseeding
    session_id = f"{user_id}:visit1"
    profile_store.write_profile_facts(
        user_id, name=entry["name"], usual_order=entry["usual_order"],
        dietary_note=entry.get("dietary_note"), allergy_confirmed=entry.get("is_allergy", False),
        source_session_id=session_id)
    flourish.extract_and_store_flourish(user_id, session_id, entry["personal_detail"], run_id)
    snow.record_visit(user_id, entry["name"], entry.get("phone_last4"), session_id,
                       order_text=entry["usual_order"])
    return user_id

def seed_fallback_persona(entry: dict) -> str:
    """
    Sam is seeded DETERMINISTICALLY: the flourish text is the fixture's pre-authored
    expected_flourish_followup, written directly (bypassing the LLM call entirely), so Sam is
    100% reproducible regardless of model variance -- this is the guaranteed fallback and must
    never depend on what a live model happens to say. Read-back verified before doors open.
    """
    user_id = profile_store.make_user_id(entry["name"], entry.get("phone_last4"))
    try:
        mem.delete_user(user_id)
    except Exception:
        pass
    snow.delete_customer(user_id)
    session_id = f"{user_id}:visit1"
    profile_store.write_profile_facts(
        user_id, name=entry["name"], usual_order=entry["usual_order"],
        dietary_note=entry.get("dietary_note"), allergy_confirmed=entry.get("is_allergy", False),
        source_session_id=session_id)
    try:
        mem.remember(session_id, [{"sender_id": user_id, "role": "user", "content": entry["personal_detail"]}])
    except Exception:
        pass
    snow.insert_flourish_row(user_id, session_id, entry["personal_detail"],
                              "catching up", entry["expected_flourish_followup"])
    snow.record_visit(user_id, entry["name"], entry.get("phone_last4"), session_id,
                       order_text=entry["usual_order"])

    fields = profile_store.get_profile_fields(user_id)
    assert fields.get("name") == entry["name"], f"Sam name did not round-trip: {fields}"
    assert fields.get("usual_order") == entry["usual_order"], f"Sam usual_order did not round-trip: {fields}"
    fl = flourish.get_flourish(user_id)
    assert fl and fl["followup_question"] == entry["expected_flourish_followup"], \
        f"Sam flourish did not round-trip: {fl}"
    print(f"[seed] Sam verified deterministic: {fields}; flourish={fl['followup_question']!r}")
    return user_id

def write_replay_snapshot(sam_user_id: str):
    """Real captured data from THIS run -- the contract's 'real prior run' replay requirement."""
    fields = profile_store.get_profile_fields(sam_user_id)
    fl = flourish.get_flourish(sam_user_id)
    upsell = greeting.build_upsell(fields.get("allergy") or fields.get("dietary"),
                                    is_allergy=bool(fields.get("allergy")))
    greeting_text = greeting.render_greeting(fields, fl["followup_question"] if fl else None, upsell)
    costs = snow.avg_flourish_cost()
    snapshot = {
        "captured_at": dt.datetime.utcnow().isoformat(),
        "sam": {"user_id": sam_user_id, "fields": fields, "flourish": fl,
                "first_visit_session": snow.first_visit_session(sam_user_id),
                "greeting_text": greeting_text},
        "costs": costs,
        "margin": economics.location_margin(costs["avg_usd_per_call"]),
        "cohort_default": economics.simulate_cohort(),
        "activity_feed": snow.recent_activity(),
        "receipts": snow.billed_receipts(),
    }
    with open("fixtures/replay_snapshot.json", "w") as f:
        json.dump(snapshot, f, indent=2, default=str)

def main():
    snow.bootstrap(); snow.bootstrap_regulars()
    deleted = snow.purge_stale_call_log()      # drop prior seed/check llm_call_log rows FIRST --
    print(f"[seed] Purged {deleted} stale seed/check llm_call_log row(s) from prior rehearsals.")
    run_id = snow.new_run_id("seed")
    data = json.load(open("fixtures/regulars_fixtures.json"))
    open("fixtures/replay_events.jsonl", "w").close()      # fresh capture file every rebuild
    for entry in data["background_customers"]:
        seed_customer(entry, run_id)
    sam_user_id = seed_fallback_persona(data["fallback_persona"])
    write_replay_snapshot(sam_user_id)
    print(f"Seeded {len(data['background_customers'])} background customers + fallback persona "
          f"{data['fallback_persona']['name']}. Replay snapshot + events written. Ready in <2 min.")

if __name__ == "__main__":
    main()
```
**Acceptance**: `time python seed.py` completes in < 120s, prints the summary line INCLUDING the
`[seed] Sam verified deterministic: ...` line; re-running it immediately also completes clean with
IDENTICAL Sam output (idempotent across both EverOS and Snowflake — no duplicate-key errors, no
visit_count drift); `fixtures/replay_events.jsonl` and `fixtures/replay_snapshot.json` both exist
and are non-empty after the run.

Also create `benchmark.py` — the shared contract (R1 amendment #6) requires the pre-show capture
script to be named `benchmark.py`; `seed.py` already performs the real seeded run and captures
every event, so this is a thin, contract-compliant wrapper, not a duplicate implementation:
```python
"""benchmark.py -- the pre-show capture script the shared contract requires by name. seed.py
already performs the real seeded run (background customers + Sam) and writes
fixtures/replay_events.jsonl / fixtures/replay_snapshot.json; this is that script's canonical
entrypoint name."""
import seed

if __name__ == "__main__":
    seed.main()
```
**Acceptance**: `python benchmark.py` produces identical output/files to `python seed.py` (same
function, same idempotency guarantees).

### Task 9 — check_demo.py [Lane A, 20 min]
**Files**: `check_demo.py` (new). Single end-to-end assertion the contract requires — tests the
ACTUAL headline mechanism (two distinct sessions for the same customer), never masks a broken
measurement with a fake fallback value.
```python
import os
import profile_store, flourish, greeting, economics, snow

def main():
    run_id = snow.new_run_id("check")
    uid = "cust:9998"
    session_1 = f"{uid}:{run_id}:v1"
    profile_store.write_profile_facts(uid, name="Check Demo", usual_order="Drip coffee",
        dietary_note=None, allergy_confirmed=False, source_session_id=session_1)
    flourish.extract_and_store_flourish(uid, session_1, "Ran a 5K this weekend.", run_id)
    snow.record_visit(uid, "Check Demo", None, session_1, order_text="Drip coffee")

    # A SECOND, independent session_id for the SAME customer, with an ACTUAL visit write under
    # it -- this is the headline mechanism the memory panel shows on stage: the CURRENT session
    # (session_2) must differ from the ORIGINATING session (session_1) the stored facts trace
    # back to, and read-back must still resolve correctly under the new session.
    session_2 = f"{uid}:{run_id}:v2"
    assert session_1 != session_2
    snow.record_visit(uid, "Check Demo", None, session_2, order_text="Drip coffee")
    fields = profile_store.get_profile_fields(uid)          # read under session_2's "visit"
    assert fields.get("name") == "Check Demo", f"profile did not persist across sessions: {fields}"
    fl = flourish.get_flourish(uid)
    assert fl is not None, "flourish cache empty"
    originating = snow.first_visit_session(uid)
    assert originating == session_1, f"originating session mismatch: expected {session_1}, got {originating}"
    assert originating != session_2, "originating session must differ from the current (2nd) session"
    text = greeting.render_greeting(fields, fl["followup_question"], None)
    assert "Check Demo" in text and "Drip coffee" in text

    sim = economics.simulate_cohort()
    assert sim["n_customers"] == 200 and sim["weeks"] == 8

    costs = snow.avg_flourish_cost()
    assert costs["n_calls"] > 0, "no measured Cortex calls logged -- check llm_call_log / QUERY_TAG"
    assert costs["avg_tokens_per_call"] > 0, "measured tokens are zero -- AI_COMPLETE logging is broken"
    margin = economics.location_margin(costs["avg_usd_per_call"])   # NO fake fallback value
    assert margin["gross_margin_pct"] > 0

    assert os.path.exists("fixtures/replay_events.jsonl"), "run seed.py first to produce replay events"
    assert os.path.getsize("fixtures/replay_events.jsonl") > 0
    assert os.path.exists("fixtures/replay_snapshot.json"), "run seed.py first to produce the replay snapshot"

    print("DEMO CHECK: PASS")

if __name__ == "__main__":
    main()
```
**Acceptance**: `python seed.py` at least once, then `python check_demo.py` → `DEMO CHECK: PASS`,
no assertion errors. If `n_calls == 0` or the replay-file assertions fail, the run genuinely FAILS
(no silent substitution) — fix logging or re-run `seed.py` before proceeding.

### Task 10 — Demo integration, replay rehearsal & submission [Both lanes, 30 min + 20 min buffer]
Merge Lane A + Lane B work (both touched only their own files — this is import wiring, not
conflict resolution): confirm `app.py` imports resolve, run `python seed.py` fresh, run
`streamlit run app.py`, walk the full Jordan-equivalent flow once with a throwaway name through
ALL FOUR kiosk states (`idle → first_visit_form → saved → idle → return_greeting`), then
`mem.delete_user(...)` + `snow.delete_customer(...)` that throwaway identity so the live
volunteer's tap-in is a genuine first-time capture on stage. Also run
`REGULARS_REPLAY=1 streamlit run app.py` once and confirm Sam + Owner Dashboard render with zero
errors (the outage-fallback rehearsal).

**[HUMAN] Submission (20-minute buffer starting 15:40, before the 16:00 HARD deadline)**:
1. **15:40** — Freeze code: no further edits except a critical live-blocking bug.
2. Run `python check_demo.py` one final time — must print `DEMO CHECK: PASS`.
3. Run `python seed.py` one final time so `replay_snapshot.json`/`replay_events.jsonl` reflect the
   frozen code.
4. Re-run the `REGULARS_REPLAY=1 streamlit run app.py` rehearsal once — confirm zero errors.
5. **[HUMAN — name the submission owner explicitly at 11:00, not at 15:40]** submits per the
   event's actual process (confirm the exact mechanism — Devpost link, GitHub repo URL, zip
   upload — with organizers early in the day; do not assume). The submission artifact is the
   `regulars/` directory as committed to git (or a zip of it if the event requires upload) —
   push/export it, then paste the submission confirmation URL into the team channel. That
   confirmation URL, visible to both teammates, is the success check for this task.

---

## Hour-by-hour Schedule (11:00–16:00, HARD submission)

Tasks are sequenced in DEPENDENCY ORDER, not arbitrarily: fixtures (Task 7) has zero code
dependencies so it runs first; Task 9 (`check_demo.py`) is written and run LAST among Lane A's
tasks because it's the only one that needs Tasks 2/3/4/7/8 all already done (its replay-file
assertions specifically need Task 8's output) — the schedule below reflects that, so nothing is
ever invoked before the task that creates it. The numbers are computed to land exactly on the
16:00 deadline; there is no slack margin baked in, which is why the checkpoints below exist.

| Time | Lane A | Lane B |
|---|---|---|
| 11:00–11:30 | Phase 0 (together) | Phase 0 (together) |
| **11:30** | **— FIXTURE-SCOPE DECISION (instant, both) — decide NOW, before Task 7 starts, whether background customers will be 6 (default) or fewer if the team expects a tight afternoon —** | |
| 11:30–11:50 | Task 7: fixtures (20 min) | Task 5: greeting.py (20 min) |
| 11:50–12:20 | Task 1: schema + smoke ext. (30 min) | Task 6: idle/first_visit_form states |
| 12:20–12:35 | **Lunch overlap** | **Lunch overlap** |
| 12:35–13:05 | Task 2: profile_store.py (30 min) | Task 6: saved/reset state |
| **13:05** | **— SOFT CHECKPOINT (real progress check) — if Lane A is visibly behind, Lane B/human pulls Task 3 or 4 now (pure Python, no Streamlit state, safe to hand off) —** | |
| 13:05–13:45 | Task 3: flourish.py (40 min) | Task 6: return_greeting + memory panel |
| 13:45–14:15 | Task 4: economics.py (30 min) | Task 6: Owner Dashboard, 3 cost tiers |
| **14:15** | **— HARD CUT LINE CHECK — drop cut-line items below if behind — Tasks 8/9/10 below are the minimum-proof path and are NOT cut —** | |
| 14:15–14:50 | Task 8: seed.py + benchmark.py (35 min) | Task 6: replay-mode branch + polish/wrap |
| 14:50–15:10 | Task 9: check_demo.py (20 min) — **this IS the minimum-proof checkpoint**: it can only run for real now, because Task 8 just produced the replay files and Tasks 2–4 already exist | Lane B assists Task 9 if needed, else finishes Task 6 |
| 15:10–15:40 | Task 10: integration run-through, full 30 min (both, incl. `--replay` rehearsal and the Sam-live fallback test) | same |
| 15:40–16:00 | **[HUMAN]** Submission buffer, full 20 min (freeze → check_demo → seed → replay rehearsal → submit) | same |

**Never cuttable, regardless of time pressure** (required by contract/fixes, not polish): the
three-tier cost display including the billed-receipts expander; the `--replay` outage fallback;
the Sam-live volunteer-failure fallback; the explicit kiosk state machine (`idle → first_visit_form
→ saved → return_greeting`) and its reset actions; the allergy CONFIRM toggle; Tasks 8, 9, and 10
themselves (they ARE the minimum proof — nothing below cuts into their time).

**Cut line (drop first if behind at 14:15, in this order — chosen to protect the items above)**:
1. Cohort sensitivity slider → hardcode `lift_relative=0.10`, remove the `st.slider`.
2. Owner Dashboard "recent activity feed" panel → cut entirely (not required by any fix).
3. The optional "anything new since last time?" return-visit field (Task 6) → cut; keep
   `location_margin()`'s steady-state assumption as a disclosed MODEL rather than a live UI
   affordance.
4. Background customer count in `fixtures/regulars_fixtures.json` → this was already decided at
   the 11:30 fixture-scope decision (before Task 7 was written), not reopened here.
5. Owner Dashboard visual polish (extra styling beyond default Streamlit dark) → skip.

---

## Fixtures Spec

### Kiosk conversation script — planted volunteer ("Jordan"), exact lines

**Visit 1 — live capture (on stage):**
1. Staff: *"Hey! Welcome in — first time here?"*
2. Volunteer: *"Yeah, first time."*
3. Kiosk (`idle` state): *"New here? Enter your name or phone (last 4 digits) to start a tab."*
   Volunteer types name `Jordan`, phone last-4 `4471`, taps in — kiosk mints a fresh `session_id`
   and moves to `first_visit_form`.
4. Kiosk: *"Nice to meet you, Jordan! What'll you have?"* Volunteer types `Oat-milk cortado`.
5. Kiosk: *"Any dietary notes or allergies we should know?"* Volunteer types `Gluten-free — celiac`;
   taps the "This is an ALLERGY" toggle ON, then checks "I confirm this allergy information."
6. Kiosk: *"Tell us something about you — we'll remember it for next time."* Volunteer types
   `Training for the marathon this Sunday, kind of nervous about it!`
7. Volunteer taps Save. Kiosk moves to `saved`: *"Thanks, Jordan! Profile saved."* — no greeting or
   memory panel yet (that would spoil the reveal). Staff taps "Next customer" → kiosk returns to
   `idle`. **This is where the ~60-second gap lives — filled by the Owner Dashboard/margin beat
   below, not dead air.**

**Visit 2 — live return, after the margin-dashboard beat (new `session_id`, same `user_id`):**
1. Staff: *"Now — Jordan's back."* Volunteer taps in again with the same name/phone; kiosk mints a
   SECOND, different `session_id` and (because the profile is now known) goes straight to
   `return_greeting`.
2. Kiosk renders: `Hey Jordan! The usual oat-milk cortado? <flourish> Allergy noted on this order
   (gluten-free — celiac) — please confirm with staff.` — `<flourish>` is the extracted
   `followup_question`, expected close to *"How'd the marathon go?"*; if extraction degraded to
   `DEFAULT_FLOURISH`, expect *"Good to see you again!"* instead — rehearse both, both are fine on
   stage. Note the upsell line only states the fact was noted on the order — it never claims any
   kitchen action was taken or that any dish is safe.
3. Staff: *"A minute ago this had never seen Jordan. Now it remembers the order, the allergy, and
   asks about the marathon — zero live LLM calls on this exact screen, it's all pulled from what's
   on file. And look —"* (points at memory panel) *"— that's a brand-new session ID next to the
   original one from a minute ago."*

### Full `fixtures/regulars_fixtures.json` content
```json
{
  "background_customers": [
    {"name": "Priya", "phone_last4": "1201", "usual_order": "Chai latte", "dietary_note": null, "is_allergy": false, "personal_detail": "Just got a new job downtown."},
    {"name": "Marcus", "phone_last4": "3390", "usual_order": "Drip coffee, black", "dietary_note": "Lactose intolerant", "is_allergy": false, "personal_detail": "Coaches his daughter's soccer team on Saturdays."},
    {"name": "Elena", "phone_last4": "5567", "usual_order": "Matcha oat latte", "dietary_note": "Gluten allergy", "is_allergy": true, "personal_detail": "Studying for the bar exam."},
    {"name": "Devon", "phone_last4": "7712", "usual_order": "Cold brew, splash of cream", "dietary_note": null, "is_allergy": false, "personal_detail": "Recently moved to the neighborhood."},
    {"name": "Fatima", "phone_last4": "4402", "usual_order": "Americano, extra hot", "dietary_note": "Nut allergy", "is_allergy": true, "personal_detail": "Training a new puppy named Waffles."},
    {"name": "Ravi", "phone_last4": "6689", "usual_order": "Chai, oat milk, extra hot", "dietary_note": "Vegan", "is_allergy": false, "personal_detail": "Just ran his first 10K."}
  ],
  "fallback_persona": {
    "name": "Sam", "phone_last4": "8823", "usual_order": "Iced oat-milk latte, extra shot",
    "dietary_note": "Tree nut allergy", "is_allergy": true,
    "personal_detail": "Just adopted a rescue dog named Biscuit!",
    "expected_flourish_followup": "How's Biscuit settling in?"
  },
  "volunteer_script": {
    "display_name_on_stage": "Jordan", "phone_last4": "4471", "usual_order": "Oat-milk cortado",
    "dietary_note": "Gluten-free — celiac", "is_allergy": true,
    "personal_detail": "Training for the marathon this Sunday, kind of nervous about it!",
    "visit2_expected_greeting_contains": ["Hey Jordan!", "oat-milk cortado", "Allergy noted on this order"]
  }
}
```
Note: the 6 background customers + Sam + Jordan are individually seeded records for the memory-panel
and activity-feed demo only. The `250` figure in the Owner Dashboard's margin math is a stated
**assumption** representing a real café's active customer count, not 250 literal seeded rows —
labeled on screen as *"assumed location size: 250 active customers/mo."*

### Pre-seeded fallback persona — "Sam" (seeded before doors open) — TWO DISTINCT FALLBACK TIERS
Sam's full profile is the `fallback_persona` object above, seeded **deterministically** by
`seed.py` (Task 8) — no LLM call, the flourish text is written verbatim from
`expected_flourish_followup` and read-back verified before doors open.

**Tier 1 — Sam-LIVE (volunteer/state failure, services healthy)**. Trigger: (a) the live
volunteer's own write fails —
`profile_store.get_profile_fields()` returns an empty dict for Jordan's `user_id` right after
Save while Snowflake/EverOS themselves are reachable, or (b) the live volunteer visibly freezes
for >10 seconds, or a wrong value gets typed and Save was already clicked. Staff says *"Let's look
at a customer we've had for a while instead"* and taps in `8823` on the STILL-RUNNING live kiosk —
this is still a real read against real services, just against a guaranteed-good record instead of
an improvised one.

**Tier 2 — REPLAY (full outage, services unreachable)**. Trigger: any Snowflake or EverOS call
raises a connection error/timeout such that NO live call of any kind will succeed (Sam-live would
ALSO fail here, since her greeting still reads real services). Staff restarts the kiosk with
`REGULARS_REPLAY=1 streamlit run app.py` (or `streamlit run app.py -- --replay`), which renders
Sam's greeting, memory panel, and the full Owner Dashboard entirely from
`fixtures/replay_snapshot.json` — zero external calls, a visible "REPLAY MODE" banner, and no
attempt to contact either service.

Both tiers use the SAME Sam identity (`8823`) so the on-stage script doesn't have to branch —
only the underlying data source changes.

---

## 3-Minute Demo Script

| Time | Beat | Live vs. pre-seeded |
|---|---|---|
| 0:00–0:15 | Hook: *"Meet Regulars — the Cheers effect, as a service, for any small business."* Kiosk `idle` screen (Terracotta & Oat branding, big "Tap in" button). | LIVE (idle UI, no data) |
| 0:15–0:45 | "Jordan" taps in as a brand-new customer, live: name/order/allergy (toggle+confirm)/personal detail → Save → `saved` confirmation. | **LIVE** — real `edit()` profile write + real `add()+flush()` episode + one real haiku flourish-extraction call |
| 0:45–0:50 | Staff: *"Saved. While that settles in, let's look at what this actually costs."* Switch to Owner Dashboard. | transition |
| 0:50–1:35 | **Margin-dashboard beat — fills the ~60-second gap since Save, not dead air.** Three cost tiers shown: measured tokens, estimated $/customer/mo, and the billed-receipts expander (Snowflake's own metering). *"Fractions of a cent per visit — measured, right here — against a $49/mo price versus $150–300/mo tools that don't remember anything."* | **LIVE** Snowflake queries — real measured numbers, all three tiers |
| 1:35–1:40 | Staff: *"Now — Jordan's back."* Switch to kiosk, tap in again. | transition |
| 1:40–2:05 | Jordan taps in again (kiosk mints a SECOND, different `session_id`) → `return_greeting` renders: *"Hey Jordan! The usual oat-milk cortado? How'd the marathon go? Allergy noted on this order (gluten-free — celiac) — please confirm with staff."* Staff: *"Zero live LLM calls on this screen — assembled entirely from what's on file."* | **LIVE** — deterministic render, zero LLM calls, proves cross-session memory via the new `session_id` |
| 2:05–2:30 | Memory panel deep-dive: current session_id shown NEXT TO the older originating session_id, exact profile fields EverOS returned, episode snippet, allergy badge. *"Every field here is something EverOS actually stored, and that's a brand-new session ID next to the original one."* | LIVE reads (profile) + cached record (episode), both labeled |
| 2:30–2:50 | Cohort chart: *"Here's what memory-driven return visits could be worth over a simulated 56-day, 8-week window — 200 simulated customers, seeded, disclosed."* SIMULATED watermark; Bain context line shown. | SIMULATED, clearly labeled on screen |
| 2:50–3:00 | Closing: *"The cost is real. The cohort is simulated — we said so. What's a memory worth in revenue? We just showed you both halves of that number."* | — |

**Unforgettable moment**: 1:40–2:05 — the reveal, because the audience watched the write happen
about a minute earlier (filled productively by the margin-dashboard beat, not silence) and can see
the `session_id` is new.

### Rehearsal checklist
- [ ] `python smoke.py` passes clean within 30 minutes of doors opening (go/no-go gate).
- [ ] `python seed.py` run fresh, < 2 min, no errors, prints the Sam-verified-deterministic line —
      confirms the "wifi died" rebuild path AND idempotency across both EverOS and Snowflake.
- [ ] Dry-run the full Jordan flow once with a throwaway identity through all four kiosk states
      (`idle → first_visit_form → saved → idle → return_greeting`), then `mem.delete_user(...)` +
      `snow.delete_customer(...)` it so the on-stage volunteer capture is genuinely first-time.
- [ ] **flush() discipline**: every `mem.remember()` call is immediately followed by `flush()`
      inside `mem.remember()` itself — grep the codebase for bare `_client.add(` outside `mem.py`
      before rehearsal and remove any hits found.
- [ ] Sam-live round-trips correctly: tap in `8823` on the running kiosk, greeting renders Sam's
      order + the Biscuit follow-up line with zero manual steps.
- [ ] **`REGULARS_REPLAY=1 streamlit run app.py` rehearsed at least once**: confirm Sam + the full
      Owner Dashboard render from `fixtures/replay_snapshot.json` with the REPLAY MODE banner
      visible and zero errors — this is the OUTAGE fallback, distinct from Sam-live.
- [ ] **Both fallback trigger criteria rehearsed explicitly and distinguished out loud**: Sam-live
      (services healthy, volunteer/state failure) vs. `--replay` (services unreachable) — practice
      the verbal pivot line and the physical action for each at least twice.
- [ ] Time the walkthrough with a stopwatch at least twice; it must fit inside 3:00.
- [ ] Confirm the cohort chart's SIMULATED caption ("56-day, 8-week") and Bain context line are
      visible without scrolling at the presentation display's resolution.

---

## Risk Table

| # | Risk | Trigger | Fallback |
|---|---|---|---|
| 1 | EverOS silent write failure on episode `add()`/`flush()` (documented open issue) | `verify_everos_has_episode()` returns `False` for the expected originating session during rehearsal, or `get("profile")` is empty right after a successful `edit()` | Greeting/flourish are sourced from the Snowflake cache written at capture time, never a live EverOS read — the reveal is immune. If the profile round trip itself fails for the live volunteer while services are otherwise healthy, cut over to Sam-LIVE (tier 1, `8823` on the running kiosk). |
| 2 | Flourish extraction whiff (malformed/non-JSON Cortex output) | `json.loads`/`jsonschema.validate` raises inside `extract_and_store_flourish` | `DEFAULT_FLOURISH` used automatically — reveal never breaks; the Snowflake cache write still happens unconditionally. Structured profile fields (name/usual/dietary/allergy) are unaffected — they bypass LLM extraction entirely via direct `edit()`. |
| 3 | Live volunteer freezes or goes off-script | Staff judgment call, >10s dead air at the kiosk | Printed script cards with the exact lines above; if still stuck, pivot to Sam-LIVE (tier 1) per the rehearsed trigger line. |
| 4 | Snowflake or EverOS itself unreachable mid-demo (connection error/timeout — a FULL outage, distinct from risk #3) | Any exception surfaces from a live Snowflake/EverOS call | Switch to `REGULARS_REPLAY=1 streamlit run app.py` (tier 2) — renders Sam's full reveal and the entire Owner Dashboard from `fixtures/replay_snapshot.json`, zero external calls. Sam-LIVE would ALSO fail here since it still reads real services, so replay is the only valid fallback for this specific risk. |
| 5 | Venue wifi down before going on stage | `python smoke.py` fails at the pre-stage go/no-go check | `python seed.py` again once connectivity returns (<2 min); if still down at go-time, run the ENTIRE demo in `--replay` mode from the start rather than attempting any live call. |

---

## Q&A Cheat Sheet

**Q1: "Isn't the cohort simulation just made up?"**
Yes — and we say so on screen. It's a seeded simulation (RNG(42), 200 customers, 8 weekly cycles =
56 days, not 60 — we say that number honestly too), with a disclosed, conservative +10% relative
visit-lift assumption (slider shows 5–20% sensitivity), $6.50 AOV, 70% margin — none of that is
measured behavioral data, because we don't have 56 real days to test with this afternoon. What IS
real: the Cortex cost per interaction (measured from actual logged calls, shown in three labeled
tiers — measured tokens, estimated $, and Snowflake's own billed-receipts corroboration) and the
$49-vs-$150–300/mo pricing comparison (real published prices). We simulate the part we can't
measure in an afternoon and measure everything we can.

**Q2: "How do I know the memory panel isn't hardcoded — what if EverOS is actually down?"**
The memory panel calls EverOS's own `get("profile")` live and prints back exactly what it returns —
nothing there is a literal in our code. We do know about a documented EverOS bug where episode writes
can silently no-op, which is exactly why the return-visit greeting renders from a Snowflake cache
captured at write time rather than a live re-read — that field deliberately does NOT depend on EverOS
being up at reveal time. The profile round trip (name/usual/dietary), by contrast, is live end-to-end
in front of you.

**Q3: "How is this different from a loyalty app like Fivestars or Thanx?"**
Those track points and send generic blasts — no idea what was actually said at the counter. There's no
"how'd the marathon go," no allergy note reaching the barista, because there's no memory layer, just a
punch card. Regulars is built on an actual memory system (EverOS), so the personalization is
conversational, not transactional — and it costs a fraction of what those tools charge, because the
"smart" part is a few thousandths of a cent of Cortex inference per visit, not a sales team and a
big SaaS platform.
