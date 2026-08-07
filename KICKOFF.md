# Team Kickoff — Rent (SVAI "Token Economy" hackathon)

**Project:** Rent — the memory P&L. Every EverOS memory pays rent for its context seat; earns only
when it's the evidence behind a correct answer; freeloaders get pruned on stage with a regression
proof. Targets Track 3 (Wildcard, primary) + Track 1's cost-reduction proof in the same demo.
UpScaleX-bounty play. Full pitch script: bottom of `plans/PLAN-rent.md`.

## Who does what

| | Lane A — Data & Economics | Lane B — Retrieval, UI & Demo |
|---|---|---|
| Codex prompt | `prompts/CODEX-LANE-A.md` | `prompts/CODEX-LANE-B.md` |
| Owns | fixtures, schema, `ledger.py`, `seed.py`, `benchmark.py`, calibration/prune | `bundles.py`, `app.py` (leaderboard + PRUNE + replay), `check_demo.py` |
| Account job | Snowflake trial + PAT | EverOS key (EverMind booth — grab credits) |
| Human role | "The numbers are real" — benchmark, ledger, receipts, calibration calls | "The demo lands" — UI polish, replay parity, rehearsal, presents |

Supervisor: Claude (this repo's session) — reviews diffs at sync points, makes binding calls on
calibration, cut line (14:30), and any honesty-rule question. Escalate through Lane A's machine.

## Before the event (tonight if possible)

1. Lane A: create the GitHub remote and push (from repo root):
   `gh repo create snowflake2026-rent --private --source=. --push`
   Add Lane B as a collaborator; Lane B clones.
2. Both: run environment setup steps 1–2 from your lane's prompt (venv + deps; Snowflake trial can
   be created tonight — 30-day window; EverOS key at the booth tomorrow for credits).
3. Both: read `plans/PLAN-rent.md` end to end once. Fifteen minutes now saves an hour tomorrow.

## Day-of timeline (compressed 4-hour build; full detail in the plan's schedule table)

| When | What |
|---|---|
| T+0:00 | Phase 0 together: `.env` filled, `snow.py`/`mem.py`/`smoke.py` — **gate: smoke green on both machines** |
| T+0:40 | Lanes split. A: fixtures→schema→ledger. B: `bundles.py` FIRST (A is waiting), then UI skeleton on mock data |
| T+1:25 | Sync: `bundles.py` handoff → A runs `seed.py`; B starts leaderboard for real |
| T+2:45 | A: benchmark both arms → calibration report matches the designed matrix (supervisor reviews) |
| T+3:15 | A: prune → post-capture → receipts snapshot → **`seed.py --restore-active`** (never skip). Captures committed |
| T-0:45 | B: final wire pass to real captures; `check_demo.py` green; supervisor reviews the freeze |
| T-0:20 | Rehearse twice: once `--replay`, once live. Freeze. Submit with buffer |

**14:30 cut-line rule:** supervisor decides. Cut order: live query first, receipts panel second.
Never cut: the PRUNE beat, the replay suite, the regression proof.

## Git rules (what makes two-people-on-main safe)

- Absolute file ownership per lane — the lanes share zero files after Phase 0.
- Commit + push after every task (`lane-a: task N — ...`); `git pull --rebase` before each task.
- Commit `captures/` and `fixtures/receipts_snapshot.json` when produced — they're the
  disaster-recovery artifacts; if a laptop dies, the other machine can run the whole demo in
  `--replay` mode.
- `.env` never enters git. Keys move over a secure channel only.

## The three failure modes we've pre-planned (don't improvise new fixes)

1. **Calibration miss** (a decoy isn't retrieved / an idle bundle is): edit that bundle's fixture
   text, `seed.reseed_bundle`, re-run. Two attempts max, then supervisor.
2. **EverOS flakes live** (known silent-write bug): the demo runs entirely in `--replay` mode —
   identical screens, zero external calls. Rehearse it first for exactly this reason.
3. **Behind schedule at 14:30**: supervisor applies the cut order above. The demo still lands with
   just leaderboard + PRUNE + regression replay.
