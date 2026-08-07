# Snowflake Engineering Brief — Token Economy Hackathon (5-hour build window)

## 1. Cortex LLM functions — current state (Aug 2026)

Two overlapping surfaces exist. Use `AI_COMPLETE` (newer, GA) — `SNOWFLAKE.CORTEX.COMPLETE` still works but is the legacy name.

**Minimal SQL call:**
```sql
SELECT AI_COMPLETE('claude-sonnet-5', 'Explain the token economy in one sentence.');

-- with params
SELECT AI_COMPLETE(
  model => 'claude-sonnet-5',
  prompt => 'Summarize this support ticket: ' || ticket_text,
  model_parameters => {'temperature': 0.2, 'max_tokens': 200}
) AS summary
FROM tickets LIMIT 10;
```
This is the single fastest "impressive Snowflake integration" available: one SQL statement, no infra, runs over a whole table in a normal `SELECT`.

**Available models (per `aisql-regional-availability` docs):**
| Tier | Models | Context | Notes |
|---|---|---|---|
| Large | `claude-opus-5` (preview), `claude-opus-4-8`, `gemini-3.1-pro` (preview) | up to 1M tokens | Opus models: AWS US/EU/APJ/AU, Azure US/EU, GCP US. Gemini: AWS US/EU only |
| Medium | `claude-sonnet-5`, `claude-sonnet-4-6`, `llama3.3-70b` | up to 1M (Claude) / 128K (Llama) | Claude broadly available cross-region; Llama needs native region (AWS US, EU-Frankfurt/Ireland, APJ-Sydney/Tokyo) |
| Small | `claude-haiku-4-5`, `llama3.1-8b`, `mistral-7b`, `openai-gpt-5-mini` | 200K / 128K / 32K / 272K | cheapest, fastest — good for high-volume demo loops |

So yes: **Claude, Llama (Meta), Mistral, and OpenAI models are all hosted directly in Cortex** — no separate API keys needed, just SQL.

**Pricing:** billed in "AI Credits" per million tokens, rate varies by model; both input+output tokens count for `AI_COMPLETE`/`AI_CLASSIFY`/`AI_TRANSLATE`/`SUMMARIZE` (embedding functions bill input only). Exact numbers found (credits per M tokens, from the Snowflake Service Consumption Table via secondary sources — treat as approximate, confirm against your account's `Table 6` before finance-sensitive demos):
- `mistral-7b`: ~0.12 credits
- `openai-gpt-5-mini`: ~0.32 credits
- `llama3.1-70b`: ~1.21 credits
- `openai-gpt-4.1`: ~1.40 credits
- `llama-3.1-405b`: ~3 credits
- `claude-4-opus` class: ~12 credits
- Range cited elsewhere: **$0.12–$5.10 per million tokens** in dollar terms once converted
- **Credit price: $2.00/credit (global/cross-region routing) or $2.20/credit (pinned to home region)**

This $/credit + credits/M-tokens combo is exactly the kind of real number a judge will want to see in a live dashboard — good hackathon material.

## 2. Cortex Agents API

Cortex Agents orchestrate **Cortex Analyst** (text-to-SQL, structured data) + **Cortex Search** (hybrid/semantic search over docs) + arbitrary custom tools (UDFs/stored procs) behind one conversational endpoint. You declare instructions like "for revenue questions use Analyst, for policy questions use Search" and the agent routes.

Two ways to call it:
- **Stateless (fastest for hackathon)** — no agent object needed, full config inline:
  `POST https://<account>.snowflakecomputing.com/api/v2/cortex/agent:run`
- **Stateful** — create a named agent object first (`POST .../api/v2/databases/{db}/schemas/{schema}/agents`), then call `.../agents/{name}:run`. Better for multi-turn/reusable agents, more setup.

```python
import requests
headers = {
    "Authorization": "Bearer <TOKEN>",
    "Content-Type": "application/json",
    "Accept": "text/event-stream",
}
payload = {
    "messages": [{"role": "user", "content": [{"type": "text", "text": "What is total revenue for 2023?"}]}],
    "stream": True,
}
resp = requests.post(
    "https://<account>.snowflakecomputing.com/api/v2/cortex/agent:run",
    headers=headers, json=payload, stream=True,
)
for line in resp.iter_lines():
    if line: print(line.decode())
```
Response is Server-Sent Events by default (`response.text.delta`, `response.tool_use`, `response.tool_result`, final `response`); set `stream: false` for one JSON blob (much easier to demo/debug in a hurry). You can set an explicit **token/time budget** in the orchestration config (`budget: {seconds, tokens}`) — directly relevant to a "token economy" theme (cost-capped agents).

**Setup effort estimate:** stateless agent hitting one Cortex Search service + one Cortex Analyst semantic model = roughly **1.5–2.5 hours** for a team unfamiliar with Snowflake (mostly spent standing up the semantic model / search service, not the API call itself). Skipping Analyst/Search and just wiring the agent to a single custom tool (a UDF) is faster, ~45–60 min.

## 3. Fastest zero-to-demo path

1. **Trial signup**: `signup.snowflake.com` — instant account creation, no payment info. **$400 free credits**, usable within **30 days**. Do this literally first — email verification + region/cloud selection is the only friction (~5 min).
2. **Auth from a local Python script — use a Programmatic Access Token (PAT)**, not key-pair, not password:
   ```python
   import snowflake.connector
   conn = snowflake.connector.connect(
       user="YOUR_USER",
       password="<programmatic_access_token>",   # PAT drops in as password
       account="your_account_locator",
       warehouse="COMPUTE_WH",
       database="HACKDB",
       schema="PUBLIC",
   )
   ```
   PATs (native since connector v3.12, Apr 2025) avoid MFA prompts and avoid generating/registering an RSA keypair — fastest path for a 5-hour clock. Key-pair auth is the "correct" production pattern but costs you 10–15 extra minutes you don't have. Plain password auth is being phased out / will hit MFA friction — avoid.
3. **Python connector vs Snowpark**: `pip install snowflake-connector-python` for raw SQL (simplest, use for the event-log + AI_COMPLETE calls). Add `snowflake-snowpark-python` only if you want DataFrame-style transforms — not necessary for a 5-hour scope.
4. **Streamlit: run locally against Snowflake, don't use Streamlit-in-Snowflake.** Local Streamlit + `snowflake-connector-python` (or `st.connection("snowflake")`) gives you normal hot-reload, your own editor, and no fighting Snowsight's in-browser IDE. Streamlit-in-Snowflake is nice for zero-install *sharing* but costs setup time (upload/stage the app, permissions, slower iteration loop) that isn't worth it for a 5-hour build — reserve it only if a judge specifically wants "runs entirely inside Snowflake" for scoring purposes. Verdict: **local Streamlit wins on speed to demo.**

Total realistic time-to-first-`AI_COMPLETE`-call-from-Python: **20–30 minutes** (signup + PAT + connector install + one query), leaving the remaining ~4.5 hours for the actual product.

## 4. Token-economy angles (this is the theme — lean into it)

**A. Event-log table for every LLM call** — trivially demoable, plays directly to the theme:
```sql
CREATE TABLE llm_call_log (
  call_id STRING DEFAULT UUID_STRING(),
  ts TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
  model STRING,
  prompt_tokens INT,
  completion_tokens INT,
  latency_ms INT,
  credits_est FLOAT,
  user_id STRING,
  request_text STRING,
  response_text STRING
);
```
Wrap every `AI_COMPLETE` call (or Agent call) in Python/SQL to insert a row (`AI_COMPLETE(..., show_details => TRUE)` returns token counts + model in the response object — use that instead of estimating). Then build a Streamlit dashboard over it: cost per user/session, $/query, running spend vs. budget, cost-per-model comparison (route cheap queries to `mistral-7b`, escalate to `claude-sonnet-5` only when needed — a genuinely good "token economy" demo narrative).

**B. Query Snowflake's own metering for real cost data** — strong "we didn't fake this" credibility signal for judges:
```sql
SELECT start_time, end_time, function_name, model_name,
       credits, metrics
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY
WHERE start_time >= DATEADD('hour', -6, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```
Use `CORTEX_AI_FUNCTIONS_USAGE_HISTORY` (current, GA) — **not** `CORTEX_FUNCTIONS_USAGE_HISTORY`, which is deprecated/frozen (superseded by `CORTEX_AISQL_USAGE_HISTORY`/`CORTEX_AI_FUNCTIONS_USAGE_HISTORY`). Columns: `start_time/end_time` (1-hour buckets), `function_name`, `model_name`, `query_id`, `warehouse_id`, `role_names`, `query_tag`, `user_id`, `metrics` (token/page breakdown array), `credits`, `is_completed`. Attribution by user/role/tag has been available since **Feb 16, 2026**; account-usage latency target is ~5 minutes (running queries refresh every 2 min). Caveat found in docs: these views expose a subset of raw metering events, so totals won't exactly reconcile with `METERING_HISTORY` — good for relative attribution/dashboards, not penny-perfect billing.

**C. Cost management / budgets (native, GA Mar 2026):** Snowflake now ships built-in Cortex AI Functions spend monitoring/controls (see release note "Monitor and control Cortex AI Functions spending", 2026-02-25) — worth a 10-minute look if you want to show *governed* token spend rather than just logging it yourself. Combine with the Agent `budget: {tokens, seconds}` cap from section 2 for a live "cost circuit breaker" demo.

**D. Chargeback narrative**: join `CORTEX_AI_FUNCTIONS_USAGE_HISTORY` by `user_id`/`role_names`/`query_tag` to attribute Cortex spend per team/user/feature — this is literally Snowflake's suggested chargeback pattern and requires zero custom instrumentation.

## 5. Gotchas

- **Trial account limits**: external network access, hybrid tables, and Openflow are capped at 10 credits/day until a payment method is added — irrelevant for a pure Cortex+Streamlit build, but don't plan a feature around those.
- **Preview models region-locked**: `claude-opus-5` and `gemini-3.1-pro` are Public Preview and only available in specific cross-region combos (Opus: AWS US/EU/APJ/AU + Azure US/EU + GCP US; Gemini: AWS US/EU only). If your trial account lands in an unsupported region, fall back to `claude-sonnet-5` / `claude-haiku-4-5`, which are broadly available.
- **Cross-region inference must be enabled** for many of these models to be reachable at all outside their native region — check `CORTEX_ENABLED_CROSS_REGION` account parameter if a model call errors as unavailable; this also changes billing from $2.00/credit to $2.20/credit if pinned regional routing is used instead.
- **Auth**: don't burn time on key-pair generation or fighting MFA with password auth — use a Programmatic Access Token, drop-in as the `password` field.
- **Warehouse size**: Cortex AI Functions don't get faster on bigger warehouses — Snowflake explicitly recommends staying at MEDIUM or below to avoid burning compute credits for no benefit (separate from AI credits).
- **Cortex Agents 15-minute default timeout**: fine for a demo; only relevant if you chain many tool calls — set `background: true` if you need up to 6 hours (not needed here).
- **Cost view reconciliation**: `CORTEX_AI_FUNCTIONS_USAGE_HISTORY` credits won't exactly match `METERING_HISTORY` totals — mention this explicitly if judges probe your cost numbers, it's expected/documented behavior, not a bug in your build.
- **Deprecated view trap**: several blog posts/tutorials still reference `CORTEX_FUNCTIONS_USAGE_HISTORY` (no "AI_") — it's stale, use `CORTEX_AI_FUNCTIONS_USAGE_HISTORY`.

## Recommended fastest path for a 2-person, 5-hour team

1. (0:00–0:20) Trial signup, PAT auth, local Python connecting, one `AI_COMPLETE` call working.
2. (0:20–1:00) Create `llm_call_log` table; wrap all app LLM calls (route between `mistral-7b`/`claude-haiku-4-5`/`claude-sonnet-5` by task complexity) to log tokens/cost/latency via `show_details => TRUE`.
3. (1:00–3:30) Build the actual product feature on top (chat/agent/analysis tool) — use `AI_COMPLETE` directly for simple flows; only reach for the Cortex Agents REST API (stateless `agent:run`) if you need multi-tool orchestration.
4. (3:30–4:30) Local Streamlit dashboard: cost-over-time, cost-by-model, cost-by-user, live spend vs. budget, pulling from both your own `llm_call_log` and `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY` side by side (self-tracked vs. Snowflake's-own-truth is a strong demo beat).
5. (4:30–5:00) Polish, rehearse, prep the "here's our real Snowflake credit spend" screenshot.
