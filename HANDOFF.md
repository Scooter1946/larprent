# HANDOFF — Rent (SVAI "Token Economy" hackathon)

You are picking up a **finished, verified project** to present. This file is your single entry
point; everything it references is in this repo. Read this fully, then `SCRIPT.md`, then rehearse.

## 1. What the product is (say it plainly)

**Rent tracks what an AI assistant's stored memories cost, and what they contribute.**
Memories get included in prompts; each inclusion costs tokens — that's the memory's **rent**
(tokenizer-estimated share of a measured prompt). When a memory is the *reason* an answer was
correct, it's credited the tokens it saved versus sending the full history — that's what it
**earned** (measured: both arms actually execute, token counts from the model API's usage object).
Memories that keep being included but never help get removed — and a fixed 8-question accuracy test
runs before and after every removal; the removal only counts if the score held and cost dropped.
An **autopilot** runs that find→verify→remove→re-verify loop unattended, with automatic rollback.

Verified headline (committed run `show1`, real EverOS memory + real gpt-4o-mini inference):
**8/8 → 8/8 identical score, 205.9 → 156.1 mean prompt tokens/query = −24.2%**, removed memories
exactly B09 & B10 (each included 2×, earned $0.0000). Deeper math Q&A: see the "Q&A cheat sheet"
at the bottom of `plans/PLAN-rent.md` and the rent/earnings explanation in §7 below.

## 2. Run it locally (10 minutes, zero accounts for replay)

```bash
git clone https://github.com/Scooter1946/larprent.git && cd larprent
python3 -m venv .venv && source .venv/bin/activate    # Python 3.12+
pip install -r requirements.txt
RENT_REPLAY_MODE=1 streamlit run app.py               # REPLAY: full demo, zero keys, zero network
```

Replay mode drives every screen from the committed `captures/*.json` — this alone is enough to
rehearse and even to present if everything else fails.

**Live mode** (the real thing): `cp .env.example .env`, fill `EVEROS_API_KEY` (shared key — get it
from your teammate over a private channel, never via git) and `OPENAI_API_KEY`; leave
`RENT_BACKEND=local` (SQLite). Then:
```bash
python smoke.py                      # gate: must be all green before anything else
python bootstrap.py && python bootstrap_rent.py   # one-time schema
python seed.py                       # 12 memories into EverOS + registry
python reset_prune.py --run-id show1 # pre-show capture sequence (~3 min, both benchmark arms)
python seed.py --restore-active      # stage the live PRUNE transition  ← NEVER SKIP
python seed.py --prefeed             # register the Initech fallback (guarded: must run AFTER captures)
python check_demo.py                 # final gate: must print "B09/B10 staged ACTIVE"
streamlit run app.py
```
Config matrix: `RENT_BACKEND=local|snowflake`, `RENT_LLM=mock|openai|cortex`. At the venue, if the
Snowflake trial works, run `RENT_BACKEND=snowflake` — real Cortex metering + the billed-credits
receipts panel (sponsor points). NOTE: the "organizers said Snowflake optional" claim should be
re-verified in the event Discord before relying on it.

## 3. The demo (your job)

- **`SCRIPT.md` is the word-for-word script**: slides 1–6 (~70s) → live app screens 2→3→4→5
  (~100s). ~410 words. Includes the pre-demo staging checklist and every fallback play.
- The app's five sidebar screens mirror the script in order: `1 · The P&L → 2 · Hire → 3 · Fire →
  4 · Proof → 5 · Autopilot`. Each screen shows a muted presenter cue (time window + opening line)
  and a plain-language explainer, so you can never lose your place.
- Demo inputs are pre-filled (the Initech fact + its question) — you click, never type, on stage.
- **After every rehearsal**: `python seed.py --restore-active && python check_demo.py` (rehearsing
  really prunes/feeds; this re-stages the world).
- Fallback hierarchy (all rehearsed states, see SCRIPT.md): network dies → flip Replay toggle;
  app dies → slides 7–10 carry the same beats; extraction stalls → pre-fed memory auto-appears.

## 4. The slide deck & submission link

`slides.html` — 10 scroll-snap sections, light print style, all real numbers. Open locally and
scroll; it's also the intro half of the live script.

**To submit a link** (you're the repo owner — 30 seconds): GitHub → `Scooter1946/larprent` →
Settings → Pages → Source: "Deploy from a branch" → Branch `main`, folder `/ (root)` → Save.
After ~1 minute the deck is live at:
**`https://scooter1946.github.io/larprent/slides.html`** — that's the submission link.
(A `slides.pdf` export also lives in the repo as a backup for forms that want a file upload.)
Optional crowd-pleaser: host the app read-only at share.streamlit.io (repo `Scooter1946/larprent`,
file `app.py`, secret `RENT_REPLAY_MODE="1"`) and put its QR on the closing slide.

## 5. Repo map

| Path | What it is |
|---|---|
| `app.py` | The Streamlit demo (5 screens, replay/live dual-mode) |
| `snow.py` / `mem.py` | ALL DB+LLM access / ALL EverOS access (the only integration points) |
| `bundles.py` | Retrieval: no-backfill seat freezing + client-side relevance gate + prune flags |
| `ledger.py` | The accounting: rent/earned/net attribution SQL, prune-candidate rule, calibration |
| `benchmark.py` | Paired-arm capture (naive vs memory, both really executed) |
| `seed.py` / `reset_prune.py` / `autopilot.py` / `check_demo.py` | Seeding / pre-show capture sequence / self-pruning loop / final gate |
| `captures/`, `fixtures/` | The measured show1 run (replay's data source) + the Acme world |
| `SCRIPT.md`, `slides.html`, `slides.pdf` | Your script, the deck, the deck's file backup |
| `plans/PLAN-rent.md` | Full build plan; **demo script + Q&A cheat sheet at the bottom** |
| `docs/` | Engineering contract, API research briefs, the full 9-idea portfolio |
| `KICKOFF.md`, `prompts/` | Team runbook; the agent task prompts that built this |

## 6. Hard-won platform facts (do not relearn these on stage)

1. EverOS extraction **declines single terse messages** — all writes go through a conversation
   wrapper with `async_mode=False` (`seed.wrap_conversation`). Console "Request Logs" page shows
   server-side extraction reasons if you need to debug at the venue.
2. EverOS's server-side `min_score` search param **returns empty sets** — the relevance gate is
   client-side and relative (`RENT_MIN_REL`, ≥0.75 × top score).
3. EverOS's vector/hybrid index **silently dropped embeddings** mid-run — retrieval uses
   `method="keyword"`; the data was never lost, only the index.
4. What EverOS stores is a **summary rewrite**, not your verbatim text (that's why the "memory
   born" panel is a demo moment — it shows what was actually distilled).
5. Removal ("prune") is an application-level `active=false` flag — EverOS has no per-memory
   delete. Seats stay empty (no backfill), it's reversible, and that reversibility is what makes
   the autopilot's auto-rollback safe.
6. The autopilot never touches live-fed memories (newborn grace period) and verifies both before
   AND after every prune, into isolated scratch phases.

## 7. If a judge pushes on the math

Rent = inclusion cost, charged whether or not it helps (tokenizer-estimated share, labeled).
Earned = called **and** the designated supporting evidence behind a **correctly graded** answer —
never just called. Amount = measured savings of that question (naive prompt tokens − memory prompt
tokens; both arms actually ran). Split evenly if several supporting memories were seated. The
support map is authored in the demo fixture (that's disclosed); in production it generalizes to
any outcome signal (evals, thumbs, task completion) + evidence marking. One line:
**"Costs are tracked live; credit requires evidence."** Full pre-answered Q&A: `plans/PLAN-rent.md`.

## 8. Hygiene before/after the event

- Rotate the EverOS + OpenAI keys after the event (both moved through chats). Grab the EverMind
  booth key at the venue (their credits) — drop-in env swap.
- The Snowflake trial (if used): created fresh, $400 credits, PAT auth — `.env` only, never git.
- `git pull --rebase` before you touch anything; commit+push after every change. Two sessions once
  re-solved the same bug because of a stale checkout. Don't be the third.
