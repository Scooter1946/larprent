# SVAI "Token Economy in the AI Era" — Final Idea Portfolio

**Event:** one-day hackathon, ~5h build window (11:00–16:00), 3-min demos, audience voting decides
1st–3rd ($600/$500/$400), UpScaleX standout bounty ($200 + 1:1 with the fund). Teams of 1–2.
**Hard rules:** every project uses **EverOS** (EverMind's agent memory layer) load-bearing, and
**Snowflake** to build/operate/analyze the token economy. ~600 participants.

**How this portfolio was built:** deep research on the real EverOS + Snowflake Cortex APIs
(`docs/research-everos.md`, `docs/research-snowflake.md`) → 12 candidate ideas → three independent
judge reviews (hackathon veteran, seed-VC, skeptical CTO) → refinement → adversarial verification
judge → two rounds of review by **Codex itself as the implementer** (`docs/codex-review-r2.md`) →
settled. Final status: every idea below is conceptually BUILD-READY with all spec gaps pinned
(`docs/idea-slate-v3.md` + `docs/slate-v31-pins.md`).

**The strategic frame** (used everywhere): *memory IS a token-economy technology.* Retrieved
memories replace long context → fewer tokens → lower cost; memories personalize → higher
willingness-to-pay. Ideas where both sponsors are structurally load-bearing stand out from the
~300 predictable "chatbot with memory" and "spend dashboard" entries.

**Shared spine (all 9):** Python + local Streamlit; all LLM calls via Snowflake Cortex
`AI_COMPLETE(show_details=>TRUE)` (Claude/GPT/Llama/Mistral hosted natively — real measured token
counts, no external API keys); every call logged to Snowflake; EverOS Cloud SDK (one API key);
demos replay a *measured pre-show benchmark run* + 1–2 scripted live calls (deterministic, honest,
un-crashable); every on-screen number is measured or explicitly labeled as a disclosed assumption.

---

## Track 1 — Cost of Intelligence *(must show real % cost reduction live)*

### ⭐ 1. Broke — the model router that gets cheaper the more you use it
**What:** A routing API over Cortex models. New task types start on claude-sonnet-5 with a graded
cheap-model shadow call; after two verified cheap passes, the task type is promoted down-market
(gpt-5-mini); failures escalate and get remembered. The routing brain is EverOS **agent-case
memory** — the router literally learns from experience.
**The demo moment:** the cost-per-task curve *bends downward on screen* as memories accumulate,
then one live task routes cheap off a retrieved case. "Same measured score, N% cheaper — and
cheaper tomorrow than today."
**Why it wins:** every static router in the room shows a constant; Broke shows a *learning curve*.
EverOS agent-side memory used exactly as designed (sponsor-visible); the % metric is the on-screen
hero. All spend counted honestly (shadows, retries, escalations) against a same-tasks all-frontier
baseline.
**Feasibility:** replay-first (pre-show benchmark of ~150 graded tasks), one live call; graders are
gold-label/schema checks, no LLM opinions. Phase-0 gate on agent-case memory with a pre-decided
fallback. → Full plan: `plans/PLAN-broke.md`

### 2. Déjà Vu — the org-brain cache: repeat questions ~99% cheaper
**What:** Org-wide semantic answer cache. EverOS (org-scoped identity) semantically matches
paraphrased repeat questions; Snowflake holds canonical answers + TTL and serves them for the cost
of a haiku-tier verify call. Per-department chargeback dashboard.
**The demo moment:** hit-rate and $-saved odometers climb; then the deliberate NEAR-MISS —
"parental leave?" vs "sick leave?" correctly falls through to the model. The knowing laugh = the
precision proof.
**Why it wins:** the safest build on the slate (Codex: "easiest Track 1 idea"); every enterprise
attendee has watched this money burn; honest headline ("~99% cheaper per hit, net of verification")
survives any judge.
**Feasibility:** one loop, one confidence gate (min_score + structured fail-closed verifier), one
dashboard. The pre-decided fallback swap if Broke's Phase-0 gate fails.

### 3. Ghostwriter — the context codec (cheaper AND remembers more)
**What:** Two arms under a disclosed 8K-token prompt budget ("every real product runs a context
budget"). Naive arm: full history, oldest turns truncated. Ghostwriter: EverOS-retrieved memories +
last 2 turns. Same 50-turn multi-session transcript, same model, planted gold facts checked
objectively at checkpoints.
**The demo moment:** mid-transcript the naive arm's truncation *forgets a planted fact* (red X)
while Ghostwriter recalls it (green check) — at a measured ~2/3 fewer prompt tokens per turn.
"Cheaper AND it remembers more."
**Why it wins:** "memory is a compression codec" is the sharpest one-line thesis in Track 1; the
forgotten-fact beat is emotionally legible to non-engineers; measured, no fake context crash.
**Feasibility:** harness + replay of measured run; only the final checkpoint runs live (one call
per arm).

## Track 2 — Value of Intelligence *(must show willingness-to-pay)*

### ⭐ 1. Regulars — the Cheers effect as a service
**What:** A counter-top kiosk agent for cafes/barbers/gyms that remembers every customer: usual
order, confirmed allergy (safety-gated structured capture), last conversation, the marathon they
mentioned. Per-customer EverOS profiles + episodes, provably cross-session. Snowflake computes the
retention economics: measured cost-to-remember a customer (fractions of a cent/mo) vs a $49/mo
price vs $150–300/mo legacy loyalty platforms that remember nothing.
**The demo moment:** a (rehearsed) volunteer orders, mentions marathon Sunday; "returns next week"
60 seconds later → *"The usual oat-milk cortado? How'd the marathon go?"* + the GF-cookie upsell.
Memory panel shows exactly what EverOS stored.
**Why it wins:** the hackathon veteran's overall event pick (10/10 demo punch, 10/10 audience-vote
appeal) AND Codex's highest-confidence build. Audience participation is the strongest voting lever
in a room of 600. The value-side token-economy story: *what is a memory worth in revenue?*
(Retention cohort shown as a disclosed simulation; cost data fully measured.)
**Feasibility:** deterministic greeting rendered from retrieved profile (can't whiff), pre-seeded
fallback persona, replay-safe. → Full plan: `plans/PLAN-regulars.md`

### 2. Recall — the tutor whose teaching cost falls as it knows you
**What:** A tutor that stores misconceptions as structured EverOS profile facts and starts every
session exactly where the learner actually is (app-side spaced-repetition scheduler over
memory). The pitch leads with economics: a paired stateless baseline must re-diagnose the student
from scratch every session — Recall doesn't. Two-bar chart: measured tokens-to-mastery, memory vs
memoryless.
**The demo moment:** session 2 opens with "last time you mixed up the chain rule — quick check,"
the student passes two variants, and the misconception panel flips to *resolved* — live from EverOS.
**Why it wins:** highest VC score in the portfolio (parents pay $50+/hr for tutoring today — $10
ARR is trivial); the deepest EverOS API faithfulness on the slate (profile + episodes + additive
facts), which the on-site EverMind team will recognize; the economics-first pitch separates it from
the room's other tutors (education is in EverMind's own blurb — expect competitors).
**Feasibility:** one narrow curriculum (chain rule, 4 authored questions, objective mastery rule),
pre-seeded "yesterday" session, disclosed.

### 3. Loose Ends — the follow-up agent that never drops a ball
**What:** For founders/freelancers/salespeople: Cortex extracts every promise from a seeded
14-thread week into validated Snowflake rows (who owes what, to whom, by when, deal value, source
quote); deterministic SQL finds what's overdue *today*; EverOS per-prospect memory personalizes the
rescue drafts. Drafts only — nothing auto-sent.
**The demo moment:** one click → three landmines surface with receipts ("you told Sarah pricing by
Friday — it's Friday") → three context-grounded drafts appear. Relief, in 40 seconds.
**Why it wins:** the strongest pure B2B willingness-to-pay in Track 2 (a real budget line —
Folk/Streak/Clay run $20–60/seat/mo); Codex's "strongest deterministic implementation"; zero
live-input risk. Completes the track's three-buyer spread: SMB owner / parent / professional.
**Feasibility:** everything seeded and extracted at seed time; demo is a deterministic query + drafts.

## Track 3 — Wildcard *(AI-token economy, with conviction)*

### ⭐ 1. Rent — the memory P&L: every memory must pay for its seat
**What:** Treats each memory as a balance-sheet asset. A support agent for a fictional SaaS runs a
fixed eval; both arms (full-history vs memory-retrieval) are *actually executed* pre-show, so each
memory bundle's earnings = measured prompt-tokens it displaced × published rate (attribution
convention disclosed). The Snowflake ledger ranks memories by ROI; bundles that keep getting
retrieved but never help a correct answer are *not paying rent* — and get pruned **on stage**
(application-level demotion honest to the real EverOS API), with a fixed regression suite retaining
an identical score at visibly lower cost per query.
**The demo moment:** the leaderboard fills — "this memory earned $X this week; these four freeload."
PRUNE (scoreboard dollar callout) → regression suite animates green → cost/query drops. *"Context
is capital. We built the P&L for it."*
**Why it wins:** the skeptical-CTO judge's flagship (10/10 track fit: "the only idea exercising the
full EverOS API + real Snowflake analytics") and the VC's UpScaleX-standout pick — the event's
entire thesis, productized. After the API-honest reframe, Codex ranks it *safer than Broke* to
deliver. Dual-prize shot: track win + UpScaleX bounty.
**Feasibility:** 12 seeded bundles, 8 exact-answer questions, paired pre-show runs, replayed
regression + one live query. → Full plan: `plans/PLAN-rent.md`

### 2. Allowance — a CFO for your agents (the wallet says no)
**What:** Three agents, same task queue, app-side wallets in cents (sized from measured costs so
the math is honest). Naive (all-frontier) hits *INSUFFICIENT FUNDS — call blocked* mid-queue;
Cheapskate finishes rich but fails the quality grades; Learner uses EverOS agent-case memory to
spend where it matters and wins on correct-tasks-per-dollar. Real per-agent chargeback from
Snowflake metering via query tags.
**The demo moment:** three wallets draining on a live scoreboard; the Naive agent freezes
mid-queue. Stretch beat: a fresh agent *inherits* the Learner's memories and is cheap from task 1 —
"memory transfers; spend it once."
**Why it wins:** the best theater in Track 3 (vet: 9/10 punch, 9/10 vote), and "agent budgeting" +
"chargeback" are the track prompt's own words. Enterprises genuinely need this.
**Feasibility:** reuses Broke's routing state machine and task harness; race replayed from a
measured run + one live Learner decision.

### 3. Dividend — pay for reasoning once, collect forever
**What:** One expensive frontier deep-dive (over the *Snowflake 10-K* — public-domain and
on-theme) is distilled into structured findings and seeded into EverOS; follow-up questions are
answered by a cheap model reading top-k retrieved findings, at a tiny measured fraction of the
capex. Out-of-scope questions *escalate* honestly (the system knows what it doesn't know, and the
escalation spend is counted). Snowflake plots the amortization curve: capex, reuse opex, break-even
where it actually lands.
**The demo moment:** the amortization curve draws itself, finance-chart style, break-even flagged —
plus proof that EverOS retrieval beats naive file-caching on tokens. *"Intelligence as capex, not
opex."*
**Why it wins:** "inference amortization" is the track prompt verbatim; lightest live footprint on
the slate (the safest demo of the day); the single best chart of the event.
**Feasibility:** one pre-computed synthesis + seeded findings + replayed curve; 1 live in-scope
question.

---

## Which one to build? (decision guide)
| If you're optimizing for… | Pick | Why |
|---|---|---|
| **Audience voting** (decides 1st–3rd) | **Regulars** | Live audience participation + the reveal moment; vet's overall event pick; Codex's highest-confidence build |
| **UpScaleX bounty + judge/sponsor awe** | **Rent** | The event thesis productized; CTO+VC flagship; dual-prize shot |
| **Cost-track purity, engineering cred** | **Broke** | The learning curve nobody else will have; deepest honest measurement |
| **Lowest-risk fallback** (pre-agreed swaps) | **Déjà Vu** | Simplest build with a genuinely funny precision beat |

My overall recommendation: **Regulars** if you want the highest probability of a top-3 finish
(audience votes are the prize mechanism); **Rent** if you want the highest ceiling (standout bounty
+ the story a fund remembers). Both have full Codex-ready plans; you can decide the morning of.

## Repo map
- `plans/PLAN-broke.md`, `plans/PLAN-regulars.md`, `plans/PLAN-rent.md` — full implementation plans
  (Codex 5.6-executable from cold start; setup included; hour-by-hour schedule; demo scripts).
  **All three carry a final Codex dry-run verdict of EXECUTABLE — GO** (Regulars after 3 review
  rounds, Rent after 4, Broke after 7 — every blocker Codex found was fixed and re-verified).
- `docs/SHARED-CONTRACT.md` — engineering contract all plans share (setup, logging, replay rules,
  EverOS/Snowflake API facts, honesty rules).
- `docs/idea-slate-v3.md` + `docs/slate-v31-pins.md` — full settled specs for all 9 ideas (the
  6 non-starred ideas can be turned into full plans on request).
- `docs/research-everos.md`, `docs/research-snowflake.md` — API research briefs.
- `docs/codex-review-r2.md` — Codex's final implementer review.

## Day-of checklist (do these before 11:00)
1. Snowflake trial account + PAT created (5 min, `signup.snowflake.com`, AWS US region).
2. EverOS Cloud key from the EverMind booth (+ their credits).
3. Pick the idea; both builders open the plan; Lane A/B split per the plan.
4. Run Phase 0 + smoke test before writing any product code (~30 min, gates everything).
5. By 14:30: check the plan's cut line. By 15:20: run `benchmark.py` (pre-show measured run).
   By 15:40: full demo rehearsal in replay mode.
