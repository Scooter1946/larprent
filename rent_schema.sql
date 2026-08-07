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
