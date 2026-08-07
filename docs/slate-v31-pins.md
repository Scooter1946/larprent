# v3.1 Settlement Pins — resolves every Codex R2 "NEEDS" gap

These pins are BINDING on all implementation plans. Together with idea-slate-v3.md and
plan-shared-contract.md, the slate is settled. (Codex R2: 4 BUILD-READY; 5 bounded gaps → resolved here.)

## Regulars (T2-1 ⭐)
- Profile placement: name, usual order, dietary note (allergy confirm-toggled), all as profile
  `explicit_info` categories (`name`, `usual_order`, `dietary`); personal details (marathon etc.) as
  episodes via add+flush. Missing fields: greeting omits them (template has optional slots).
- Memory panel shows: exact returned profile fields + the episode snippet used for the flourish + its
  originating session_id.
- Cohort simulation (all on-slide, "simulated" watermark): 200 customers, 60 days, seeded RNG(42).
  Weekly visit probability p = 0.30 baseline; memory arm: p = 0.30 + 0.03 (i.e. +10% relative lift,
  disclosed assumption with a sensitivity slider 5–20%); AOV $6.50; gross margin 70%.
  Transition: each week each customer visits with prob p; a "remembered" customer = ≥1 stored
  personalization fact. Bain citation used ONLY as profit-sensitivity context ("5% retention ↑ →
  25–95% profit ↑, Bain/HBR"), never as the lift assumption.
- Location margin math: 250 active customers × cost/customer/mo (measured Cortex × 4 visits) vs
  $49/mo price; comparable cited: Fivestars/Thanx-class loyalty platforms ~$150–300/mo (no memory).
- EverOS fees: excluded, labeled "sponsor-credited".

## Recall (T2-2)
- Misconception key: stable slug `mc:{concept}:{error_type}` (e.g. `mc:chain-rule:forgot-inner`).
  State = additive facts `{key, state: open|resolved, ts}`; reducer = newest-ts-wins per key,
  computed app-side after `get("profile")`.
- Resolution beat: TWO consecutive correct variants on stage (two short questions, ~20s — the pinned
  mastery rule, honored in the demo).
- Scheduler: app table `review_queue(concept_key, due_date)`; intervals frozen [1, 3] days;
  due predicate `due_date <= DEMO_NOW` (DEMO_NOW frozen, timezone America/Los_Angeles).
- Prompt assembly: [system + open-misconception profile facts (reduced) + retrieved episode top_k=5
  (min_score gated) + current question]. Query for recall = concept name + student id.
- Paired baseline: same 2 session-2 questions, stateless arm re-diagnoses from full seeded
  transcript; ALL calls counted both arms (incl. diagnosis); stopping rule: arms end when mastery
  rule met or 4 exchanges, whichever first. Two-bar chart = measured tokens-to-mastery per arm.
- Copy fixes: "all learner state from EverOS + app scheduler"; show measured %, no precommitted number.

## Rent (T3-1 ⭐)
- Fixture domain: a support/ops agent for a fictional SaaS ("Acme") — 12 bundles = 12 seeded
  sessions (product specs, pricing history, customer quirks, incident postmortems...). 8 eval
  questions with gold answers; a bundle→supporting-evidence map is authored in the fixture
  (`fixtures/rent_world.json`).
- Prompt serialization (both arms): system + [naive: full history chronological, 8K-capped |
  memory: top_k=6 retrieved bundle summaries, deduped, chronological, capped] + question; identical
  generation params; pinned model claude-haiku-4-5 (fallback gpt-5-mini).
- PRUNE RULE (pinned): candidates = bundles RETRIEVED ≥2 times in the benchmark whose bundle_id
  never appears in the supporting-evidence set of a correct answer (retrieved-but-non-supporting:
  they occupied context and earned nothing). Pruning them shrinks actual retrieved context on
  re-run (no backfill). IDLE assets (never retrieved) shown in a separate "idle" column, explicitly
  NOT linked to inference savings ("cost nothing, earn nothing — audit candidates").
- Post-prune regression: pre/post paired runs captured PRE-SHOW; on stage the suite result is
  REPLAYED (8 green checks animate from captured data) + ONE representative query runs live.
- Ledger $ labeled: "estimated $ = measured tokens × published rate"; earnings = input tokens only;
  gold answers normalized (case/whitespace/number-format) before match.

## Allowance (T3-2)
- Learner policy = EXACTLY Broke's state machine, imported as a shared module (`router_policy.py`);
  same THREE task families as Broke (copy fix: three, not four).
- Race contract frozen pre-benchmark: 15 tasks (5 per family, fixed order), models pinned
  (frontier claude-sonnet-5, cheap openai-gpt-5-mini; fallback per contract), max_tokens 300/task,
  temperature 0; parse failure = incorrect + full cost counted; reservation = est. max cost
  (max_tokens × rate), released to actual on completion.
- Wallet size formula: wallet_cents = ceil(1.15 × measured naive-arm cost of tasks 1–11) → Naive
  freezes at ~task 11–12 by construction (measured, honest, disclosed as "wallets sized to the
  measured cost of ~2/3 of the queue").
- Whole-race fallback: full replay of captured race; the one live Learner decision degrades to
  replay if Snowflake is unreachable.
- If agent-mode memory fails Phase 0: same fallback as Broke (fingerprinted user-mode memories).

## Dividend (T3-3)
- Artifact PINNED: Snowflake Inc. FY2025 Form 10-K (SEC filing — public domain, on-theme, judges
  smile). Synthesis model: claude-opus class if available in region, else claude-sonnet-5 (measured
  cost shown either way).
- Findings: canonical rows in Snowflake `findings(finding_id, topic, claim, evidence,
  source_location, session_id)`; seeded to EverOS one session per topic; retrieval maps back via
  session_id.
- Fixtures: 8 in-scope questions + 3 holdouts, gold answers + expected evidence finding_ids.
- Support gate: min_score calibrated on the fixture + fail-closed structured verifier
  `{supported: bool}` (malformed/timeout → escalate).
- Holdout behavior PINNED: ESCALATE to frontier re-read (never refuse); escalation spend COUNTED in
  reuse_opex. Live demo = 1 in-scope + the holdout REPLAYED (respects 2-live-call cap: in-scope
  answer = 2 calls incl. verifier; holdout shown from captured run).
- All ratios measured (context fraction per answer, cost multiples) — no "~10%"/"1/1000th" constants.

## Copy guards (all ideas)
- Percentages/dollars on stage are always the measured values from the pre-show benchmark run.
- "Identical accuracy" → "same measured score on our fixed benchmark/regression set."
- If a fallback path activates, its copy activates with it (no "agent-side memory as designed" if
  user-mode fallback is live).
