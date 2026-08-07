"""bootstrap.py — run ONCE (Lane A, Phase 0).

Explicit two-step connection order (binding sequence per SHARED-CONTRACT R1 #3):
  raw connection with NO database/schema -> separate CREATE DATABASE
  -> reconnect WITH database/schema -> separate CREATE TABLE statements.
The connector does not run multi-statement strings by default, so every DDL
statement is its own cur.execute().
"""
from dotenv import load_dotenv; load_dotenv()
import os, snowflake.connector


def main():
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
    print("bootstrap OK: HACKDB.PUBLIC created, llm_call_log ready")


if __name__ == "__main__":
    main()
