I completed the review, but could not save `codex-review-r2.md`: the workspace is read-only and rejected the write. The complete file contents follow.

# Codex Implementer Review — R2

## Executive judgment

The v3 reframes are materially better. The binding shared-contract amendments remove every cross-cutting R1 blocker. Four ideas are now build-ready; the other five need bounded clarifications, not another conceptual rewrite.

| Idea | Final verdict | Exact disposition |
|---|---|---|
| Broke | **BUILD-READY** | Core router, learning policy, grader, replay, and fallback are plan-able. |
| Déjà Vu | **BUILD-READY** | Cache authority, TTL, verification, and economics are pinned. |
| Ghostwriter | **BUILD-READY** | The disclosed 8K harness makes the proof credible and bounded. |
| Regulars | **NEEDS** | Pin cohort/location economics and correct the Bain-statistic interpretation. |
| Recall | **NEEDS** | Pin the additive-state reducer and paired benchmark/stopping rule. |
| Loose Ends | **BUILD-READY** | Deterministic Snowflake obligation handling removes the risky semantic deadline engine. |
| Rent | **NEEDS** | Pin a retrieved-bundle prune rule and replay the measured post-prune regression. |
| Allowance | **NEEDS** | Pin the learner policy and one frozen race contract. |
| Dividend | **NEEDS** | Choose the artifact and fallback, then pin the quality/economics fixture. |

A `PARTIALLY APPLIED` item is not automatically blocking. Exact fixtures, benchmark-calibrated thresholds, SQL field names, and symmetric generation parameters are normal implementation-plan work when there is an obvious safe default. `NEEDS` is reserved for a claim-shaping assumption, core policy, central input, or materially different fallback.

## Shared R1 amendments — all nine ideas

These are **APPLIED** through the binding `Codex R1 amendments` section:

- Exact tested `everos-cloud` 1.x pin plus v2-key smoke gate.
- `python-dotenv` and `load_dotenv()` in every entrypoint.
- Bootstrap without nonexistent database/schema, then reconnect.
- Full `ai_complete()` attribution signature and per-call `QUERY_TAG`.
- Separate measured tokens, estimated credits/dollars, and lagged billed credits.
- Real-run capture, zero-call replay, and one-or-two-call live garnish.
- Agent-mode add/flush/search plus user-mode fallback for Broke and Allowance.
- Correct EverOS mutation semantics: application `active` flag, no result backfill, optional scoped session soft-delete.
- Gold-based graders, fresh namespace discipline, and explicit allergy handling.

The exact EverOS patch version is correctly left for Phase 0 to test and then pin.

## T1-1 ⭐ Broke

### R1 fix check

| R1 required fix | Status | R2 finding |
|---|---|---|
| Constrain endpoint and remove unsafe/general claims | **APPLIED** | `/route` is non-streaming and expressly not OpenAI-compatible; code execution is cut. |
| Pin safe task families and objective graders | **APPLIED** | Three families use expected values, gold labels, and required-fact checks. |
| Define exploration, promotion, escalation, and cooldown | **APPLIED** | Frontier plus cheap shadow, two-pass promotion, same-request escalation, failure logging, and cooldown are explicit. |
| Define fingerprint, confidence gate, and no-match behavior | **PARTIALLY APPLIED** | Semantic retrieval, `min_score`, and no-match→new are set; make `task_family` a required request field and calibrate the numeric gate. |
| Add and prove agent-case memory with fallback | **APPLIED** | Phase 0 proves add→flush→search; user-mode EverOS memory and Déjà Vu are declared fallbacks. |
| Map cases to Snowflake outcomes | **PARTIALLY APPLIED** | Logs and session fields exist; the plan still needs the case payload and originating-session join. |
| Count every call and use paired economics | **APPLIED** | Shadows, retries, and escalations count; both arms use the same ordered stream. |
| Pin models and generation parameters | **PARTIALLY APPLIED** | Sonnet is fixed; `mistral-7b/haiku` must become one primary cheap model with deterministic caps. |
| Replace live benchmark with replay | **APPLIED** | Roughly 150 tasks are captured, about 28 animated, and one route runs live. |

### New v3 problem

No new architectural problem. Two copy guards remain:

- If user-mode fallback activates, remove “agent-side memory used as designed.”
- Say “same measured score” rather than unconditional “identical accuracy” unless the benchmark proves parity.

### Final verdict

**BUILD-READY.** Requiring `task_family` in the request and selecting one available cheap model do not change the product.

## T1-2 Déjà Vu

### R1 fix check

| R1 required fix | Status | R2 finding |
|---|---|---|
| Fix org sharing and employee attribution | **APPLIED** | `user_id="org:acme"` scopes shared memory; employee/department identity stays in Snowflake. |
| Keep canonical answers, owners, and TTL in Snowflake | **APPLIED** | The registry is authoritative and keyed by EverOS session. |
| Calibrate retrieval and near-miss behavior | **PARTIALLY APPLIED** | Hybrid search and calibration are required; pin `top_k`, labeled cases, and the resulting threshold. |
| Add a structured fail-closed verifier | **APPLIED** | Malformed output and timeout are misses. |
| Decide whether misses populate the cache | **MISSED** | Use the safe default: no demo-time admission. |
| Pin gold labels and metrics | **PARTIALLY APPLIED** | Metrics are complete; add `policy_id`/null labels to the fixture. |
| Log cache decisions that make no answer call | **PARTIALLY APPLIED** | Add a minimal query event with candidate session, score, expiry, verifier result, and served-hit status. |
| Remove `$0` and count verifier cost | **APPLIED** | Net savings and non-zero hit cost are explicit. |
| Replay the bulk demo | **APPLIED through contract** | The binding replay rule controls where v3 calls several beats “live.” |

### New v3 problems

- `~99.x%` is unknown before measurement; display measured `N%`.
- A hit, near-miss, and expired re-ask can exceed two live calls. Replay at least two beats.

### Final verdict

**BUILD-READY.** The binding replay rules and safe no-admission default make the plan deterministic.

## T1-3 Ghostwriter

### R1 fix check

| R1 required fix | Status | R2 finding |
|---|---|---|
| Replace fake provider exhaustion with a disclosed app budget | **APPLIED** | Both arms use an explicit 8K application budget. |
| Make this a harness rather than a protocol proxy | **APPLIED** | The compatibility/base-URL claim is gone. |
| Bound retrieval, dedupe, and recall before storage | **APPLIED** | Prompt recipe and ordering are explicit. |
| Keep arms comparable | **APPLIED** | Same model and fixed intermediate assistant messages prevent divergence. |
| Define model, serialization, `top_k`, and cap values | **PARTIALLY APPLIED** | These are symmetric plan pins; define “last two turns” as two complete user/assistant exchanges. |
| Use objective quality checks | **APPLIED** | Planted facts and exact-answer checkpoints remove the LLM judge. |
| Seed a feasible transcript and identify the live checkpoint | **APPLIED** | Roughly 50 turns are replayed; only the final two-arm checkpoint is live. |
| Avoid unmeasured failed-call token claims | **APPLIED** | The naive arm truncates rather than crashing. |

### New v3 problem

No structural problem. Treat `60–70%` as a target and display the measured percentage. Label “cheaper” as Cortex prompt-token/estimated-credit savings, excluding unmeasured EverOS fees.

### Final verdict

**BUILD-READY.**

## T2-1 ⭐ Regulars

### R1 fix check

| R1 required fix | Status | R2 finding |
|---|---|---|
| Prove cross-session identity | **APPLIED** | Same customer `user_id`, new visit `session_id`. |
| Constrain first-visit capture | **APPLIED** | Name, usual order, dietary note, and personal detail are fixed. |
| Handle allergies safely | **APPLIED** | Explicit confirmation and profile `edit()` are mandatory. |
| Separate profile facts from episodes | **PARTIALLY APPLIED** | Allergy and personal detail are mapped; name/usual/non-allergy dietary fields also need explicit profile placement. |
| Make the reveal deterministic and provide fallback | **APPLIED** | Critical fields are rendered; only the flourish is generated; a seeded fallback exists. |
| Define missing-field behavior and memory panel | **PARTIALLY APPLIED** | Omit missing values and show exact returned profile fields plus episode source. |
| Pin the cohort simulation | **PARTIALLY APPLIED** | Duration, RNG, disclosure, and citation intent exist; cohort size, transition equation, baseline rate, lift, AOV, and gross margin do not. |
| State the cost boundary | **APPLIED** | Cortex cost × four visits is measured; EverOS fees are excluded. |
| Compare at location level | **PARTIALLY APPLIED** | Comparable range exists, but traffic/AOV/margin assumptions and formula remain open. |

### New v3 problem

“Bain 5%→25–95%” is mislabeled as a retention-lift assumption. The familiar claim is that a 5% increase in retention can correspond to a 25–95% increase in profits; it does not supply a 25–95% retention lift.

### Final verdict

**NEEDS — pin the seeded cohort/location equations and assumptions, using Bain only as a profit-sensitivity citation rather than a retention transition.**

## T2-2 Recall

### R1 fix check

| R1 required fix | Status | R2 finding |
|---|---|---|
| Narrow curriculum and grade objectively | **APPLIED** | Chain rule, four authored questions, objective answers, and two-pass mastery are pinned. |
| Make misconception resolution API-safe | **PARTIALLY APPLIED** | Additive resolution is correct; define a stable misconception key and newest-state-wins reducer. |
| Keep scheduling in the app | **PARTIALLY APPLIED** | App-side table and frozen dates are set; interval values and due predicate remain. |
| Define prompt assembly and targeted recall | **PARTIALLY APPLIED** | The missed concept drives review, but the query/context recipe is absent. |
| Replace fabricated curve with paired economics | **PARTIALLY APPLIED** | The two-bar baseline is correct; counted calls, stopping rule, and failed-baseline handling are undefined. |
| Remove unsupported 60% claim | **APPLIED** | No fixed curve remains. |
| Disclose pre-seeding and use replay | **APPLIED** | “Yesterday” is disclosed and the capture contract applies. |

### New v3 problems

- “All state from EverOS” contradicts the app-side scheduler; say “all learner state.”
- The title precommits that cost falls before the benchmark proves it.
- The demo says one answer resolves the panel, while mastery requires two consecutive correct variants.

### Final verdict

**NEEDS — define the additive-state reducer and paired stopping rule, require two passes in the resolution beat, and align the cost/state copy with measured mechanics.**

## T2-3 Loose Ends

### R1 fix check

| R1 required fix | Status | R2 finding |
|---|---|---|
| Normalize fixtures and extract at seed time | **PARTIALLY APPLIED** | Corpus and obligation schema are set; pin raw-message fields and abort malformed extraction. |
| Freeze time and select deterministically | **PARTIALLY APPLIED** | `DEMO_NOW` and SQL selection are set; add timezone and completed/boundary predicates. |
| Distinguish owed-by-us from owed-by-them | **PARTIALLY APPLIED** | Make `obligor` or `direction` explicit rather than overloading `owner`. |
| Consolidate EverOS scope and limit its role | **APPLIED** | One session per prospect; Snowflake controls selection. |
| Preserve receipt provenance | **APPLIED** | Quotes come from raw fixtures. |
| Keep outputs as drafts | **APPLIED** | “Not sent” is explicit. |
| Use an honest KPI | **APPLIED** | “Surfaced and covered,” never “recovered.” |
| Cut cold resurrection | **APPLIED** | Removed. |
| Replay the demo | **APPLIED through contract** | Seeded inputs and captured model work bound the live path. |

### New v3 problem

None. Remaining partials are fixture and SQL definitions with obvious conservative implementations.

### Final verdict

**BUILD-READY.**

## T3-1 ⭐ Rent

### R1 fix check

| R1 required fix | Status | R2 finding |
|---|---|---|
| Reframe to a bounded context-margin ledger | **APPLIED** | Twelve bundles and eight exact-answer questions match the R1 simplification. |
| Define the asset abstraction | **APPLIED** | One registry asset is one seeded EverOS session bundle. |
| Pin domain, gold fixture, and support map | **PARTIALLY APPLIED** | Counts and grading type are fixed; domain, questions/golds, and bundle→answer map are not. |
| Pin naive and memory prompt serialization | **MISSED** | Ordering, dedupe, result serialization, and caps are absent. |
| Execute paired same-model counterfactuals | **APPLIED** | Both arms actually run pre-show. |
| Define ledger, negatives, and cost boundary | **APPLIED** | Attribution is disclosed, input-only savings are used, negatives are visible, and storage rent is dropped. |
| Use API-honest logical demotion | **APPLIED** | `active=false`, no backfill, and optional session soft-delete match the API. |
| Define prune eligibility | **PARTIALLY APPLIED** | The mechanism is pinned; qualifying retrieved bundles are not. |
| Use exact before/after regression and honest claim | **PARTIALLY APPLIED** | Suite and wording are correct; gold normalization and replay treatment remain. |
| Keep headline values dynamic | **APPLIED** | Explicit. |

### New v3 problems

- The demo links four never-retrieved idle assets to lower post-prune inference cost. Pruning idle assets cannot lower inference cost; prune retrieved, non-supporting context contributors.
- Eight live post-click calls conflict with the binding two-call limit. Capture pre/post runs and replay the eight results; optionally run one representative query live.
- The ledger earns input tokens while the demo says `$X`. Dollar conversion is estimated tokens × pinned rate and must be labeled accordingly.

### Final verdict

**NEEDS — pin a retrieved/non-supporting-bundle prune rule plus exact bundle/prompt fixture mapping, and replay the measured post-prune suite.**

## T3-2 Allowance

### R1 fix check

| R1 required fix | Status | R2 finding |
|---|---|---|
| Correct native Cortex budget claim | **APPLIED** | Native tokens/seconds are accurately per-run and non-critical. |
| Use a direct, app-budgeted replay race | **APPLIED** | Fifteen tasks, app wallets, replay, and one live decision are set. |
| Pin task bank, schemas, golds, and parse failures | **PARTIALLY APPLIED** | Size/repetition/grading are set; exact fixtures, schemas, and failure behavior are not. |
| Pin primary score | **APPLIED** | Correct tasks before exhaustion, then money remaining. |
| Define learner routing policy | **MISSED** | “Uses cases to spend where it matters” is not executable; shared harness does not clearly import Broke’s state machine. |
| Define case representation and scope | **PARTIALLY APPLIED** | Agent IDs and fallback exist; trajectory/fingerprint mapping remains. |
| Make wallet arithmetic plausible | **PARTIALLY APPLIED** | Cents, reservation, and next-call block are correct; models, caps, wallet formula, reserve release, and whole-race fallback are not fixed. |
| Add per-agent chargeback | **APPLIED** | Distinct query tags are explicit. |
| Keep native Agents optional | **APPLIED** | Correctly above the cut line. |

### New v3 problems

- Allowance says four categories in a harness shared with Broke, but Broke defines three families.
- “Learner finishes under budget with top correct-task count” is a benchmark gate, not guaranteed copy. Freeze the bank and wallet formula before running it.

### Final verdict

**NEEDS — explicitly reuse or replace Broke’s learner state machine and pin one frozen four-category race contract: fixtures, models/caps, parse behavior, wallet formula, and whole-run fallback.**

## T3-3 Dividend

### R1 fix check

| R1 required fix | Status | R2 finding |
|---|---|---|
| Choose exact artifact, size, domain, and license | **MISSED** | “OSS codebase or 10-K-style doc” leaves the central input undecided. |
| Generate validated findings before seeding | **APPLIED** | All required fields are present. |
| Pin finding identity, scope, flush, and mapping | **PARTIALLY APPLIED** | Granular seeding/top-k are set; canonical storage and session mapping are not. |
| Calibrate support gate | **PARTIALLY APPLIED** | `min_score` is required, but labeled threshold cases and fail-closed verifier behavior are absent. |
| Pin in-scope and holdout fixtures | **MISSED** | No counts, gold answers, or evidence expectations are defined. |
| Choose escalation or refusal | **MISSED** | “Re-read (or refuse)” leaves materially different paths. |
| Correct economics | **PARTIALLY APPLIED** | Formula is right for in-scope reuse, but frontier escalation must be counted or excluded explicitly. |
| Show actual break-even | **APPLIED** | Dynamic measured capex and break-even are explicit. |
| Disclose EverOS fee exclusion | **MISSED** | Add explicit exclusion unless sponsor metering exists. |
| Prove value beyond file caching | **APPLIED** | The full-analysis cheap-model baseline is present. |
| Keep live work bounded | **PARTIALLY APPLIED** | Verifier+answer+frontier holdout can exceed two calls; replay the holdout or combine support and answer. |

### New v3 problems

- `~10%` of the analysis and `~1/1000th` of capex are unearned constants; display measured ratios.
- A holdout frontier re-read is reuse opex if included in the economics.

### Final verdict

**NEEDS — select one licensed artifact and one holdout behavior, pin the finding/gate/quality fixture, count escalation spend, and derive both ratios from measurement.**

## A. Track 3 star

Keep Rent starred. The v3 reframe removes the blockers that made it my R1 lowest-confidence pick: no unsupported per-memory delete, tokenizer-only counterfactual, imaginary storage rent, 400-asset seed, or general “zero quality loss” claim. Its remaining work is local and deterministic: choose retrieved non-supporting prune candidates, serialize the fixed fixture, and replay captured pre/post results. Dividend still lacks its central artifact, evidence fixture, fallback behavior, and escalation accounting; preparing three comparison paths creates more content work before UI polish. In four coding hours, Rent is now safer than Broke and Dividend.

**T3 STAR: Rent**

## B. Starred-pick delivery confidence after v3

1. **Regulars** — one user-memory round trip, deterministic reveal, and pre-seeded fallback. Its economics correction is specification work, not demo-engine risk.
2. **Rent** — bounded 12-bundle/eight-question benchmark with API-honest demotion; remaining fixes are local fixture/replay decisions.
3. **Broke** — still the heaviest: agent-case extraction, three graders, routing state, API surface, and roughly 150-task paired benchmark.

Rent is no longer the lowest-confidence starred build, so the pre-agreed Dividend swap condition is not met.