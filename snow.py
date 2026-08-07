"""snow.py — shared Snowflake module (Lane A, Phase 0).

Every script after `bootstrap.py` uses `get_conn()`, which always connects WITH
database="HACKDB", schema="PUBLIC" (bootstrap.py already created them). Every LLM
call in the whole project goes through `ai_complete()`, which logs a row to
`llm_call_log` before returning — this is the ONLY path through which any LLM call
happens.
"""
from dotenv import load_dotenv; load_dotenv()
import json
import os
import snowflake.connector

# Credits per 1M tokens (published rates). See docs/research-snowflake.md §1.
MODEL_RATES = {
    "mistral-7b": 0.12,
    "claude-haiku-4-5": 0.35,
    "openai-gpt-5-mini": 0.32,
    "claude-sonnet-5": 2.6,
    "claude-opus-class": 12.0,
}
USD_PER_CREDIT = 2.00


def get_conn():
    """Connect WITH database/schema — bootstrap.py already created HACKDB/PUBLIC.
    PAT drops in as the connector `password` field (no key-pair, no plain password)."""
    return snowflake.connector.connect(
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PAT"],
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        database=os.environ.get("SNOWFLAKE_DATABASE", "HACKDB"),
        schema=os.environ.get("SNOWFLAKE_SCHEMA", "PUBLIC"),
    )


def ai_complete(model, prompt, purpose, run_id, user_id=None, session_id=None, agent_tag=None,
                 model_parameters=None, extra=None):
    """Run one AI_COMPLETE call with show_details, parse measured tokens, and log to
    llm_call_log before returning. Returns (text, usage) where usage has
    prompt_tokens/completion_tokens (MEASURED, from show_details)."""
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
