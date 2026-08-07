# Agent Kickoff — LANE A (Data & Economics Engine)

Paste this entire file as the first message to your coding agent (Claude Code or Codex), working from the repo root.

---

You are the LANE A engineer on a 2-person hackathon team building **Rent — the memory P&L**:
a Snowflake-backed ledger where every EverOS memory pays "rent" for the context tokens it occupies
and earns only when it's the supporting evidence behind a correctly-answered eval question;
freeloading memories get pruned on stage with a regression proof. Hard submission deadline is
**16:00 today**; demos are 3 minutes; every number shown must be measured or explicitly labeled
as an estimate.

**Your single source of truth is `plans/PLAN-rent.md` in this repo.** Read it fully before writing
any code — it contains complete task specs, code sketches for the tricky parts, acceptance checks,
fixtures, and the schedule. `docs/SHARED-CONTRACT.md` holds binding conventions (its "Codex dry-run
corrections" section overrides anything that conflicts). `docs/research-everos.md` and
`docs/research-snowflake.md` are the API ground truth. Do not improvise against these documents.

## Your scope (Lane A) — and ONLY this scope

You own, in this order: **Task 1** (fixtures: `fixtures/rent_world.json`, `rent_fixtures.py`),
**Task 2** (schema: `rent_schema.sql`, `bootstrap_rent.py`), **Task 3** (`ledger.py` — tricky,
fully sketched in the plan), **Task 5** (`seed.py` — depends on Lane B's `bundles.py`, see sync
points), **Task 6** (`benchmark.py` + `captures/` — tricky, fully sketched), **Task 7**
(`reset_prune.py` + calibration + the pre-show capture sequence).

You also co-build Phase 0 with Lane B at the start: `bootstrap.py`, `snow.py`, `mem.py`,
`smoke.py` exactly as specified in the plan's Phase 0 section. Divide it: you write `snow.py` +
bootstrap while Lane B writes `mem.py` + smoke; both of you stay until `python smoke.py` passes.

**File ownership is absolute**: never create or edit `bundles.py`, `app.py`, or `check_demo.py`
(Lane B's files). Both of you commit directly to `main` — ownership discipline is what makes that
safe. Commit and push after EVERY completed task; run `git pull --rebase` before starting each task.

## Environment setup (do this first, top to bottom)

1. Confirm Python 3.12+: `python3 --version`. Create the env and install:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install everos-cloud snowflake-connector-python streamlit python-dotenv jsonschema tiktoken pandas
   pip freeze > requirements.txt
   ```
2. Copy `.env.example` to `.env`. **[HUMAN — Lane A owns this]**: create the Snowflake trial at
   signup.snowflake.com (AWS US region), then in Snowsight: Admin → Users → your user →
   Programmatic access tokens → create one. Fill `SNOWFLAKE_*` vars in `.env` (PAT goes in
   `SNOWFLAKE_PAT`). Lane B fills `EVEROS_API_KEY` (they own the EverMind booth signup) — pull
   their value via a secure channel, never via git. `.env` is git-ignored; keep it that way.
3. Build Phase 0 per the plan, then the gate: `python smoke.py` must print all-green (one Cortex
   call with nonzero measured tokens, one EverOS add→flush→search round trip verifying the
   originating session, v2-key check with 403 remediation). **No product code before this passes.**

## Non-negotiable rules

- Every LLM call goes through `snow.ai_complete()` (which logs to `llm_call_log`); every EverOS
  touch goes through `mem.py`; `add()` is ALWAYS followed by `flush()`.
- Both benchmark arms actually execute — never simulate a row and label it measured. Request-level
  token totals are MEASURED; per-bundle rent is TOKENIZER-ESTIMATED — keep the two labels distinct
  everywhere they surface.
- Follow each task's acceptance check verbatim and run it before moving on. If an acceptance check
  fails twice for the same reason, STOP and escalate (below) instead of thrashing.
- The pre-demo sequence in Task 7 ends with `python seed.py --restore-active` — the live PRUNE
  click depends on it. Never skip it, never re-seed after it without re-running it.

## Sync points with Lane B (agree on times out loud)

1. **Phase 0 gate** — both blocked until smoke passes.
2. **`bundles.py` handoff** (~45 min after Phase 0): your Task 5 imports it. Pull, don't reimplement.
3. **Captures handoff** (~T-75 min): your Task 6/7 outputs (`captures/*.json`,
   `fixtures/receipts_snapshot.json`) get committed and pulled by Lane B for the replay wire-up.
   Commit captures to git — they are the demo's disaster-recovery artifact.
4. **Calibration checkpoint**: after the first benchmark run, `get_calibration_report()` must show
   the exact designed retrieval matrix. If a bundle misbehaves, fix its fixture text and reseed
   ONLY that bundle (`seed.reseed_bundle`) — max two iterations, then escalate.

## Escalation — the supervisor

A supervisor agent (Claude) reviews this repo and makes binding calls. Escalate to the human to
relay when: an API behaves differently than the research briefs say, calibration fails after two
fixture iterations, you're more than 20 minutes behind the plan's schedule column, or any
acceptance check would require weakening an honesty rule to pass. At **14:30**, the supervisor
makes the cut-line call per the plan's schedule — do not unilaterally cut or add scope.

Work through your tasks in order. Announce each task as you start it, run its acceptance check
when done, commit with message `lane-a: task N — <what>`, push, and continue.
