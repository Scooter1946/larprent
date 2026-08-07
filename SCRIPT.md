# Presentation script

## ⚡ CURRENT FORMAT: 1 minute, slides only (rules changed day-of)

Judges look only at the deck. The deck reads standalone; if you get to speak, this is the 60-second
track over the 5 slides (~140 words — slow is fine, the slides carry the content):

**Slide 1 (What it is) — 0:00**
> "We built Rent. It tracks what an AI assistant's memories cost — and whether they're worth it."

**Slide 2 (How it works) — 0:10**
> "Every memory included in a prompt is charged rent: the tokens it takes up. When a memory is the
> reason an answer came out right, it's credited what it saved. Both sides are measured."

**Slide 3 (The ledger) — 0:25**
> "That gives every memory a balance. Eight of ours earned. Two kept being included and never
> helped. Two were never used at all."

**Slide 4 (Remove + result) — 0:38**
> "We removed the two that never helped. Same eight-question test before and after: identical
> scores, twenty-four percent cheaper — and the savings show up exactly on the questions those
> memories had been included in."

**Slide 5 (Runs itself) — 0:52**
> "An autopilot runs this loop on a schedule, and rolls back automatically if accuracy drops.
> That's Rent — thanks."

Fallbacks: none needed — the deck is offline, self-contained, keyboard-driven (Space/arrows).
If judges browse it without you, it reads standalone by design. The live app remains available at
the repo (replay mode, zero keys) as the "see it running" link.

---

# ARCHIVE — previous format: slides + live demo (3:00 total)

Spoken words: ~410. Rehearse at a conversational pace; you should finish with ~10s spare.
Plain language throughout — say the sentences as written, no ad-libbed jokes.

## Before you start (staging checklist — do this every time, takes 2 minutes)
1. `python seed.py --restore-active && python check_demo.py` → must print "B09/B10 staged ACTIVE".
2. `streamlit run app.py` open on screen "1 · The P&L", replay toggle OFF (or ON if the network is
   suspect — every beat below works identically).
3. `slides.html` open in a second tab/window, scrolled to the top.
4. Screenshare the browser. Slides tab first.

---

## Part 1 — Slides, tab one (0:00 – 1:10)

**Slide 1 (Title) — 0:00**
> "Hi, we're Rent. We track what an AI assistant's memories cost — and what they're worth."

**Slide 2 (Problem) — 0:10**
> "Every memory an assistant stores gets included in prompts, over and over. Each inclusion costs
> tokens. Nobody measures whether any given memory ever actually helps. So memory stores only grow,
> and every prompt quietly gets more expensive."

**Slides 3–5 (Born / Retrieved / Graded) — 0:30 — scroll steadily through all three while speaking**
> "Here's the pipeline. A fact becomes a stored memory. When a question comes in, a few memories are
> included in the prompt — each one is charged **rent**: the tokens it takes up. Then the answer is
> checked. If a memory was the reason the answer was right, it's credited what it **earned**: the
> tokens it saved versus sending the entire history."

**Slide 6 (The ledger) — 0:55 — pause here, point at the rows**
> "That gives every memory a balance. These three pay for themselves. These two at the bottom have
> been included twice each and have never helped — they only cost money."

*(Stop scrolling. Slides 7–10 are not used live — they're your fallback, see below.)*

## Part 2 — Live demo, app tab (1:10 – 2:50)

**Switch tabs → app screen "2 · Hire" — 1:10**
> "This is the live system. I'll give it one new fact."
*Click **Feed the agent** (the fact is pre-filled). Wait for the "memory born" panel (~5s).*
> "The memory layer — EverOS — extracted and stored that. Note it starts at zero earned."
*Click **Run query** (pre-filled question).*
> "Asked about it, the assistant retrieves the new memory, answers from it — and there's its first
> rent charge."

**Screen "3 · Fire" — 1:40**
> "Back to the two memories that never help. In the chat: which one should go first?"
*Click the FIRE button the audience names, then PRUNE for the other.*
> "Removed. That's a reversible flag — from now on they're simply never included in a prompt again,
> so every future prompt is smaller."

**Screen "4 · Proof" — 2:05**
> "Did answers get worse? Same eight-question test, before and after."
*The suite renders — point at the two columns.*
> "Eight out of eight, both times. Cost per question went from 206 tokens to 156 — twenty-four
> percent less, measured, not estimated."
*Click **Run query** for one scripted question.*
> "And that's it answering live against the smaller memory right now."

**Screen "5 · Autopilot" — 2:35**
> "You don't have to do any of this by hand. This log line is the system running the whole loop
> itself earlier today — find the useless memories, verify, remove, verify again. If accuracy had
> dropped, it would have restored them automatically."

**Close — 2:50, stay on screen 5**
> "Costs are tracked live. Credit requires evidence. Everything you saw is measured, and the whole
> thing runs on EverOS for memory, a SQL ledger for the accounting, and any model you like.
> We're Rent. Thank you."

---

## Fallbacks (rehearse each once)
- **Network dies mid-demo**: flip the sidebar **Replay mode** toggle and continue — identical
  screens, zero external calls. Say nothing about it; the flow doesn't change.
- **App won't render at all**: stay in the slides tab — slides 7–10 (Removal / Result / Autopilot /
  Close) cover the same beats with the same real numbers. The script lines above still work almost
  verbatim.
- **Feed/extraction stalls past ~10s on Hire**: the app shows the pre-fed Initech memory
  automatically. Line: "extraction's queued — here's one we fed it this morning," then continue with
  the pre-filled query unchanged.
- **A judge interrupts with a question**: answer from the Q&A cheat sheet (bottom of
  `plans/PLAN-rent.md`) — the six hardest questions are pre-answered there.

## Numbers you may be asked to repeat (all measured, from the committed show1 run)
- 205.9 → 156.1 mean prompt tokens per query after removal = **24.2% less**, score 8/8 → 8/8.
- Naive full-history baseline: ~1,182 tokens per query; with memory retrieval: ~206 → ~156.
- The two removed memories: B09 and B10, each included twice, earned $0.0000.
- Model: gpt-4o-mini (swap to Snowflake Cortex at the venue if running `RENT_BACKEND=snowflake`).
