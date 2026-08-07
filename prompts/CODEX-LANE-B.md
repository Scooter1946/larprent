# Agent Kickoff — LANE B (Retrieval, UI & Demo)

Paste this entire file as the first message to your coding agent (Claude Code or Codex), working from the repo root.

---

You are the LANE B engineer on a 2-person hackathon team building **Rent — the memory P&L**:
a Snowflake-backed ledger where every EverOS memory pays "rent" for the context tokens it occupies
and earns only when it's the supporting evidence behind a correctly-answered eval question;
freeloading memories get pruned on stage with a regression proof. Hard submission deadline is
**16:00 today**; demos are 3 minutes; every number shown must be measured or explicitly labeled
as an estimate. Your lane owns the thing the audience actually sees — treat the UI and the demo
script as the product.

**Your single source of truth is `plans/PLAN-rent.md` in this repo.** Read it fully before writing
any code — complete task specs, code sketches, acceptance checks, fixtures, demo script, schedule.
`docs/SHARED-CONTRACT.md` holds binding conventions (its "Codex dry-run corrections" section
overrides anything that conflicts). `docs/research-everos.md` / `docs/research-snowflake.md` are
API ground truth. Do not improvise against these documents.

## Your scope (Lane B) — and ONLY this scope

You own: **Task 4** (`bundles.py` — the TRUE no-backfill retrieval + prune primitives; tricky,
fully sketched; build this FIRST after Phase 0, it unblocks Lane A's seeding), **Task 8**
(`app.py` leaderboard UI — skeleton against mock data immediately, wire to real queries when
`ledger.py` lands), **Task 9** (PRUNE button, replay suite, one live query, and the whole-app
`--replay` mode — `compute_local_ledger` can be built against a hand-written mock capture long
before real captures exist), **Task 10** (`check_demo.py`).

You also co-build Phase 0 with Lane A at the start: you write `mem.py` + `smoke.py` while they
write `snow.py` + bootstrap; both of you stay until `python smoke.py` passes.

**File ownership is absolute**: never create or edit `rent_fixtures.py`, `rent_schema.sql`,
`bootstrap_rent.py`, `ledger.py`, `seed.py`, `benchmark.py`, or `reset_prune.py` (Lane A's files).
Both of you commit directly to `main` — ownership discipline is what makes that safe. Commit and
push after EVERY completed task; `git pull --rebase` before starting each task.

## Environment setup (do this first, top to bottom)

1. Clone the repo (URL from your teammate), confirm Python 3.12+, then:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install everos-cloud snowflake-connector-python streamlit python-dotenv jsonschema tiktoken pandas
   ```
2. Copy `.env.example` to `.env`. **[HUMAN — Lane B owns this]**: get the EverOS Cloud API key —
   at the event, from the EverMind booth (grab their credits too); otherwise sign up at
   everos.evermind.ai. Put it in `EVEROS_API_KEY`. Lane A owns the Snowflake trial + PAT — get
   their `SNOWFLAKE_*` values via a secure channel (both machines share ONE Snowflake account and
   ONE EverOS key), never via git. `.env` stays git-ignored.
3. Phase 0 per the plan; the gate is `python smoke.py` all-green on BOTH machines. **No product
   code before this passes.**

## Non-negotiable rules

- All EverOS access through `mem.py` (`add()` ALWAYS followed by `flush()`); anything rendering
  costs uses the three labels exactly: "measured tokens", "estimated $ (tokens × published rate)",
  "billed credits (Snowflake receipts, ~5 min lag)". Per-bundle rent is TOKENIZER-ESTIMATED and
  its UI copy says so.
- The no-backfill invariant is the product's integrity: freeze the first top-k bundle ranks BEFORE
  applying the active filter; a pruned seat stays EMPTY. The plan includes a deterministic test
  proving rank 7 never fills a pruned seat — it must pass before Task 8 consumes `bundles.py`.
- `--replay` mode makes ZERO external calls (leaderboard, candidates, regression, receipts panel,
  and PRUNE all driven from `captures/*.json` + `fixtures/receipts_snapshot.json`). It is both the
  outage fallback and the rehearsal mode; live mode and replay mode must render identically.
- Follow each task's acceptance check verbatim. Same failure twice → STOP and escalate.

## Sync points with Lane A (agree on times out loud)

1. **Phase 0 gate** — both blocked until smoke passes.
2. **`bundles.py` handoff** (~45 min after Phase 0): commit + push the moment its test passes;
   Lane A's `seed.py` is waiting on it.
3. **`ledger.py` lands** (~90 min in): pull it and swap Task 8's mock queries for real ones.
4. **Captures handoff** (~T-75 min): pull `captures/*.json` + `fixtures/receipts_snapshot.json`
   and do Task 9's final wire pass; verify live mode AND replay mode both render, then run
   `check_demo.py`.
5. **Rehearsal** (T-20): drive the demo start-to-finish in `--replay`, then once in live mode.
   The demo script (word-for-word, with staging beats) is in the plan — rehearse against it.

## Escalation — the supervisor

A supervisor agent (Claude) reviews this repo and makes binding calls. Escalate via your teammate
when: an API contradicts the research briefs, the no-backfill test won't pass, you're 20+ minutes
behind schedule, or a check would require weakening an honesty rule. At **14:30** the supervisor
makes the cut-line call per the plan — do not unilaterally cut or add scope. (The plan's cut order
protects: PRUNE + replay first, receipts panel and live query are the sacrifices, never the
regression proof.)

Work through your tasks in order. Announce each task as you start it, run its acceptance check
when done, commit with message `lane-b: task N — <what>`, push, and continue.
