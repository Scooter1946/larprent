"""reset_prune.py — calibration + real prune + post-prune capture sequence (Lane A, Task 7).

Wraps the five pre-show capture/receipts steps in the exact order the demo needs (it does NOT
run the `seed.py --restore-active` staging step — do that separately, after this):

  1. benchmark.py --phase pre_prune  --run-id <id>   (registry: all 12 active)
  2. freeze prune candidates          -> captures/prune_candidates.json
  3. bundles.apply_prune(candidates)  (real live SQL, zero LLM calls)
  4. benchmark.py --phase post_prune --run-id <id>   (B09/B10 inactive; no-backfill shrinks context)
  5. benchmark.save_receipts_snapshot(<id>)          (~5 min lag — run last)

  python reset_prune.py --run-id show1     the pre-show capture sequence (Task 7)
  python reset_prune.py --restore          rehearsal-only full redo: reset_active_all() first, then the sequence

After this, run `python seed.py --restore-active` so the live PRUNE click has a real
active->inactive transition to perform. Never run `seed.py --reset` after the show1 capture —
it wipes eval_results/retrieval_log/rent_ledger.
"""
from dotenv import load_dotenv; load_dotenv()
import argparse, json, subprocess, sys

import bundles
import ledger
import benchmark


def _run_benchmark(phase: str, run_id: str) -> None:
    subprocess.run([sys.executable, "benchmark.py", "--phase", phase, "--run-id", run_id], check=True)


def capture_sequence(run_id: str) -> None:
    _run_benchmark("pre_prune", run_id)                                   # 1
    candidates = ledger.get_prune_candidates(run_id, "pre_prune")         # 2
    json.dump(candidates, open("captures/prune_candidates.json", "w"))
    print(f"prune candidates (frozen): {candidates}")
    bundles.apply_prune(candidates)                                       # 3
    _run_benchmark("post_prune", run_id)                                  # 4
    benchmark.save_receipts_snapshot(run_id)                             # 5
    print(f"reset_prune: capture sequence complete for run_id={run_id}. "
          f"Now run `python seed.py --restore-active` to stage the live PRUNE transition.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="show1")
    ap.add_argument("--restore", action="store_true",
                    help="rehearsal-only: reset_active_all() before rerunning both phases for a fresh show1")
    args = ap.parse_args()
    if args.restore:
        bundles.reset_active_all()   # rehearsal full redo: clear any leftover pruned state first
        capture_sequence("show1")
    else:
        capture_sequence(args.run_id)


if __name__ == "__main__":
    main()
