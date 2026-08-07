"""ledger.py — insert/query layer + rent/earn/net attribution SQL (Lane A, Task 3).

Ledger math (pinned): every bundle retrieved into a question's memory-arm context pays
RENT = the tokenizer-estimated (cl100k_base) token count of its own formatted block in that
prompt x published rate (an ESTIMATE of that bundle's share of the prompt). A bundle EARNS on
a question only if it is in that question's supporting-evidence set AND the memory arm answered
correctly; earnings = that question's paired-arm token savings (naive - memory prompt tokens,
both MEASURED request-level totals), split evenly across the supporting bundles retrieved for
it. NET = earned - rent.

Two distinct labels, never conflated: request-level naive/memory prompt tokens (and therefore
tokens_saved_for_question, earned_dollars) are MEASURED; per-bundle bundle_tokens/rent_dollars
is TOKENIZER-ESTIMATED.

Self-contained: depends only on snow.py, no dependency on bundles/benchmark.
"""
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
