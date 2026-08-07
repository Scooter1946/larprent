"""autopilot.py — the self-pruning audit loop (verify -> prune -> verify -> commit or ROLLBACK).

Makes the agent's context get cheaper by itself: watches cumulative usage (benchmark + live
retrieval rows), finds bundles that provably aren't paying rent, and prunes them — but NEVER
without an accuracy proof, and a failed proof rolls back automatically (demotion is a reversible
flag, which is exactly what makes unattended pruning safe).

  python autopilot.py --once                 one audit cycle now (what the app's button runs)
  python autopilot.py --interval 300         run forever, one cycle every 5 minutes
  python autopilot.py --once --run-id show1  explicit run id (default show1 / $RENT_RUN_ID)

Scratch phases: verification benchmarks run as phase autopilot_pre / autopilot_post — excluded from
check_demo.py, never touching show1's frozen pre/post captures. Audit trail appends to
captures/autopilot_log.jsonl ({ts, cycle, candidates, action, scores, mean tokens}) — the
"it ran by itself" evidence the app's AUTOPILOT panel renders.
"""
from dotenv import load_dotenv; load_dotenv()
import argparse
import json
import os
import subprocess
import sys
import time

import bundles
import ledger

LOG_PATH = "captures/autopilot_log.jsonl"


def _log(entry: dict) -> None:
    entry["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"autopilot: {entry}")


def _run_benchmark(phase: str, run_id: str) -> dict:
    """Run the regression eval into a scratch phase; return {score_naive, score_memory, mean_memory_tokens}."""
    subprocess.run([sys.executable, "benchmark.py", "--phase", phase, "--run-id", run_id], check=True)
    events = json.load(open(f"captures/replay_{phase}.json"))["events"]
    return {"naive": sum(e["naive"]["is_correct"] for e in events),
            "memory": sum(e["memory"]["is_correct"] for e in events),
            "mean_memory_tokens": sum(e["memory"]["prompt_tokens"] for e in events) / len(events)}


def _active_map() -> dict[str, bool]:
    return {v["bundle_id"]: v["active"] for v in bundles.get_session_to_bundle_map().values()}


def cycle(run_id: str, n: int) -> str:
    """One audit cycle. Returns the action taken: 'clean' | 'pruned' | 'rolled_back'."""
    active = _active_map()
    candidates = [b for b in ledger.get_prune_candidates_multi(run_id, ["pre_prune", "live"])
                  if active.get(b, False)]   # only bundles still active — idempotent across cycles
    if not candidates:
        _log({"cycle": n, "action": "clean", "candidates": []})
        return "clean"

    pre = _run_benchmark("autopilot_pre", run_id)
    bundles.apply_prune(candidates)
    post = _run_benchmark("autopilot_post", run_id)

    ok = (post["memory"] == pre["memory"] == 8 and post["naive"] == pre["naive"]
          and post["mean_memory_tokens"] < pre["mean_memory_tokens"])
    if ok:
        _log({"cycle": n, "action": "pruned", "candidates": candidates,
              "pre_score": pre["memory"], "post_score": post["memory"],
              "pre_mean_tokens": round(pre["mean_memory_tokens"], 1),
              "post_mean_tokens": round(post["mean_memory_tokens"], 1)})
        return "pruned"
    bundles.restore_bundles(candidates)   # targeted rollback — never reset_active_all here
    _log({"cycle": n, "action": "rolled_back", "candidates": candidates,
          "pre_score": pre["memory"], "post_score": post["memory"],
          "pre_mean_tokens": round(pre["mean_memory_tokens"], 1),
          "post_mean_tokens": round(post["mean_memory_tokens"], 1),
          "reason": "quality dropped or cost did not improve — restored"})
    return "rolled_back"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=int, default=None, help="seconds between cycles (loop mode)")
    ap.add_argument("--run-id", default=os.environ.get("RENT_RUN_ID", "show1"))
    args = ap.parse_args()
    if not args.once and args.interval is None:
        ap.error("pass --once or --interval N")
    n = 0
    while True:
        n += 1
        cycle(args.run_id, n)
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
