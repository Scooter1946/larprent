# Task — "Rent Autopilot": the self-pruning loop (Lane A or B, ~60-90 min)

Paste this file as a message to your coding agent (Claude Code), repo root, pulled `main`
(must include the lifecycle-beat commit if it has landed; otherwise base on fa3333c).

---

You are adding the AUTOPILOT to the Rent demo: a background auditor that makes the agent's context
get cheaper BY ITSELF while a user just prompts normally. The loop: watch live usage → periodically
re-verify against the fixed regression eval → auto-prune memories that provably aren't paying rent
→ verify → AUTO-ROLLBACK if quality dropped. The differentiator vs. naive cache eviction: it never
evicts without an accuracy proof, and failed proofs roll back automatically (demotion is reversible
— `active` flag only). Read `plans/PLAN-rent.md` and `docs/SHARED-CONTRACT.md` first; honesty rules
apply (every displayed number measured; the auto-prune log is the audit trail).

## Scope: NEW file `autopilot.py` + minimal hooks in `app.py` and `ledger.py`

1. **`autopilot.py`** — a runnable loop (`python autopilot.py --interval 60` and `--once` for a
   single cycle). Each cycle, using ONLY existing functions (`ledger.*`, `bundles.*`, benchmark via
   subprocess like reset_prune.py does):
   a. AUDIT: read cumulative retrieval stats for phase IN ('pre_prune','live') for the current
      run_id; compute candidates with the existing pinned rule (retrieved ≥2, never
      correct+supporting, NOT in fixture_support_map) — add
      `ledger.get_prune_candidates_multi(run_id, phases: list[str])` for this (same SQL, phase IN).
   b. If no new candidates: log "cycle clean" and sleep. If candidates:
   c. VERIFY-BEFORE: run the regression eval into a scratch phase
      (`benchmark.py --phase autopilot_pre --run-id <run_id>` — add 'autopilot_pre'/'autopilot_post'
      to benchmark's --phase choices; these phases are scratch: excluded from check_demo and never
      overwrite show1's pre/post captures — captures write to
      `captures/replay_autopilot_{pre,post}.json`).
   d. PRUNE: `bundles.apply_prune(candidates)`.
   e. VERIFY-AFTER: run `--phase autopilot_post`; compare: post score == pre score AND post mean
      memory prompt_tokens < pre. PASS → commit (leave pruned, append an AUDIT LOG line). FAIL →
      `bundles.reset_active_all()` on exactly the pruned ids (add
      `bundles.restore_bundles(bundle_ids)` — targeted, not all) and log ROLLBACK with the reason.
   f. AUDIT LOG: append JSON lines to `captures/autopilot_log.jsonl`
      ({ts, cycle, candidates, action: pruned|rolled_back|clean, pre_score, post_score,
      pre_mean_tokens, post_mean_tokens}) — this file is the "it ran by itself" evidence.

2. **`app.py` hook**: an "AUTOPILOT" panel (live mode): toggle that shows the last N lines of
   `captures/autopilot_log.jsonl` rendered as an activity feed ("02:14 — pruned B09,B10 — score
   8/8→8/8, cost/query −31%"), plus a "Run audit cycle now" button that invokes one `--once` cycle
   via subprocess (so the presenter can trigger it on stage without faking it). Replay mode: the
   panel renders from the committed log file — zero external calls, unchanged elsewhere.

3. **Safety rails (non-negotiable)**: autopilot NEVER touches bundle rows in fixture_support_map
   (already guaranteed by the candidate SQL's NOT EXISTS — do not weaken it); never runs during
   `--replay`; scratch phases never contaminate show1 (verify `python check_demo.py` still passes
   after a full cycle); rollback path gets a test (`--once` with a hand-inserted fake candidate that
   would break quality → must roll back).

## Demo integration (one line in the script)
After the manual PRUNE beat: "…and you don't even have to press the button — [toggle AUTOPILOT] —
this audit runs on a schedule: it found the same freeloaders, verified quality held, and pruned
them by itself. Your agent's context gets cheaper while you sleep."
Pitch framing for the 'too manual' judge question: rent meters automatically on every live prompt
TODAY; the eval is the safety gate, and in production it's replaced by your live outcome signals
(thumbs, task completion) on the same loop — the SDK story.

## Acceptance
- `python autopilot.py --once` on a seeded, benchmarked world: finds B09/B10, prunes, verifies,
  logs PASS; `check_demo.py` still green afterwards; `seed.py --restore-active` restages cleanly.
- Forced-failure test proves rollback works and logs it.
- App panel renders the feed in both modes; "Run audit cycle now" works live.
- `python3 -m py_compile autopilot.py app.py ledger.py bundles.py benchmark.py` clean.

Commit as `autopilot: self-pruning audit loop with verify + rollback`, push, reply DONE with a
5-line summary.

## ADDENDUM — Savings Odometer (build in the same pass; ~30 min)

The demo's centerpiece number: a big cumulative "SAVED THIS SESSION" ticker (tokens AND $) that
climbs with every live query. Honest math, two labeled sources, never conflated:
- Per live memory-arm query: saved_est = tokenize(build_naive_prompt(...)  via cl100k_base) −
  measured actual prompt_tokens. Label: "estimated vs full-context baseline (tokenizer)". Computed
  with ZERO extra LLM calls — build_naive_prompt is pure string assembly.
- The 8-question benchmark's measured savings (Σ naive−memory prompt tokens from the pre capture)
  shown as a separate static line: "eval set: N tokens saved — measured". Never summed into the
  estimated ticker.
- Odometer $ = tokens × pinned rate × $2.00/credit; count-up animation on change (reuse the
  keyframes from the lifecycle commit); after PRUNE the per-query delta widens — the presenter's
  line: "watch how much faster it climbs now that the freeloaders are gone."
- Replay mode: odometer renders the captured benchmark totals only (no live ticking), zero calls.
Acceptance: run 3 live queries → odometer climbs by the per-query estimates; PRUNE → next query's
delta visibly larger; labels exactly as specified; check_demo still green.
