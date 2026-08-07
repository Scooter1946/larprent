"""benchmark.py — paired-arm capture (Lane A, Task 6).

Runs BOTH arms (naive full-history vs. memory top-k with TRUE no-backfill) for all 8 questions,
logging MEASURED request-level token totals (show_details) and TOKENIZER-ESTIMATED per-bundle
footprints to Snowflake, then writes captures/replay_<phase>.json for the replay UI.

  python benchmark.py --phase pre_prune  --run-id show1
  python benchmark.py --phase post_prune --run-id show1

Model fallback (Phase 0 step 7): if claude-haiku-4-5 is region-locked, change MODEL below to
openai-gpt-5-mini (one constant) and re-run — never mix models across arms mid-run.
"""
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
    golds = q if isinstance((q := question["gold_answer"]), list) else [q]   # accept a list of accepted forms, primary first
    is_correct = normalize(text) in {normalize(g) for g in golds}
    row = {"run_id": run_id, "phase": phase, "arm": arm, "question_id": question["question_id"],
           "model": MODEL, "prompt_hash": hashlib.sha256(prompt.encode()).hexdigest(),
           "model_answer": text.strip(), "gold_answer": golds[0],   # DB/capture row stays a string — schema and check_demo expect one
           "is_correct": is_correct,
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
    ap.add_argument("--phase", choices=["pre_prune", "post_prune", "autopilot_pre", "autopilot_post"],
                     required=True)   # autopilot_* are SCRATCH phases: check_demo never reads them and
                                      # they write their own captures/replay_autopilot_*.json files
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
