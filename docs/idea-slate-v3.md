# SVAI Hackathon — Slate v3 (verifier tweaks + Codex R1 fixes applied)

All 9 ideas revised per: three persona judges (v1→v2), adversarial verification judge (v2), and
Codex implementer review R1 (v2). Companion doc: plan-shared-contract.md (incl. binding Codex R1
amendments — replay-first, three cost tiers, agent-mode memory path, EverOS mutation semantics).
Demo default everywhere: REPLAY of a measured pre-show benchmark run + 1–2 scripted live calls.

---

## TRACK 1 — Cost of Intelligence

### T1-1 ⭐ "Broke" — the model router that gets cheaper the more you use it
WHAT: A routing API (documented non-streaming `/route` endpoint — NOT claimed as full
OpenAI-compatible) over Snowflake Cortex models. Task families: (1) JSON extraction with expected
values, (2) classification with gold labels, (3) structured summarization with required-fact
checklist — no code-exec tasks. Routing brain: EverOS agent-case memories of graded outcomes.
EXPLORATION STATE MACHINE (pinned): new fingerprint → frontier (claude-sonnet-5) + one SHADOW cheap
call (mistral-7b/haiku), both graded against gold; after 2 verified cheap passes for a fingerprint →
promote to cheap; on any cheap failure → escalate to frontier for that request, log the failure
case, 3-task cooldown before re-trial. ALL spend counts: shadow calls, retries, escalations.
Fingerprint = task family + semantic retrieval over agent cases (EverOS `recall_cases`, min_score
gate; no-match → treat as new).
METRIC (pinned): `1 − adaptive_estimated_credits / paired_frontier_estimated_credits`, both arms
measured via show_details on the same fixed-order task stream, logged to Snowflake with distinct
QUERY_TAGs.
DEMO: pre-show benchmark (~150 tasks, both arms) captured; on stage animate ~28 captured tasks —
cost-per-task curve bends down as cases accumulate ("measured pre-show run, replayed"); then ONE
live task routes down-market off a retrieved case, on screen, end-to-end. Closing: "identical
accuracy, N% cheaper — and cheaper tomorrow than today."
PHASE-0 GATE: agent-case add→flush→search round trip; fallback = fingerprinted user-mode memories
(`user_id="agent:broke"`), still EverOS retrieval. If both fail, swap to Déjà Vu (pre-decided).
WHY IT WINS: the only router in the room with a learning curve; EverOS agent-side memory used as
designed; honest measured % is the on-screen hero number.

### T1-2 "Déjà Vu" — the org-brain cache: repeat questions ~99% cheaper
WHAT: Org-wide semantic answer cache. EverOS holds memories under synthetic org identity
`user_id="org:acme"` (one session per policy topic); employee + department attribution lives in
Snowflake. Canonical answers + owners + `expires_at` (TTL) live in a Snowflake cache registry keyed
by EverOS session_id — EverOS does semantic matching (hybrid search, calibrated `min_score`),
Snowflake serves the canonical answer text.
CONFIDENCE GATE (pinned): retrieval must clear calibrated min_score AND a structured fail-closed
haiku verify call `{"answers_question": bool}` (malformed/timeout → miss). Metrics shown: hit rate,
served-hit precision, false positives (target 0), frontier calls avoided, NET savings after
verifier cost — headline is "~99.x% cheaper per hit", never "$0".
DEMO: 20 scripted questions from "5 employees" — hit-rate + saved-$ odometers climb (replay of
measured run); live beats: one cache hit, one NEAR-MISS ("parental leave" vs "sick leave" —
correctly falls through, the knowing laugh), one expired-TTL re-ask. Snowflake per-department
chargeback closes.
WHY IT WINS: safest build on the slate; every enterprise attendee has watched this money burn;
precision beat proves it's not a naive cache.

### T1-3 "Ghostwriter" — the context codec (cheaper AND remembers more)
WHAT (reframed per Codex): a context-construction harness under a DISCLOSED 8K-token application
prompt budget (stated on-slide: "every real product runs a context budget"). Naive arm: full
history, oldest-turns truncated to fit 8K. Ghostwriter arm: [system + top-k EverOS memories
(deduped, token-capped, recalled BEFORE storing current turn) + last 2 verbatim turns]. Same fixed
multi-session transcript (~50 turns, seeded/batched), same models, fixed intermediate assistant
messages so arms never diverge.
QUALITY (pinned): exact-answer FACT CHECKS at checkpoints (gold facts planted early in the
transcript: names, numbers, preferences) — objective, no LLM judge on critical path.
THE BEAT: mid-transcript, the naive arm's truncation FORGETS a planted fact (fails the check,
red X) while Ghostwriter recalls it from memory (green check) — at ~60-70% fewer prompt tokens per
turn (measured). "Cheaper AND it remembers more" — honest, no fake context crash.
DEMO: replay the measured run with a turn-by-turn diverging token meter + cumulative savings from
Snowflake; run the final checkpoint live (one call per arm).
WHY IT WINS: cleanest % proof in Track 1 after Broke; "memory is a compression codec" framing;
the forgotten-fact moment is emotionally legible to everyone.

## TRACK 2 — Value of Intelligence

### T2-1 ⭐ "Regulars" — the Cheers effect as a service
WHAT: Counter-top agent for small businesses that remembers every customer. Identity: phone-number
last-4 or name tap-in → `user_id`; every visit is a NEW `session_id` (provably cross-session).
First visit captures via quick structured form + chat: name, usual order, dietary note
(allergy = explicit CONFIRM toggle → written as profile `explicit_info` via `edit()` — never
inferred), one personal detail (chat, add+flush as episode). Return greeting: deterministically
rendered from retrieved profile fields (usual, allergy) + one generated flourish line from episode
recall — the reveal can't whiff.
ECONOMICS (pinned, honest): (a) measured — real Cortex cost per interaction × assumed 4 visits/mo
(≈ fractions of a cent; EverOS fees noted as sponsor-credited, excluded); (b) location-level margin
math vs a real comparable price point, cited on-slide (Fivestars/Thanx-class loyalty tools,
~$150–300/mo, which DON'T remember conversations); (c) 60-day cohort SIMULATION, seeded RNG,
disclosed on-slide, retention-lift assumption cited (Bain 5%→25-95%). Script says "simulated
cohort, real cost data" out loud.
DEMO: planted volunteer (rehearsed) "visits" the kiosk, orders, mentions marathon Sunday; 60s later
"returns next week" → "The usual oat-milk cortado? How'd the marathon go?" + GF-cookie upsell.
Memory panel shows the profile EverOS actually stored. Pre-seeded fallback persona standing by
(known EverOS silent-write-failure bug). Snowflake margin dashboard closes.
WHY IT WINS: vet's overall event pick (10/10 punch, 10/10 vote appeal); Codex's highest-confidence
build; audience participation is the strongest voting lever in the room; "what is a memory worth
in revenue" is the value-side token-economy story.

### T2-2 "Recall" — the tutor whose teaching cost falls as it knows you
WHAT: One narrow curriculum (chain rule, 4 authored questions with objective answers). Mastery rule
(pinned): 2 consecutive correct variants. Misconceptions stored as structured profile items;
resolution recorded ADDITIVELY (new "resolved" fact referencing the old item — no fragile item
edits unless the update path tests green in Phase 0). Scheduler = app-side table with frozen demo
dates (spaced-repetition intervals are app logic; EverOS is the memory of WHAT to review, the
scheduler decides WHEN).
ECONOMICS (pinned): lead the pitch with this, not "it's a tutor" — a PAIRED STATELESS BASELINE
(same session-2 questions with no memory: model must re-diagnose from scratch) vs the memory arm;
show a measured two-bar comparison of tokens-to-correct-outcome, not a fabricated 60% curve.
DEMO: session 1 (pre-seeded, disclosed as "yesterday") shows the misconception panel; live
session 2 opens with targeted review of exactly the missed concept, student answers, panel flips
to resolved; two-bar cost comparison closes. All state from EverOS, shown in the memory panel.
WHY IT WINS: highest VC score (parents pay $50+/hr today; $10 ARR trivial); deepest EverOS API
faithfulness (profile+episodes+additive facts) — sponsor-visible; the economics-first pitch
separates it from the room's other tutors.

### T2-3 "Loose Ends" — the follow-up agent that never drops a ball
WHAT: For founders/freelancers/salespeople. Pipeline (pinned, per Codex): at SEED time, Cortex
extracts obligations from a 14-thread fixture corpus into validated Snowflake rows
(obligation_id, prospect_id, owner, promise, due_at, status, deal_value, source_message_id,
source_quote); demo-day selection of overdue/due-today is a DETERMINISTIC SQL predicate over
frozen `DEMO_NOW`; receipts quoted from raw fixtures (never reconstructed from memory text);
EverOS (one consolidated session per prospect) supplies per-prospect history for personalized
DRAFTS (drafts only — explicit "not sent" state). Owed-by-us vs owed-by-them distinguished.
Cold-prospect resurrection: CUT.
METRIC (pinned): "seeded deal value at risk, surfaced & covered by prepared drafts" (never
"recovered") vs real token cost; comparable cited on-slide (Folk/Streak/Clay $20–60/seat/mo).
DEMO: chaotic week on screen → one click → three landmines surface with receipts ("you told Sarah
pricing by Friday — it's Friday") → three grounded drafts appear. Relief in 40 seconds. Zero live
input risk (all seeded).
WHY IT WINS: strongest pure B2B WTP in T2 (budget line that exists today); Codex's
"highest-confidence deterministic implementation"; completes the three-buyer spread (SMB owner /
parent / professional).

## TRACK 3 — Wildcard

### T3-1 ⭐ "Rent" — the memory P&L (context-margin ledger, prune on stage)
WHAT (reframed per Codex): every memory must pay for its seat in the context window. World: 12
one-session MEMORY BUNDLES (one asset = one seeded EverOS session; bundle registry in Snowflake
maps session_id → asset). Agent answers a fixed 8-question exact-answer eval; for each request BOTH
arms are EXECUTED in the pre-show benchmark (naive full-history arm and memory arm, same model) —
savings are measured from real paired runs, never tokenizer hypotheticals. Ledger (Snowflake):
per-bundle earnings = measured prompt-token savings of requests it served (even attribution across
retrieved bundles — convention disclosed on-slide), input tokens only; negative rows possible and
shown. Storage rent: DROPPED from math (not measurable) — "rent" survives as the metaphor: a
memory's seat in context must earn its tokens.
PRUNE MECHANIC (pinned to real API): application-level `active=false` flag in the bundle registry;
retrieval over-fetches then filters inactive bundles WITHOUT backfilling the slots; optional scoped
session soft-delete only after the logical prune succeeds. Never-retrieved bundles are labeled
"idle assets" (they cost nothing yet earn nothing — the freeloaders you'd audit), not counted as
inference savings.
DEMO: leaderboard fills from the measured run — "this bundle earned $X this week; these 4 never
earned a cent"; press PRUNE live (scoreboard-style dollar callout, per verifier) → the fixed
regression set re-runs (8 exact-answer questions, cheap+fast) → identical score, cost/query down —
claim worded exactly: "our fixed regression set retained an identical score at lower cost."
Dynamic numbers only — nothing hard-coded.
WHY IT WINS: still the thesis-productized play (CTO flagship, VC standout pick) — now with
mechanics that survive both a sharp judge AND the actual EverOS API; dual-prize shot (track +
UpScaleX bounty).

### T3-2 "Allowance" — a CFO for your agents (the wallet says no)
WHAT: Three agents, same 15-task queue (4 repeated categories, gold-label graded — shared harness
with Broke), each with an app-side wallet denominated in CENTS, sized from measured per-task costs
so the Naive agent (all-frontier) EXHAUSTS its wallet at ~task 11 of 15 — the "INSUFFICIENT FUNDS —
call blocked" freeze is honest (next call blocked, not fake mid-sentence cutoff, per Codex). Wallet
reserves each call's estimated max before dispatch; overdraft impossible. Cheapskate (all-cheap)
finishes rich but fails quality grades; Learner uses EverOS agent cases to spend where it matters —
finishes under budget with top correct-task count. Score (pinned): correct tasks completed before
exhaustion, then $ remaining. Per-agent QUERY_TAG → real per-agent chargeback from Snowflake
metering. Cortex Agents' native `budget:{tokens,seconds}` per-run cap: shown once as a sponsor
proof point, NOT critical path (it's per-run, not a cumulative wallet — stated honestly).
STRETCH (above cut line, skippable): "Inheritance" beat — a 4th agent starts fresh but shares the
Learner's agent_id, inherits its cases, and is cheap from task 1: "memory transfers; spend it once."
DEMO: replay of the measured race on a live scoreboard (three wallets draining, curve bending for
the Learner); Naive freezes mid-queue; ONE live Learner decision (retrieve case → route cheap →
grade pass) runs on stage. Ledger + chargeback close.
WHY IT WINS: best theater in Track 3 (vet 9/9), now with plausible arithmetic; "agent budgeting"
and "chargeback" are the track prompt's own words; enterprises need exactly this.

### T3-3 "Dividend" — pay for reasoning once, collect forever
WHAT: One expensive frontier deep-dive (claude-opus-class over a real artifact — a chunky OSS
codebase or 10-K-style doc; actual measured cost shown, whatever it is — no "$3" script) is FIRST
distilled into a validated structured analysis (finding_id, topic, claim, evidence,
source_location), THEN seeded into EverOS as granular findings. Follow-up questions: retrieval gate
(calibrated min_score) → cheap model answers from top-k findings; out-of-scope holdout questions
ESCALATE to a frontier re-read (or refuse) — the system knows what it doesn't know.
ECONOMICS (pinned, per Codex): capex = measured synthesis usage × rate; reuse_opex = verifier +
cheap-answer usage (all measured); dividend(n) = Σ paired-frontier-baseline − Σ reuse_opex − capex;
break-even marked where it ACTUALLY lands on the measured run. Extra honesty bar: a
"cheap-model + full saved analysis stuffed in context" baseline is also shown — proving EverOS
top-k retrieval beats ordinary file-caching on tokens (retrieval reads ~10% of the analysis per
question).
DEMO: the amortization curve draws itself from the measured run (finance-chart styling,
break-even flag); live: one in-scope question answered from memory for ~1/1000th the capex cost +
one holdout question correctly escalating. Closing: "intelligence as capex, not opex."
WHY IT WINS: "inference amortization" is the track prompt verbatim; lightest live footprint on the
slate (safest demo); the self-drawing curve is the best single chart of the day.

---

## Diversity check (unchanged)
T1: model selection / call elimination / context compression. T2: SMB owner / parent / professional.
T3: asset ROI accounting / budget governance / capex amortization.

## ⭐ Deep-plan picks & decision guide
- Audience-vote optimizer: **Regulars** (T2) — vet's event pick, Codex's highest-confidence build.
- UpScaleX/thesis optimizer: **Rent** (T3) — reframed to API-honest mechanics; if Codex R2 still
  ranks it lowest-confidence, the pre-agreed swap is **Dividend** as T3 ⭐.
- Cost-track: **Broke** (T1) — with pinned exploration policy + Phase-0 gate + pre-decided Déjà Vu swap.
