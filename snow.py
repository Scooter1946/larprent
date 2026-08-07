"""snow.py — shared data + LLM module, now DUAL-BACKEND (Lane A, Phase 0; supervisor local-mode patch).

Every LLM call still goes through `ai_complete()` (which logs to `llm_call_log`) and every DB touch
still goes through `get_conn()` — the swap happens INSIDE this module, nowhere else:

  RENT_BACKEND=local (default)      SQLite file (rent_local.db) behind a paramstyle/DDL-translating
                                    cursor shim — the rest of the codebase keeps its Snowflake SQL.
                                    Default per team decision (reported organizer confirmation that
                                    Snowflake is not a hard requirement — VERIFY in the event Discord).
  RENT_BACKEND=snowflake            Snowflake tables + Cortex AI_COMPLETE — the sponsor-judging
                                    configuration: real metering, the ACCOUNT_USAGE receipts panel,
                                    and Cortex-hosted models. Run this at the event if the account
                                    works; it is strictly more credible on stage.

  RENT_LLM=cortex (default)         Snowflake Cortex AI_COMPLETE with show_details (MEASURED tokens).
  RENT_LLM=openai                   Any OpenAI-compatible endpoint via stdlib urllib —
                                    OPENAI_API_KEY, OPENAI_MODEL (default gpt-4o-mini), and
                                    OPENAI_BASE_URL (default api.openai.com; point it at
                                    http://localhost:11434/v1 for free local Ollama). MEASURED tokens
                                    from the API's usage object.
  RENT_LLM=mock                     Deterministic pipeline-test model: answers a fixture question
                                    correctly ONLY IF its supporting bundle text actually made it
                                    into the prompt (so retrieval is genuinely exercised), else
                                    "I don't know". Tokens are tiktoken ESTIMATES; every surface
                                    shows model='mock'. For mechanics dry-runs only — never demo it
                                    as real inference.
"""
from dotenv import load_dotenv; load_dotenv()
import json
import os
import re
import sqlite3
import urllib.request

# Default is LOCAL (organizers confirmed Snowflake is not a hard requirement); set
# RENT_BACKEND=snowflake to flip the full Snowflake+Cortex path back on for sponsor judging.
BACKEND = os.environ.get("RENT_BACKEND", "local")
LLM = os.environ.get("RENT_LLM", "cortex" if BACKEND == "snowflake" else "mock")
LOCAL_DB = os.environ.get("RENT_LOCAL_DB", "rent_local.db")

# Credits per 1M tokens (published rates). See docs/research-snowflake.md §1.
MODEL_RATES = {
    "mistral-7b": 0.12,
    "claude-haiku-4-5": 0.35,
    "openai-gpt-5-mini": 0.32,
    "claude-sonnet-5": 2.6,
    "claude-opus-class": 12.0,
}
USD_PER_CREDIT = 2.00


def rate_for(model: str) -> float:
    return MODEL_RATES.get(model, 0.35)   # unknown/local models: haiku-class placeholder rate, labeled est.


# --------------------------------------------------------------------------------------------------
# DB backends
# --------------------------------------------------------------------------------------------------
_PARSE_JSON_RE = re.compile(r"PARSE_JSON\((%\(\w+\)s|%s)\)", re.IGNORECASE)
_NAMED_RE = re.compile(r"%\((\w+)\)s")
_DDL_MAP = [(re.compile(p, re.IGNORECASE), r) for p, r in [
    (r"\bSTRING\b", "TEXT"), (r"\bTIMESTAMP_LTZ\b", "TEXT"), (r"\bVARIANT\b", "TEXT"),
    (r"UUID_STRING\(\)", "(lower(hex(randomblob(16))))"), (r"CURRENT_TIMESTAMP\(\)", "CURRENT_TIMESTAMP"),
]]


def _translate(sql: str) -> str:
    """Snowflake SQL -> SQLite SQL for the small dialect surface this codebase uses."""
    if "ACCOUNT_USAGE" in sql:
        raise RuntimeError("receipts (ACCOUNT_USAGE) exist only on the Snowflake backend")
    sql = _PARSE_JSON_RE.sub(r"\1", sql)          # PARSE_JSON(%s) -> %s (json stored as TEXT locally)
    for pat, rep in _DDL_MAP:
        sql = pat.sub(rep, sql)
    sql = _NAMED_RE.sub(r":\1", sql)               # %(name)s -> :name
    return sql.replace("%s", "?")                  # positional


class _LocalCursor:
    def __init__(self, cur): self._c = cur
    def execute(self, sql, params=None):
        if sql.strip().upper().startswith("ALTER SESSION"):
            return self                                  # QUERY_TAG: Snowflake-only, no-op locally
        self._c.execute(_translate(sql), params if params is not None else [])
        return self
    def executemany(self, sql, seq): self._c.executemany(_translate(sql), seq); return self
    def fetchone(self): return self._c.fetchone()
    def fetchall(self): return self._c.fetchall()
    @property
    def description(self): return self._c.description
    @property
    def connection(self): return _LocalConn._instance


class _LocalConn:
    _instance = None
    def __init__(self):
        self._db = sqlite3.connect(LOCAL_DB, check_same_thread=False)   # Streamlit reruns cross threads
        _LocalConn._instance = self
    def cursor(self): return _LocalCursor(self._db.cursor())
    def commit(self): self._db.commit()
    def close(self): pass                                # module-lifetime singleton; nothing to do


_local = None


def get_conn():
    """Snowflake (PAT-as-password) or the SQLite shim, decided by RENT_BACKEND."""
    global _local
    if BACKEND == "local":
        if _local is None:
            _local = _LocalConn()
        return _local
    import snowflake.connector
    return snowflake.connector.connect(
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PAT"],
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        database=os.environ.get("SNOWFLAKE_DATABASE", "HACKDB"),
        schema=os.environ.get("SNOWFLAKE_SCHEMA", "PUBLIC"),
    )


# --------------------------------------------------------------------------------------------------
# LLM backends
# --------------------------------------------------------------------------------------------------
def _cortex_call(cur, model, prompt, model_parameters):
    cur.execute("SELECT AI_COMPLETE(model => %(model)s, prompt => %(prompt)s, "
                "model_parameters => PARSE_JSON(%(mp)s), show_details => TRUE) AS resp",
                {"model": model, "prompt": prompt, "mp": json.dumps(model_parameters or {})})
    raw = cur.fetchone()[0]
    resp = json.loads(raw) if isinstance(raw, str) else raw
    # Field names confirmed against the live response in Phase 0 smoke (SHARED-CONTRACT item 12).
    return resp["choices"][0]["messages"], {"prompt_tokens": resp["usage"]["prompt_tokens"],
                                             "completion_tokens": resp["usage"]["completion_tokens"]}


def _openai_call(prompt, model_parameters):
    body = json.dumps({"model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": (model_parameters or {}).get("temperature", 0),
                        "max_tokens": (model_parameters or {}).get("max_tokens", 200)}).encode()
    req = urllib.request.Request(
        os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/chat/completions",
        data=body, headers={"Content-Type": "application/json",
                             "Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', 'ollama')}"})
    resp = json.loads(urllib.request.urlopen(req, timeout=60).read())
    u = resp.get("usage", {})
    return (resp["choices"][0]["message"]["content"],
            {"prompt_tokens": u.get("prompt_tokens", 0), "completion_tokens": u.get("completion_tokens", 0)})


def _mock_call(prompt):
    """Pipeline-test model: correct ONLY if the supporting bundle's text is actually in the prompt —
    retrieval is genuinely exercised; generation is not (tokens are tiktoken ESTIMATES)."""
    import tiktoken
    from rent_fixtures import load_world
    enc = tiktoken.get_encoding("cl100k_base")
    world = load_world()
    by_id = {b["bundle_id"]: b for b in world["bundles"]}
    answer = "I don't know"
    for q in world["questions"]:
        if q["query"].rstrip("?").lower() in prompt.lower():
            sup = q["supporting_bundle_ids"][0]
            if by_id[sup]["content"][:60].lower() in prompt.lower():
                gold = q["gold_answer"]
                answer = gold[0] if isinstance(gold, list) else gold
            break
    return answer, {"prompt_tokens": len(enc.encode(prompt)), "completion_tokens": len(enc.encode(answer))}


def ai_complete(model, prompt, purpose, run_id, user_id=None, session_id=None, agent_tag=None,
                 model_parameters=None, extra=None):
    """One LLM call through the active backend + a llm_call_log row before returning.
    Returns (text, usage) with prompt_tokens/completion_tokens (MEASURED on cortex/openai;
    tiktoken-ESTIMATED on mock)."""
    conn = get_conn(); cur = conn.cursor()
    cur.execute("ALTER SESSION SET QUERY_TAG = %s", (f"{run_id}:{agent_tag or purpose}",))
    if LLM == "cortex":
        text, usage = _cortex_call(cur, model, prompt, model_parameters)
        logged_model = model
    elif LLM == "openai":
        text, usage = _openai_call(prompt, model_parameters)
        logged_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    else:
        text, usage = _mock_call(prompt)
        logged_model = "mock"
    cur.execute("INSERT INTO llm_call_log (model, purpose, prompt_tokens, completion_tokens, "
                "credits_est, user_id, session_id, extra) VALUES (%s,%s,%s,%s,%s,%s,%s,PARSE_JSON(%s))",
                (logged_model, purpose, usage["prompt_tokens"], usage["completion_tokens"],
                 (usage["prompt_tokens"]+usage["completion_tokens"])/1e6*rate_for(logged_model),
                 user_id, session_id, json.dumps({"run_id": run_id, "agent_tag": agent_tag, **(extra or {})})))
    conn.commit()
    usage["model"] = logged_model   # the model that ACTUALLY served — rows/captures must record this,
    return text, usage              # never the requested constant (they diverge in openai/mock modes)
