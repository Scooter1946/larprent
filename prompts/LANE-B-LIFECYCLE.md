# Lane B Task — "Watch a Memory Get Hired" (lifecycle beat) + demo-motion polish

Paste this entire file as a message to your coding agent (Claude Code), from the repo root, on a
pulled `main` (must include commit 7d01c87 — the supervisor review fixes).

---

You are extending the Rent demo app (`app.py`) with a LIVE MEMORY LIFECYCLE beat: the presenter
feeds the agent one new fact on stage, the audience watches EverOS extract and store it as a new
memory, then a query retrieves it and its first rent charge appears on the leaderboard — proving
"every memory starts life in the red and must earn its seat." Read `plans/PLAN-rent.md` (Tasks 8/9
context) and `docs/SHARED-CONTRACT.md` first. Honesty rules and replay-mode integrity are
non-negotiable.

## Scope (edit ONLY: app.py, ledger.py, seed.py — the specific functions named below)

1. **Feed box (app.py, Leaderboard screen, live mode only)**: a text input "Feed the agent a fact"
   + button. On submit:
   - `session_id = f"live-fed-{uuid4().hex[:6]}"`; `mem.remember(session_id, [{"sender_id": USER_ID,
     "role": "user", "content": <input>}])`.
   - VERIFY-LOOP (mirror seed.py's pattern): poll `mem.recall(<input>, user_id=USER_ID, top_k=12)`
     until an episode with this session_id appears, max ~10s. On timeout show a calm warning
     ("extraction queued — using this morning's pre-fed memory") and fall back to the PRE-FED
     fallback memory (see §4). Never crash, never block the app.
   - Upsert a registry row via a new `seed.upsert_live_bundle(session_id, title)` helper:
     bundle_id auto-assigned `B13`, `B14`, ... (next free), `category='live_memory'`,
     `is_idle=FALSE`, `active=TRUE`.
   - Display the EXTRACTED episode text (from the recall result's `content`) in a highlighted
     "memory born" panel — what EverOS distilled, not what was typed.

2. **Live rent rows (app.py `run_query` + ledger)**: when a live query runs, ALSO call
   `ledger.insert_retrieval_log(RUN_ID, "live", <question_id or "freeform">, hits, bundle_tokens)`
   so the retrieval is a real Snowflake row. Live rows are RENT-ONLY (no earnings — freeform facts
   have no graded outcome yet; that asymmetry is the on-stage line, not a bug). Add to ledger.py a
   small `get_live_rent(run_id)` (sum bundle_tokens × rate per bundle for phase='live') and have
   live-mode `load_view` overlay those rent charges onto the leaderboard rows (visually: the row's
   rent/net updates and flashes; a `+$0.000X rent` delta chip next to the affected bundles).
   CRITICAL ISOLATION: phase='live' rows must never contaminate show1's pre/post captures,
   `get_prune_candidates` (which already filters phase='pre_prune'), or `check_demo.py` — verify
   check_demo still passes after a live feed+query.

3. **Freeform query**: extend the query control with a free-text option (in addition to the
   selectbox). Freeform live answers display with retrieval context + measured tokens as today;
   if retrieval returns nothing above the gate, render the honest miss: "no memory pays rent on
   that — I don't know." (That line demonstrates the score gate working — it's a feature.)

4. **Pre-fed fallback**: add to `seed.py` a `--prefeed` mode that feeds one known fact
   ("Initech signed 2026-08-01; we promised them a 99.99% uptime SLA") through the same path and
   registers it. Run it during pre-show prep so the demo NEVER depends on live extraction: if the
   on-stage feed stalls, the presenter pivots to the pre-fed memory with the fallback line.

5. **Motion polish (same commit, cheap wins only)**: number count-up on the two cost tiles after
   PRUNE (simple JS in the HTML tiles or st_autorefresh stepping), a brief row flash/highlight when
   a rent delta lands, and the PRUNE state flip animating badge color. No new dependencies beyond
   what a `st.markdown` HTML/CSS/JS block can do. Do NOT restyle the app wholesale — the Rent
   Terminal Dark palette stays.

6. **Fire-buttons (audience picks the victim, ~10 lines)**: in the "Not paying rent" red panel,
   render a small `FIRE B09` / `FIRE B10` button on each candidate row (in BOTH modes) alongside the
   existing all-at-once PRUNE. A fire-button prunes ONLY that bundle (live: `bundles.apply_prune([bid])`;
   replay: add the bid to a `st.session_state["pruned_ids"]` set that compute_local_ledger's
   pruned_ids union with the frozen file). Both candidates are support-map-guarded decoys, so any
   audience choice is safe — the presenter asks the room which one dies first. The all-PRUNE button
   stays as the "fire the rest" follow-up. Cost tiles logic unchanged (they still compare the frozen
   pre/post captures).

7. **OPTIONAL — build ONLY if 1–6 are green with time to spare: live earnings for scripted
   questions (~15 lines)**: when a live query matches one of the 8 eval questions (selectbox path,
   or freeform text that equals one), grade it against its gold alternates (reuse benchmark's
   normalize-in-set check) and, on a correct answer, also write the earnings side into the
   phase='live' slice (same even-split-across-supporting rule). The leaderboard then shows a memory
   EARNING live on stage — the Q&A killer when a judge asks a scripted question themselves.
   Freeform non-eval questions stay rent-only (no gold → no earnings → that's the worldview, not a gap).

## Demo-script placement (update the two lines in plans/PLAN-rent.md's demo script if needed)
The beat runs ~1:00–1:30: feed → "memory born" panel → freeform query answers from it → its first
rent chip appears → "every memory starts life in the red — it has to earn its seat. These two never
did." → PRUNE beat as scripted.

## Acceptance (run all before pushing)
- Live: feed → extracted text appears ≤10s → query retrieves the new bundle → leaderboard shows its
  rent-only row/chip. Timeout path renders the fallback line (test by feeding with wifi off).
- `python seed.py --prefeed` registers the Initech memory; querying it works.
- `python check_demo.py` STILL PASSES after a feed + 2 live queries (phase isolation proven).
- Replay mode: completely unaffected — no feed box rendered, all screens identical to before.
- `python3 -m py_compile app.py ledger.py seed.py` clean.

Commit as `lane-b: lifecycle beat — live memory birth + rent overlay + motion polish`, push, and
reply DONE with a 5-line summary. Escalate to the supervisor (via teammate) if EverOS extraction
latency makes the 10s verify-loop unrealistic — do not silently raise the timeout past 15s.
