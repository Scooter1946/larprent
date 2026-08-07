"""app.py — Rent Terminal Dark: leaderboard, PRUNE, regression replay, one live query, whole-app
--replay mode (Tasks 8 + 9, Lane B).

Dual-mode by design: live mode reads Snowflake via ledger.py; REPLAY_MODE reads only captured JSON +
the local fixture (compute_local_ledger), makes ZERO external calls, and renders through the SAME UI
code — only the data-fetch call site (load_view) branches on REPLAY_MODE, never the rendering.

Two honesty tiers, never conflated (footer + Q&A cheat sheet): request-level naive/memory prompt
tokens (and $ earned) are MEASURED from AI_COMPLETE show_details; the per-bundle rent allocation
($ rent, $ net) is TOKENIZER-ESTIMATED (cl100k_base via tiktoken).

Deliberate, disclosed deviations from the plan sketch:
  * Headline + cost tiles are rendered as themed HTML tiles rather than raw st.metric, to guarantee
    the amber/green/red color and "largest font on screen" the plan requires (st.metric value color
    is not reliably themeable across Streamlit versions). The numbers and labels are exactly as
    specified.
  * PRUNE + the before/after cost tiles live on the Leaderboard screen so the ACTIVE->PRUNED badge
    flip happens ON SCREEN as the demo script's 1:20 beat requires; the second screen holds the
    regression replay + the one live/replayed query.
"""
from dotenv import load_dotenv; load_dotenv()

import json
import os
import subprocess
import sys
import time
from uuid import uuid4

import streamlit as st

import bundles
import ledger
import mem      # lifecycle beat: live feed box (remember + verify-loop)
import seed     # lifecycle beat: upsert_live_bundle + pre-fed fallback constants
import snow     # footer: active backend/LLM disclosure
from rent_fixtures import load_world, normalize
from benchmark import MODEL, GEN_PARAMS, USER_ID, ENC, SYSTEM_PROMPT, build_naive_prompt  # reused, not duplicated
from snow import ai_complete, get_conn, MODEL_RATES, USD_PER_CREDIT, rate_for

# --------------------------------------------------------------------------------------------------
# Constants / paths
# --------------------------------------------------------------------------------------------------
RUN_ID = os.environ.get("RENT_RUN_ID", "show1")
PRE_CAPTURE = "captures/replay_pre_prune.json"
POST_CAPTURE = "captures/replay_post_prune.json"
PRUNE_CANDIDATES_PATH = "captures/prune_candidates.json"
RECEIPTS_SNAPSHOT_PATH = "fixtures/receipts_snapshot.json"

# Rent Terminal Dark palette (PLAN Task 8 table)
BG, PANEL, BORDER = "#0B0F14", "#11161D", "#1F2937"
TEXT, MUTED = "#E6EDF3", "#6B7280"
GREEN, RED, AMBER = "#00D26A", "#FF4D4F", "#FFB000"
MONO = '"JetBrains Mono", "IBM Plex Mono", ui-monospace, monospace'

st.set_page_config(page_title="Rent — the memory P&L", layout="wide")

st.markdown(f"""<style>
  .stApp {{ background: {BG}; color: {TEXT}; font-family: {MONO}; }}
  section[data-testid="stSidebar"] {{ background: {PANEL}; }}
  html, body, [class*="css"] {{ font-family: {MONO}; }}
  .rent-panel {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px;
                 padding: 14px 18px; margin: 8px 0; }}
  .rent-red {{ border: 1px solid {RED}; box-shadow: 0 0 0 1px {RED} inset; }}
  .rent-tile-label {{ color: {MUTED}; font-size: 0.8rem; letter-spacing: .08em; text-transform: uppercase; }}
  .rent-headline {{ color: {AMBER}; font-size: 3.4rem; font-weight: 700; line-height: 1.05; }}
  .rent-tile-val {{ font-size: 2.2rem; font-weight: 700; }}
  table.rent {{ width: 100%; border-collapse: collapse; font-family: {MONO}; font-size: 0.95rem; }}
  table.rent th {{ color: {MUTED}; text-align: right; padding: 6px 10px; border-bottom: 1px solid {BORDER};
                   font-weight: 500; text-transform: uppercase; font-size: 0.72rem; letter-spacing: .06em; }}
  table.rent th.l, table.rent td.l {{ text-align: left; }}
  table.rent td {{ text-align: right; padding: 6px 10px; border-bottom: 1px solid {BORDER}; }}
  .badge {{ padding: 1px 8px; border-radius: 999px; font-size: 0.72rem; font-weight: 700; }}
  .badge-active {{ color: {GREEN}; border: 1px solid {GREEN}; }}
  .badge-pruned {{ color: {RED}; border: 1px solid {RED}; }}
  .rent-foot {{ color: {MUTED}; font-size: 0.78rem; line-height: 1.5; }}
  /* Motion polish (lifecycle beat §5) — CSS-only, no new deps. st.markdown does not execute <script>,
     so a JS numeric tween is not reliable here; these keyframes give the count-up "pop", the rent-delta
     row flash, and the PRUNE badge-color flip as pure CSS animations. */
  .rent-chip {{ color: {AMBER}; border: 1px solid {AMBER}; border-radius: 999px; padding: 0 6px;
                font-size: 0.7rem; margin-left: 6px; }}
  .rent-chip-green {{ color: {GREEN}; border: 1px solid {GREEN}; border-radius: 999px; padding: 0 6px;
                      font-size: 0.7rem; margin-left: 6px; }}
  @keyframes rentflash {{ 0% {{ background: rgba(255,176,0,.30); }} 100% {{ background: transparent; }} }}
  tr.rent-flash td {{ animation: rentflash 1.4s ease-out; }}
  @keyframes countpop {{ 0% {{ transform: scale(.82); opacity: .15; }}
                         60% {{ transform: scale(1.06); }} 100% {{ transform: scale(1); opacity: 1; }} }}
  .rent-countpop {{ display: inline-block; animation: countpop .6s ease-out; }}
  @keyframes badgeflip {{ 0% {{ box-shadow: 0 0 0 2px {RED} inset; opacity: .35; }}
                          100% {{ box-shadow: none; opacity: 1; }} }}
  .badge-pruned {{ animation: badgeflip .8s ease-out; }}
</style>""", unsafe_allow_html=True)


def money(x, dp: int = 4) -> str:
    return f"${x:,.{dp}f}"


# --------------------------------------------------------------------------------------------------
# Task 9 pure functions — zero-network replay compute (driven only by captured JSON + local fixture)
# --------------------------------------------------------------------------------------------------
def load_agg(path: str) -> dict:
    """Zero-network aggregate from a capture file — no separate stored 'aggregates' section needed."""
    data = json.load(open(path))
    events = data["events"]
    mean_tokens = sum(e["memory"]["prompt_tokens"] for e in events) / len(events)
    rate = rate_for(data["model"])
    return {"mean_memory_prompt_tokens": mean_tokens,
            "mean_memory_cost_per_query": mean_tokens / 1e6 * rate * USD_PER_CREDIT}


def load_receipts_snapshot() -> list[dict]:
    """REPLAY_MODE's receipts panel reads this instead of querying ACCOUNT_USAGE — zero Snowflake."""
    return json.load(open(RECEIPTS_SNAPSHOT_PATH))


def compute_local_ledger(pre_path: str, post_path: str, world: dict, use_post: bool = False,
                         extra_pruned=None) -> dict:
    """Pure-Python reimplementation of ledger.ATTRIBUTION_SQL + get_prune_candidates/get_idle_bundles,
    driven ONLY by captured JSON + the local fixture file. Returns the SAME LEADERBOARD ROW SCHEMA as
    ledger.get_leaderboard() so app.py never branches on REPLAY_MODE, only the call site does.
    `extra_pruned` (a set of bundle_ids) is unioned into pruned_ids — used by replay-mode fire-buttons
    so the audience can prune a single candidate on top of the frozen Task-7 decision."""
    data = json.load(open(post_path if use_post else pre_path))
    events = data["events"]
    rate = rate_for(data["model"])
    support = {q["question_id"]: set(q["supporting_bundle_ids"]) for q in world["questions"]}
    per_bundle = {b["bundle_id"]: {"title": b["title"], "category": b["category"], "is_idle": b["is_idle"],
                                   "total_earned": 0.0, "total_rent": 0.0, "times_retrieved": 0}
                  for b in world["bundles"]}
    candidate_hits = {b["bundle_id"]: 0 for b in world["bundles"]}
    correct_supporting = {b["bundle_id"]: 0 for b in world["bundles"]}
    for e in events:
        qid, mem_row = e["question_id"], e["memory"]
        saved = e["naive"]["prompt_tokens"] - mem_row["prompt_tokens"]
        ctx_ids = mem_row["context_bundle_ids"]
        supporting_here = [b for b in ctx_ids if b in support[qid]]
        for bid in ctx_ids:
            tok = mem_row.get("bundle_token_map", {}).get(bid, mem_row["prompt_tokens"] // max(len(ctx_ids), 1))
            rent = tok / 1e6 * rate * USD_PER_CREDIT   # tokenizer-estimated per-bundle share, see Task 3
            per_bundle[bid]["total_rent"] += rent
            per_bundle[bid]["times_retrieved"] += 1
            candidate_hits[bid] += 1
            if bid in support[qid] and mem_row["is_correct"] and supporting_here:
                per_bundle[bid]["total_earned"] += saved / len(supporting_here) / 1e6 * rate * USD_PER_CREDIT
                correct_supporting[bid] += 1
    # Candidates/idle are PRE-PRUNE concepts and pruned state is the frozen Task-7 decision — never
    # derive either from the post capture: pruned bundles are absent from post-capture retrieval and
    # would masquerade as "idle but active" (the exact bug this replaces).
    if use_post:
        pre_events = json.load(open(pre_path))["events"]
        candidate_hits = {b["bundle_id"]: 0 for b in world["bundles"]}
        correct_supporting = {b["bundle_id"]: 0 for b in world["bundles"]}
        for e in pre_events:
            qid, mem_row = e["question_id"], e["memory"]
            sup_here = [b for b in mem_row["context_bundle_ids"] if b in support[qid]]
            for bid in mem_row["context_bundle_ids"]:
                candidate_hits[bid] += 1
                if bid in support[qid] and mem_row["is_correct"] and sup_here:
                    correct_supporting[bid] += 1
        pruned_ids = set(json.load(open(PRUNE_CANDIDATES_PATH)))  # frozen in Task 7
    else:
        pruned_ids = set()   # pre-prune view: everything active
    if extra_pruned:
        pruned_ids = pruned_ids | set(extra_pruned)   # replay fire-buttons: audience-picked victims
    all_supporting_ids = {bid for s in support.values() for bid in s}
    candidates = sorted(bid for bid, n in candidate_hits.items()
                        if n >= 2 and correct_supporting[bid] == 0 and bid not in all_supporting_ids)
    idle = sorted(bid for bid, n in candidate_hits.items() if n == 0)
    leaderboard = sorted(({"bundle_id": bid, **v, "total_net": v["total_earned"] - v["total_rent"],
                           "active": bid not in pruned_ids}
                          for bid, v in per_bundle.items()), key=lambda r: -r["total_net"])
    return {"leaderboard": leaderboard, "candidates": candidates, "idle": idle}


# --------------------------------------------------------------------------------------------------
# Data-fetch call site — the ONE place that branches on REPLAY_MODE. Returns the normalized triple
# (leaderboard rows, candidate bundle_ids, idle bundle_ids) identically in both modes.
# --------------------------------------------------------------------------------------------------
def load_view(replay_mode: bool, pruned: bool):
    world = load_world()
    if replay_mode:
        res = compute_local_ledger(PRE_CAPTURE, POST_CAPTURE, world, use_post=pruned,
                                   extra_pruned=st.session_state.get("pruned_ids"))
        return res["leaderboard"], res["candidates"], res["idle"]
    # Live: leaderboard numbers are the pre_prune P&L; the active badge reflects the LIVE registry, so
    # it flips the instant PRUNE runs real SQL. Candidates/idle are pre_prune concepts.
    rows = ledger.get_leaderboard(RUN_ID, "pre_prune")
    # Overlay LIVE rent (phase='live' only) onto the frozen pre_prune P&L — never mixed into show1's
    # captures, get_prune_candidates, or check_demo. Live retrievals are RENT-ONLY (no earnings).
    live_rent = ledger.get_live_rent(RUN_ID)
    live_earned = ledger.get_live_earned(RUN_ID)   # §7: scripted-question live earnings, if any
    for r in rows:
        lr = live_rent.get(r["bundle_id"], 0.0)
        le = live_earned.get(r["bundle_id"], 0.0)
        r["live_rent"], r["live_earned"] = lr, le
        r["total_rent"] += lr
        r["total_earned"] += le
        r["total_net"] += le - lr
    candidates = ledger.get_prune_candidates(RUN_ID, "pre_prune")
    idle_ids = [b["bundle_id"] for b in ledger.get_idle_bundles(RUN_ID, "pre_prune")]
    return rows, candidates, idle_ids


# --------------------------------------------------------------------------------------------------
# Rendering (written ONCE against the normalized row shape; never branches on REPLAY_MODE)
# --------------------------------------------------------------------------------------------------
def render_headline(rows: list[dict]) -> None:
    total_net = sum(r["total_net"] for r in rows if not r["is_idle"])
    st.markdown(f"""<div class="rent-panel">
      <div class="rent-tile-label">Estimated net $ this run</div>
      <div class="rent-headline">{money(total_net)}</div>
    </div>""", unsafe_allow_html=True)


def render_table(rows: list[dict]) -> None:
    # Non-idle rows only, sorted by net desc (idle rows live in the gray panel per PLAN Task 8 b2).
    body = sorted((r for r in rows if not r["is_idle"]), key=lambda r: -r["total_net"])
    trs = []
    for rank, r in enumerate(body, start=1):
        color = GREEN if r["total_net"] > 0 else RED
        badge = ('<span class="badge badge-active">ACTIVE</span>' if r["active"]
                 else '<span class="badge badge-pruned">PRUNED</span>')
        lr = r.get("live_rent", 0.0)   # live rent-only charge overlaid this run (0 unless a live query hit it)
        le = r.get("live_earned", 0.0)   # §7: live earnings from a scripted correct answer, if any
        chip = f'<span class="rent-chip">+{money(lr, 5)} rent</span>' if lr > 0 else ''
        earn_chip = (f'<span class="rent-chip-green" title="vs. benchmarked naive baseline">'
                     f'+{money(le, 5)} earned</span>' if le > 0 else '')
        tr_cls = ' class="rent-flash"' if (lr > 0 or le > 0) else ''   # flash the row where a live delta landed
        trs.append(
            f'<tr{tr_cls}><td>{rank}</td><td class="l">{r["bundle_id"]}</td><td class="l">{r["title"]}</td>'
            f'<td class="l" style="color:{MUTED}">{r["category"]}</td>'
            f'<td style="color:{GREEN}">{money(r["total_earned"])}{earn_chip}</td>'
            f'<td style="color:{AMBER}">{money(r["total_rent"])}{chip}</td>'
            f'<td style="color:{color};font-weight:700">{money(r["total_net"])}</td>'
            f'<td>{r["times_retrieved"]}</td><td>{badge}</td></tr>')
    st.markdown(
        '<table class="rent"><tr>'
        '<th>#</th><th class="l">Bundle</th><th class="l">Title</th><th class="l">Category</th>'
        '<th>Earned</th><th>Rent</th><th>Net</th><th>Included</th><th>Status</th></tr>'
        + "".join(trs) + "</table>", unsafe_allow_html=True)
    st.markdown(f'<div class="rent-foot" style="margin-top:6px">Rent = cost of being included in '
                f'prompts &middot; Earned = tokens saved when it made an answer correct &middot; '
                f'Net = earned &minus; rent</div>', unsafe_allow_html=True)


def _set_cost_tiles() -> None:
    """Populate the before/after cost tiles from the FROZEN pre/post captures (unchanged by fire vs.
    all-PRUNE — they always compare the captured runs, per §6)."""
    try:
        pre, post = load_agg(PRE_CAPTURE), load_agg(POST_CAPTURE)
        st.session_state.update(cost_before=pre["mean_memory_cost_per_query"],
                                cost_after=post["mean_memory_cost_per_query"])
    except Exception as e:  # noqa: BLE001 — captures may not exist yet in skeleton stage
        st.info(f"cost tiles need {PRE_CAPTURE} / {POST_CAPTURE} ({e}).")


def _removed_sentence(bundle_ids: list[str]) -> str:
    """Plain after-action sentence for FIRE/PRUNE — stashed in session_state (st.rerun() fires
    immediately after, same persistence pattern as fed_memory_html) so it survives the rerun."""
    ids = ", ".join(f"[{b}]" for b in bundle_ids)
    pronoun = "They" if len(bundle_ids) > 1 else "It"
    return (f'<div class="rent-panel" style="border:1px solid {RED};margin-top:6px">'
            f'<b style="color:{RED}">{ids} removed.</b> {pronoun} will no longer be included in any '
            f'prompt.</div>')


def _fire_bundle(bid: str, replay_mode: bool) -> None:
    """Prune exactly ONE candidate (audience picks the victim). Both candidates are support-map-guarded
    decoys, so any choice is safe. Live: real single-bundle SQL. Replay: local pruned_ids set."""
    if replay_mode:
        st.session_state["pruned_ids"].add(bid)   # unioned into compute_local_ledger's pruned_ids
    else:
        bundles.apply_prune([bid])                # REAL SQL, single bundle, zero LLM calls
    st.session_state["removed_notice_html"] = _removed_sentence([bid])
    _set_cost_tiles()
    st.rerun()


def render_red_panel(rows: list[dict], candidate_ids: list[str], replay_mode: bool) -> None:
    by_id = {r["bundle_id"]: r for r in rows}
    st.markdown('<div class="rent-tile-label" style="margin-top:14px">Not paying rent</div>',
                unsafe_allow_html=True)
    if not candidate_ids:
        st.markdown('<div class="rent-panel">No prune candidates in this run.</div>', unsafe_allow_html=True)
        return
    st.markdown('<div class="rent-red rent-panel" style="padding:8px 14px"><span class="rent-foot" '
                f'style="color:{TEXT}">Audience picks the victim — FIRE one, then PRUNE the rest.</span></div>',
                unsafe_allow_html=True)
    for bid in candidate_ids:
        r = by_id.get(bid, {})
        fired = not r.get("active", True)   # already pruned (live registry flag, or replay pruned_ids)
        c1, c2 = st.columns([6, 1])
        with c1:
            st.markdown(
                f'<div class="rent-panel rent-red" style="margin:4px 0"><b style="color:{RED}">{bid}</b> '
                f'{r.get("title","")} — retrieved {r.get("times_retrieved",0)} times, paid '
                f'<b style="color:{AMBER}">{money(r.get("total_rent",0.0))}</b> in rent, earned '
                f'<b>$0.0000</b> — never supported a correct answer.'
                f'<div class="rent-foot" style="margin-top:4px">removal is a reversible flag — the '
                f'memory is not deleted, it just stops being included</div></div>', unsafe_allow_html=True)
        with c2:
            if fired:
                st.markdown('<div class="badge badge-pruned" style="text-align:center;margin-top:16px">'
                            'FIRED</div>', unsafe_allow_html=True)
            elif st.button(f"FIRE {bid}", key=f"fire_{bid}"):
                _fire_bundle(bid, replay_mode)


def render_idle_panel(rows: list[dict], idle_ids: list[str]) -> None:
    by_id = {r["bundle_id"]: r for r in rows}
    st.markdown('<div class="rent-tile-label" style="margin-top:14px">Idle — not part of the P&amp;L</div>',
                unsafe_allow_html=True)
    lines = []
    for bid in idle_ids:
        r = by_id.get(bid, {})
        lines.append(f'<div style="margin:4px 0;color:{MUTED}"><b>{bid}</b> {r.get("title","")} — '
                     f'never entered prompt context. $0.0000 rent, $0.0000 earned. Audit candidate.</div>')
    if not lines:
        lines = [f'<div style="color:{MUTED}">No idle bundles in this run.</div>']
    st.markdown(f'<div class="rent-panel">{"".join(lines)}</div>', unsafe_allow_html=True)


def render_receipts(replay_mode: bool) -> None:
    st.markdown('<div class="rent-tile-label" style="margin-top:14px">Receipts — billed credits</div>',
                unsafe_allow_html=True)
    try:
        if replay_mode:
            receipts = load_receipts_snapshot()
        else:
            cur = get_conn().cursor()
            cur.execute("""SELECT start_time, model_name, query_tag, credits
                           FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY
                           WHERE query_tag LIKE %s ORDER BY start_time DESC LIMIT 20""", (f"{RUN_ID}%",))
            receipts = [{"start_time": str(r[0]), "model_name": r[1], "query_tag": r[2],
                         "credits": float(r[3])} for r in cur.fetchall()]
    except Exception as e:  # noqa: BLE001 — receipts are corroboration only; never block the app
        st.markdown(f'<div class="rent-panel rent-foot">receipts unavailable ({e}).</div>',
                    unsafe_allow_html=True)
        return
    # Local-backend snapshots hold a note row, not receipt rows (ACCOUNT_USAGE is Snowflake-only).
    # Render the honest note instead of KeyError-ing mid-demo.
    if not receipts or "start_time" not in receipts[0]:
        note = (receipts[0].get("note") if receipts and isinstance(receipts[0], dict) else None) or \
               "billed-credits receipts exist only on the Snowflake backend"
        st.markdown(f'<div class="rent-panel rent-foot">{note} — run with RENT_BACKEND=snowflake '
                    f'for the metering receipts panel.</div>', unsafe_allow_html=True)
        return
    rows_html = "".join(
        f'<tr><td class="l">{r["start_time"]}</td><td class="l">{r["model_name"]}</td>'
        f'<td class="l">{r["query_tag"]}</td><td>{r["credits"]:.6f}</td></tr>' for r in receipts)
    st.markdown('<div class="rent-panel"><table class="rent"><tr>'
                '<th class="l">Start</th><th class="l">Model</th><th class="l">Query tag</th>'
                f'<th>Credits</th></tr>{rows_html}</table></div>', unsafe_allow_html=True)
    st.markdown('<div class="rent-foot">billed credits — Snowflake metering, ~5 min lag — '
                'corroborates the run above, never drives the live ticker.</div>', unsafe_allow_html=True)


def render_footer() -> None:
    st.markdown(f"""<div class="rent-panel rent-foot">
      Request-level tokens (naive/memory prompt totals, and therefore $ earned) are
      <b style="color:{TEXT}">MEASURED</b> — from AI_COMPLETE's <code>show_details</code>.
      Per-bundle rent allocation ($ rent, $ net) is
      <b style="color:{TEXT}">TOKENIZER-ESTIMATED</b> (cl100k_base via tiktoken) — Claude's exact
      per-snippet token count isn't exposed by AI_COMPLETE, so each bundle's rent is an estimate of
      its share of the measured total, at claude-haiku-4-5's published rate ($0.35/M-token credits
      &times; $2.00/credit).
      <br>Active backend: <b style="color:{TEXT}">{snow.BACKEND}</b> / LLM: <b style="color:{TEXT}">{snow.LLM}</b>{
      " — mock is a pipeline-test model (tiktoken-estimated tokens); demo with a real LLM backend." if snow.LLM == "mock" else ""}
    </div>""", unsafe_allow_html=True)


def render_cost_tiles() -> None:
    before = st.session_state.get("cost_before")
    after = st.session_state.get("cost_after")
    if before is None or after is None:
        return
    delta = after - before
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""<div class="rent-panel">
          <div class="rent-tile-label">Est. prompt-input cost / query — before</div>
          <div class="rent-tile-val" style="color:{TEXT}">{money(before, 5)}</div></div>""",
                    unsafe_allow_html=True)
    with col2:
        st.markdown(f"""<div class="rent-panel">
          <div class="rent-tile-label">Est. prompt-input cost / query — after</div>
          <div class="rent-tile-val rent-countpop" style="color:{GREEN}">{money(after, 5)}
          <span style="font-size:1rem;color:{GREEN}"> {delta:+.5f}</span></div></div>""",
                    unsafe_allow_html=True)
    st.caption("our fixed regression set retained an identical score at lower cost")


# --------------------------------------------------------------------------------------------------
# Task 9 — regression replay + one live/replayed query (ALWAYS render from a captured file at click
# time in EITHER mode — satisfies the binding two-live-call cap for the regression suite)
# --------------------------------------------------------------------------------------------------
def render_proof_summary_strip() -> None:
    """The ONE main thing on screen 4, first: a compact before/after strip computed from the frozen
    capture files (never hardcoded) — score and mean tokens/query, pre-prune vs. post-prune."""
    try:
        pre = json.load(open(PRE_CAPTURE))["events"]
        post = json.load(open(POST_CAPTURE))["events"]
        pre_correct = sum(1 for e in pre if e["memory"]["is_correct"])
        post_correct = sum(1 for e in post if e["memory"]["is_correct"])
        pre_tokens = sum(e["memory"]["prompt_tokens"] for e in pre) / len(pre)
        post_tokens = sum(e["memory"]["prompt_tokens"] for e in post) / len(post)
        pct = (post_tokens - pre_tokens) / pre_tokens * 100 if pre_tokens else 0.0
        st.markdown(f"""<div class="rent-panel" style="border:1px solid {GREEN}">
          <div class="rent-tile-label">Measured, recorded run</div>
          <div style="font-size:1.35rem;font-weight:700;margin-top:4px;color:{TEXT}">
            {pre_correct}/{len(pre)} before &middot; {post_correct}/{len(post)} after &middot;
            {pre_tokens:.1f} &rarr; {post_tokens:.1f} tokens/query &middot;
            <span style="color:{GREEN}">{pct:+.1f}%</span>
          </div>
        </div>""", unsafe_allow_html=True)
    except Exception as e:  # noqa: BLE001 — captures may not exist yet in skeleton stage
        st.info(f"summary strip needs {PRE_CAPTURE} / {POST_CAPTURE} ({e}).")


def animate_regression_suite(pruned: bool) -> None:
    path = POST_CAPTURE if pruned else PRE_CAPTURE
    st.caption("measured pre-show run (replayed) — zero live calls right now")
    for ev in json.load(open(path))["events"]:
        r = ev["memory"]
        ok = r["is_correct"]
        icon, color = ("PASS", GREEN) if ok else ("FAIL", RED)
        st.markdown(f'<div style="font-family:{MONO}"><b style="color:{color}">[{icon}]</b> '
                    f'{ev["question_id"]}: {r["model_answer"]}  '
                    f'<span style="color:{MUTED}">(gold: {r["gold_answer"]})</span></div>',
                    unsafe_allow_html=True)


def _match_scripted_question(question: dict):
    """§7: return the fixture question dict if this live query IS one of the 8 scripted eval questions
    (selectbox pick by id, or freeform text that equals a question's wording) — else None. Only
    scripted questions have gold answers, so only they can be graded + earn live."""
    world = load_world()
    qid = question.get("question_id", "freeform")
    if qid != "freeform":
        return next((q for q in world["questions"] if q["question_id"] == qid), None)
    nq = normalize(question["query"])
    return next((q for q in world["questions"] if normalize(q["query"]) == nq), None)


def _captured_naive_tokens() -> dict:
    """§7 honesty pin: a live prompt runs ONE arm, so the earnings counterfactual is show1's
    BENCHMARKED naive baseline — {question_id: naive_prompt_tokens} from the frozen pre_prune capture."""
    try:
        data = json.load(open(PRE_CAPTURE))
        return {e["question_id"]: e["naive"]["prompt_tokens"] for e in data["events"]}
    except Exception:  # noqa: BLE001
        return {}


def _live_prompt(query: str):
    """Build a live memory-arm prompt for ANY live query (fixed or freeform), honoring bundles.py's
    no-backfill freeze + active filter. Content comes from the FIXTURE for fixture bundles (canonical
    text) and from EVEROS for live-fed bundles that aren't in the fixture file — so a query that
    retrieves a just-fed memory works and is rent-charged. This replaces benchmark.build_memory_prompt
    on the live path, which only knows fixture text and would KeyError on a live-fed bundle (B13+).
    Returns (prompt, hits, bundle_tokens) — the same shape build_memory_prompt returns."""
    hits = bundles.recall_bundles(query, user_id=USER_ID)   # active-only, no-backfill: [{bundle_id, score, rank}]
    if not hits:
        return None, [], {}
    # a second recall carries the EverOS-extracted text (recall_bundles drops content); map session->bundle.
    # No min_score here: the gated seat list already came from recall_bundles (client-side relative gate,
    # MIN_REL) — this call is only a content lookup, and the server-side min_score param is the broken API
    # (returns empty sets, dry-run finding #2).
    raw = mem.recall(query, user_id=USER_ID, top_k=bundles.TOP_K_DEFAULT + bundles.OVERFETCH_PAD)
    reg = bundles.get_session_to_bundle_map()
    content_by_bundle = {}
    for ep in raw:
        info = reg.get(ep["session_id"])
        if info and info["bundle_id"] not in content_by_bundle:
            content_by_bundle[info["bundle_id"]] = ep.get("content") or ""
    fixture_by_id = {b["bundle_id"]: b for b in load_world()["bundles"]}
    ids = sorted({h["bundle_id"] for h in hits})
    blocks, bundle_tokens = {}, {}
    for bid in ids:
        if bid in fixture_by_id:
            b = fixture_by_id[bid]
            block = f"[{bid}] {b['title']}\n{b['content']}"
        else:
            block = f"[{bid}] (live-fed)\n{content_by_bundle.get(bid, '')}"   # EverOS-extracted text
        blocks[bid] = block
        bundle_tokens[bid] = len(ENC.encode(block))   # tokenizer-estimated rent basis, same as benchmark
    ctx = "\n\n".join(blocks[i] for i in ids)   # <=6 short bundles: well under the 8K cap, no capping needed
    prompt = f"{SYSTEM_PROMPT}\n\nCONTEXT:\n{ctx}\n\nQUESTION: {query}\nANSWER:"
    return prompt, hits, bundle_tokens


def _used_memories_sentence(bundle_ids: list[str]) -> str:
    """Plain after-action sentence rendered under every answered query (replay or live) — reuses the
    real bundle ids that were actually retrieved and rent-charged for this answer."""
    ids = ", ".join(f"[{b}]" for b in bundle_ids)
    return (f'<div class="rent-foot" style="margin-top:4px">This answer used {ids}. Each memory '
            f'listed was charged rent for being included.</div>')


def run_query(question: dict, replay_mode: bool, run_id: str) -> None:
    qid = question.get("question_id", "freeform")
    if replay_mode:
        # Only the fixed regression questions have a capture to replay; freeform is live-only and is
        # not offered in replay mode, so this branch always has a matching event.
        ev = next((e for e in json.load(open(POST_CAPTURE))["events"] if e["question_id"] == qid), None)
        if ev is None:
            st.warning("freeform queries run live only — replay has no captured event for them.")
            return
        r = ev["memory"]
        st.markdown(f'<div class="rent-panel"><b style="color:{AMBER}">REPLAYED</b> — {question["query"]}'
                    f'<br>&rarr; <b>{r["model_answer"]}</b><br>'
                    f'<span style="color:{MUTED}">context: {r["context_bundle_ids"]}, '
                    f'{r["prompt_tokens"]} prompt tokens</span></div>', unsafe_allow_html=True)
        st.markdown(_used_memories_sentence(r["context_bundle_ids"]), unsafe_allow_html=True)
        return
    prompt, hits, bundle_tokens = _live_prompt(question["query"])   # fixture text for fixture bundles, EverOS text for live-fed
    if not hits:   # nothing cleared the min_score gate — the honest miss (the gate working IS the feature)
        st.markdown(f'<div class="rent-panel"><b style="color:{AMBER}">LIVE</b> — {question["query"]}'
                    f'<br>&rarr; <b>no memory pays rent on that — I don\'t know.</b><br>'
                    f'<span style="color:{MUTED}">retrieval returned nothing above the score gate.</span>'
                    f'</div>', unsafe_allow_html=True)
        return
    text, usage = ai_complete(MODEL, prompt, purpose="rent_eval_live", run_id=run_id,
                              user_id=USER_ID, agent_tag="rent:memory:live", model_parameters=GEN_PARAMS,
                              extra={"question_id": qid})
    # Real Snowflake retrieval row, phase='live' (the RENT basis) — isolated from show1's pre/post P&L
    # and from get_prune_candidates / check_demo (both scoped to phase='pre_prune').
    ledger.insert_retrieval_log(run_id, "live", qid, hits, bundle_tokens)
    # Savings odometer: what this query WOULD have cost with the full 12-bundle fixture context,
    # tokenizer-counted (zero extra LLM calls, ESTIMATED label) minus the measured actual prompt.
    naive_est = len(ENC.encode(build_naive_prompt(load_world(), {"query": question["query"]})[0]))
    saved_est = max(naive_est - usage["prompt_tokens"], 0)
    st.session_state["odo_tokens"] = st.session_state.get("odo_tokens", 0) + saved_est
    st.session_state["odo_last"] = saved_est
    # §7 (optional): a SCRIPTED eval question answered correctly also EARNS live — savings basis is the
    # question's CAPTURED naive baseline (a live prompt runs one arm), even-split across supporting
    # bundles retrieved. Freeform non-eval questions stay rent-only (no gold -> no earnings, by design).
    earned_note = "rent-only (no graded outcome to earn on)"
    scripted = _match_scripted_question(question)
    if scripted is not None:
        golds = scripted["gold_answer"] if isinstance(scripted["gold_answer"], list) else [scripted["gold_answer"]]
        if normalize(text) in {normalize(g) for g in golds}:
            naive_base = _captured_naive_tokens().get(scripted["question_id"])
            sup_hits = [h["bundle_id"] for h in hits if h["bundle_id"] in set(scripted["supporting_bundle_ids"])]
            if naive_base and sup_hits:
                saved = max(naive_base - usage["prompt_tokens"], 0)
                per = saved / len(sup_hits) / 1e6 * MODEL_RATES[MODEL] * USD_PER_CREDIT
                for bid in sup_hits:
                    ledger.insert_live_earning(run_id, scripted["question_id"], bid, per)
                earned_note = (f"CORRECT — {', '.join(sup_hits)} earned {money(per * len(sup_hits), 6)} "
                               f"vs. benchmarked naive baseline")
    st.markdown(f'<div class="rent-panel"><b style="color:{GREEN}">LIVE</b> — {question["query"]}'
                f'<br>&rarr; <b>{text.strip()}</b><br>'
                f'<span style="color:{MUTED}">context: {[h["bundle_id"] for h in hits]}, '
                f'{usage["prompt_tokens"]} prompt tokens — {earned_note}</span></div>',
                unsafe_allow_html=True)
    st.markdown(_used_memories_sentence([h["bundle_id"] for h in hits]), unsafe_allow_html=True)


def _show_prefed_fallback() -> None:
    """Timeout/failure path for the feed box: pivot to the pre-fed Initech memory (seed.py --prefeed).
    Never raises — worst case it shows the known fact text."""
    try:
        hits = mem.recall(seed.PREFEED_FACT, user_id=USER_ID, top_k=12)
        m = next((h for h in hits if h["session_id"] == seed.PREFEED_SESSION), None)
        content = m["content"] if m and m.get("content") else seed.PREFEED_FACT
    except Exception:  # noqa: BLE001
        content = seed.PREFEED_FACT
    st.markdown(f'<div class="rent-panel" style="border:1px solid {AMBER}">'
                f'<div class="rent-tile-label" style="color:{AMBER}">Pre-fed memory (fallback)</div>'
                f'<div style="margin-top:6px">{content}</div>'
                f"<div class=\"rent-foot\" style=\"margin-top:6px\">extraction queued — using this "
                f"morning's pre-fed memory.</div></div>", unsafe_allow_html=True)


def feed_memory(text: str) -> None:
    """Live-mode only (§1): feed one fact, poll until EverOS has extracted+indexed it (~10s verify-loop
    mirroring seed.py), register it as a new bundle, and show the EXTRACTED text — what EverOS distilled,
    not what was typed. Never crashes or blocks: on timeout/error it falls back to the pre-fed memory."""
    session_id = f"live-fed-{uuid4().hex[:6]}"
    try:
        # extraction needs a conversation, not a bare line (dry-run finding — see mem.remember)
        mem.remember(session_id=session_id,
                     messages=seed.wrap_conversation(USER_ID, "live note", text))
    except Exception as e:  # noqa: BLE001
        st.warning(f"feed failed to enqueue ({e}) — using this morning's pre-fed memory.")
        _show_prefed_fallback()
        return
    born = None
    with st.spinner("EverOS extracting the memory…"):
        deadline = time.time() + 10   # ~10s; do NOT raise past 15s without escalating (per prompt)
        while time.time() < deadline:
            try:
                hits = mem.recall(text, user_id=USER_ID, top_k=12)
            except Exception:  # noqa: BLE001
                hits = []
            born = next((h for h in hits if h["session_id"] == session_id), None)
            if born:
                break
            time.sleep(1.0)
    if born is None:
        st.warning("extraction queued — using this morning's pre-fed memory.")
        _show_prefed_fallback()
        return
    title = (text[:38] + "…") if len(text) > 38 else text
    bundle_id = seed.upsert_live_bundle(session_id, title)
    # Stashed in session_state (not rendered directly) so the "memory born" panel survives a screen
    # switch away from "2 · Hire" and back — the call site renders it on every visit, not just this run.
    st.session_state["fed_memory_html"] = (
        f'<div class="rent-panel rent-countpop" style="border:1px solid {GREEN}">'
        f'<div class="rent-tile-label" style="color:{GREEN}">Memory born — {bundle_id} '
        f'(ACTIVE, in the red)</div>'
        f'<div style="margin-top:6px">{born["content"]}</div>'
        f'<div class="rent-foot" style="margin-top:6px">Stored as {bundle_id}. It has earned $0 so '
        f'far — it gets charged rent every time it is included in a prompt. Query it below to watch '
        f'that happen.</div>'
        f'</div>')


def render_odometer(replay_mode: bool) -> None:
    """The centerpiece number: cumulative savings. Two labeled sources, never conflated —
    the eval set's MEASURED savings (from the pre capture) and, in live mode, the session's
    ESTIMATED savings ticker (tokenizer naive-baseline minus measured actual, per live query)."""
    try:
        pre = json.load(open(PRE_CAPTURE))["events"]
        eval_saved = sum(e["naive"]["prompt_tokens"] - e["memory"]["prompt_tokens"] for e in pre)
    except Exception:  # noqa: BLE001 — skeleton stage
        eval_saved = None
    odo = st.session_state.get("odo_tokens", 0)
    odo_usd = odo / 1e6 * MODEL_RATES[MODEL] * USD_PER_CREDIT
    last = st.session_state.get("odo_last")
    pop = ' rent-countpop' if last else ''
    delta_chip = f'<span style="font-size:1rem;color:{GREEN}"> +{last:,}</span>' if last else ''
    live_html = "" if replay_mode else (
        f'<div class="rent-tile-label" style="margin-top:4px">Saved this session — live queries</div>'
        f'<div class="rent-headline{pop}">{odo:,} tok <span style="font-size:1.6rem">({money(odo_usd, 5)})</span>'
        f'{delta_chip}</div>'
        f'<div class="rent-foot">estimated vs full-context baseline (tokenizer) — climbs faster after PRUNE</div>')
    eval_html = ("" if eval_saved is None else
                 f'<div class="rent-foot" style="margin-top:6px">eval set: {eval_saved:,} prompt tokens '
                 f'saved vs naive — <b style="color:{TEXT}">measured</b> (8-question paired benchmark)</div>')
    if live_html or eval_html:
        st.markdown(f'<div class="rent-panel">{live_html}{eval_html}</div>', unsafe_allow_html=True)


AUTOPILOT_LOG = "captures/autopilot_log.jsonl"


def render_autopilot_panel(replay_mode: bool) -> None:
    """Activity feed from autopilot's audit log + the on-stage 'run one real cycle' button (live only).
    Replay mode renders the committed log file — zero external calls."""
    st.markdown('<div class="rent-tile-label" style="margin-top:14px">Autopilot — self-pruning audit</div>',
                unsafe_allow_html=True)
    lines = []
    try:
        entries = [json.loads(l) for l in open(AUTOPILOT_LOG)][-8:]
        for e in reversed(entries):
            act = e.get("action", "?")
            color = {"pruned": GREEN, "rolled_back": RED}.get(act, MUTED)
            detail = ""
            if act == "pruned":
                detail = (f' — pruned {", ".join(e["candidates"])}: score {e["pre_score"]}/8→{e["post_score"]}/8, '
                          f'{e["pre_mean_tokens"]:.0f}→{e["post_mean_tokens"]:.0f} tok/query')
            elif act == "rolled_back":
                detail = f' — {", ".join(e["candidates"])} RESTORED ({e.get("reason", "")})'
            lines.append(f'<div style="margin:3px 0"><span style="color:{MUTED}">{e.get("ts","")}</span> '
                         f'<b style="color:{color}">{act.upper()}</b>{detail}</div>')
    except FileNotFoundError:
        lines = [f'<div style="color:{MUTED}">no audit cycles yet — the loop runs on a schedule '
                 f'(`python autopilot.py --interval 300`) or on demand below.</div>']
    except Exception as e:  # noqa: BLE001
        lines = [f'<div style="color:{MUTED}">audit log unreadable ({e}).</div>']
    st.markdown(f'<div class="rent-panel">{"".join(lines)}</div>', unsafe_allow_html=True)
    if replay_mode:
        # Live-only control — still rendered (disabled) so it's discoverable, not silently missing.
        st.button("Run audit cycle now", disabled=True, key="audit_cycle_disabled")
        st.caption("Running a live audit cycle requires live mode — untick 'Replay mode' in the "
                   "sidebar.")
    elif st.button("Run audit cycle now"):
        with st.spinner("autopilot: verify → prune → verify …"):
            r = subprocess.run([sys.executable, "autopilot.py", "--once", "--run-id", RUN_ID],
                               capture_output=True, text=True)
        if r.returncode != 0:
            st.error(f"autopilot cycle failed: {r.stderr[-400:]}")
        st.rerun()


# --------------------------------------------------------------------------------------------------
# Layout — 5 screens mirroring plans/PLAN-rent.md's "Demo script (3 minutes)" beats, in order.
# --------------------------------------------------------------------------------------------------
SCREENS = ["1 · The P&L", "2 · Hire", "3 · Fire", "4 · Proof", "5 · Autopilot"]

# Presenter cues: (time window, opening line) verbatim/near-verbatim from the plan's demo script —
# small, muted rehearsal cards, never the source of truth (the plan doc is).
PRESENTER_CUES = {
    "1 · The P&L": ("0:20–1:00", "Its rent is what it cost to sit in context; its earnings are the "
                     "tokens we saved on the one question it actually answered — net is the "
                     "difference, and it's real, not a guess."),
    "2 · Hire": ("1:00–1:30", "Every memory starts life in the red — it has to earn its seat."),
    "3 · Fire": ("1:30–1:45", "Which one dies first? You choose."),
    "4 · Proof": ("1:45–2:50", "Our fixed regression set retained an identical score at lower cost."),
    "5 · Autopilot": ("2:50–3:00", "Context is capital. We built the P&L for it — and it does this by itself."),
}


def render_presenter_cue(screen_name: str) -> None:
    """Presenter-only rehearsal cue (time window + opening line) — lives in the SIDEBAR, not the
    canvas, so the main screen stays audience-facing only. Updates with the sidebar screen radio."""
    window, line = PRESENTER_CUES[screen_name]
    st.sidebar.caption(f'{window} — "{line}"')


# Self-explanatory text (plain language, no presenter needed) — one always-visible sentence per
# screen plus a shared "About this project" expander, so the app stands alone when screenshared,
# hosted, or opened cold by a judge.
ABOUT_PROJECT = (
    "**Rent tracks what an AI assistant's stored memories cost, and what they contribute.**\n\n"
    "When the assistant answers a question, a few stored memories are included in the prompt as "
    "context. Every inclusion costs tokens — that cost is the memory's **rent**. When a memory was "
    "the reason an answer came out correct, it is credited with the tokens it saved compared to "
    "sending the assistant the entire history — that credit is what it **earned**. The ledger adds "
    "these up per memory.\n\n"
    "Memories that keep being included but never help can then be removed. Before any removal "
    "counts, the same 8-question accuracy test runs again — a removal is only kept if the score is "
    "unchanged and the cost per question went down. An autopilot can run this find → verify → "
    "remove → re-verify loop on a schedule, and restores the memories automatically if accuracy "
    "drops.\n\n"
    "Stack: EverOS (the memory layer that stores and retrieves memories) · a SQL ledger for every "
    "call and charge (Snowflake or SQLite) · any LLM for answers. Labels on every number: "
    "*measured* means it came from the model API's own token counts; *estimated* means it was "
    "computed with a tokenizer."
)

SCREEN_EXPLAINERS = {
    "1 · The P&L": "This table is the ledger: every memory the assistant holds, what it has cost to "
                    "include in prompts (**rent**), what it saved by making answers correct "
                    "(**earned**), and the net. Green rows pay for themselves; red rows don't.",
    "2 · Hire": "Type a fact and it becomes a new stored memory. From now on it can be pulled into "
                 "prompts — which costs rent — and it starts at $0 earned. Ask the question below "
                 "to see it retrieved and charged for the first time.",
    "3 · Fire": "These memories keep being included in prompts but have never contributed to a "
                 "correct answer. Removing them makes every future prompt smaller and cheaper. "
                 "Removal is a flag, not a delete — it is reversible.",
    "4 · Proof": "The same 8-question test, before and after removal: identical score, fewer tokens "
                  "per question. These results come from a recorded run; the query box below runs "
                  "against the live system.",
    "5 · Autopilot": "The find → verify → remove → re-verify loop from the previous screens, run "
                      "automatically on a schedule. Each line below is one audit cycle; if accuracy "
                      "had dropped, the removal would have been rolled back and logged.",
}

# Step-header content — audience-facing, plain-language titles (distinct from the terse sidebar
# labels in SCREENS) + a one/two-sentence subtitle trimmed from SCREEN_EXPLAINERS above.
SCREEN_TITLES = {
    "1 · The P&L": "What each memory costs — and what it's worth",
    "2 · Hire": "Add a memory, watch it get charged",
    "3 · Fire": "Remove the memories that never help",
    "4 · Proof": "Same test, before and after — did answers get worse?",
    "5 · Autopilot": "The loop that runs by itself",
}

def _first_sentences(text: str, n: int = 1) -> str:
    """Plain-text trim of a SCREEN_EXPLAINERS entry to its first N sentences — strips the markdown
    bold markers (the subtitle renders inside a raw HTML block, not through st.markdown's parser)."""
    parts = text.replace("**", "").split(". ")
    return ". ".join(parts[:n]).rstrip(".") + "."


SCREEN_SUBTITLES = {name: _first_sentences(text, 2 if name == "2 · Hire" else 1)
                    for name, text in SCREEN_EXPLAINERS.items()}


def render_step_header(screen_name: str) -> None:
    """Audience-facing block at the top of every screen: STEP N OF 5 eyebrow, a large plain-language
    title, and a one/two-sentence subtitle — normal contrast, not muted, so a glance answers "what am
    I looking at" in under 2 seconds. Replaces the old explainer-panel placement."""
    step_n = SCREENS.index(screen_name) + 1
    st.markdown(f"""<div style="margin:6px 0 20px">
      <div style="color:{MUTED};font-size:0.78rem;letter-spacing:.14em;text-transform:uppercase">
        STEP {step_n} OF {len(SCREENS)}</div>
      <div style="color:{TEXT};font-size:1.6rem;font-weight:700;line-height:1.3;margin-top:2px">
        {SCREEN_TITLES[screen_name]}</div>
      <div style="color:{TEXT};font-size:0.95rem;margin-top:6px;opacity:.82">
        {SCREEN_SUBTITLES[screen_name]}</div>
    </div>""", unsafe_allow_html=True)


def render_about_expander() -> None:
    """The 'About this project' expander — kept, but relocated to the BOTTOM of every screen, just
    above the footer, so the canvas leads with the one important thing instead of a stack of panels."""
    with st.expander("About this project — what Rent does"):
        st.markdown(ABOUT_PROJECT)


def _sidebar_run_info() -> str:
    """Muted sidebar line: run_id / backend / model — model sourced from the pre capture when present,
    falling back to the active LLM (snow.LLM) in skeleton stage before any capture exists."""
    model = None
    try:
        model = json.load(open(PRE_CAPTURE)).get("model")
    except Exception:  # noqa: BLE001 — pre-capture may not exist yet in skeleton stage
        pass
    return f"run: {RUN_ID} · backend: {snow.BACKEND} · model: {model or snow.LLM}"


REPLAY_MODE = st.sidebar.checkbox("Replay mode (zero external calls)",
                                  value=os.environ.get("RENT_REPLAY_MODE") == "1")
st.sidebar.caption(_sidebar_run_info())
screen = st.sidebar.radio("Screen", SCREENS)
render_presenter_cue(screen)   # presenter-only time-window/quote — sidebar only, updates with the pick
st.sidebar.caption("Run the demo top to bottom: 1 → 2 → 3 → 4 → 5. Each screen needs at most a "
                   "click or two — the cue above is the presenter line for whichever screen is "
                   "selected.")
st.session_state.setdefault("pruned", False)
st.session_state.setdefault("pruned_ids", set())   # replay-mode fire-buttons: audience-picked victims

# Global elements, every screen: title strip + REPLAY badge, then the savings odometer, then the
# audience-facing step header for whichever screen is selected. render_footer() closes every screen
# at the bottom, with the About expander directly above it.
st.markdown(f'<div style="color:{AMBER};font-size:1.1rem;letter-spacing:.14em">RENT — THE MEMORY P&amp;L'
            f'{"  ·  REPLAY" if REPLAY_MODE else ""}</div>', unsafe_allow_html=True)
render_odometer(REPLAY_MODE)
render_step_header(screen)

try:
    rows, candidate_ids, idle_ids = load_view(REPLAY_MODE, st.session_state["pruned"])
except Exception as e:  # noqa: BLE001 — pre-capture / pre-Snowflake skeleton stage: render guidance
    rows, candidate_ids, idle_ids = None, [], []
    st.warning(f"Ledger view unavailable ({e}). In live mode this needs Snowflake + a benchmarked "
               f"run_id; in replay mode it needs {PRE_CAPTURE} / {POST_CAPTURE}.")

if screen == "1 · The P&L":
    # 0:20–1:00 — the ranked ledger story.
    if rows is not None:
        render_headline(rows)
        render_table(rows)
        render_idle_panel(rows, idle_ids)

elif screen == "2 · Hire":
    # 1:00–1:30 — watch a memory get born and pay its first rent. Feed box leads the screen.
    st.markdown('<div class="rent-tile-label">Feed the agent a fact</div>', unsafe_allow_html=True)
    if REPLAY_MODE:
        # Feed box is LIVE-only — but the control still RENDERS (disabled), so it's discoverable
        # rather than silently missing; the pre-fed fallback panel shows what an earlier feed looked
        # like (same panel the live path falls back to on an extraction timeout).
        st.text_input("Feed the agent a fact", key="feed_text_disabled", disabled=True,
                      value="Initech signed 2026-08-01; we promised them a 99.99% uptime SLA")
        st.caption("Feeding requires live mode — untick 'Replay mode' in the sidebar. Below is a "
                   "memory that was fed earlier.")
        _show_prefed_fallback()
    else:
        # Pre-filled with the scripted fact — click-through demo needs no typing, but stays editable
        # for a genuinely live/off-script fact if the presenter wants one.
        fed = st.text_input("Feed the agent a fact", key="feed_text",
                            value="Initech signed 2026-08-01; we promised them a 99.99% uptime SLA")
        if st.button("Feed the agent") and fed.strip():
            feed_memory(fed.strip())
        if st.session_state.get("fed_memory_html"):   # survives switching away and back to this screen
            st.markdown(st.session_state["fed_memory_html"], unsafe_allow_html=True)

    st.markdown("---")
    st.markdown('<div class="rent-tile-label">Query it back — freeform (live)</div>', unsafe_allow_html=True)
    if REPLAY_MODE:
        st.text_input("Ask anything", key="freeform_q_disabled", disabled=True,
                      value="What uptime did we promise Initech?")
        st.caption("Freeform queries require live mode — untick 'Replay mode' in the sidebar to try "
                   "one.")
    else:
        # Pre-filled to match the scripted fact above — click "Run query" with no typing needed.
        free = st.text_input("Ask anything", key="freeform_q",
                             value="What uptime did we promise Initech?")
        if st.button("Run query", key="run_freeform") and free.strip():
            run_query({"query": free.strip(), "question_id": "freeform"}, REPLAY_MODE, RUN_ID)

elif screen == "3 · Fire":
    # 1:30–1:45 — audience picks the victim; red panel with FIRE buttons leads the screen.
    if rows is not None:
        render_red_panel(rows, candidate_ids, REPLAY_MODE)
    if st.session_state.get("removed_notice_html"):   # plain after-action sentence, FIRE or PRUNE
        st.markdown(st.session_state["removed_notice_html"], unsafe_allow_html=True)
    st.markdown("---")
    if st.button("PRUNE", type="primary"):
        candidates = json.load(open(PRUNE_CANDIDATES_PATH))   # frozen in Task 7
        if REPLAY_MODE:
            st.session_state["pruned"] = True   # LOCAL state flip only — zero Snowflake calls
        else:
            bundles.apply_prune(candidates)                       # REAL SQL, live, zero LLM calls
            st.session_state["pruned"] = True
        st.session_state["removed_notice_html"] = _removed_sentence(candidates)
        _set_cost_tiles()
        st.rerun()
    render_cost_tiles()

elif screen == "4 · Proof":
    # 1:45–2:50 — identical score, lower cost, receipts corroborate. The compact summary strip
    # (measured, recorded run) leads the screen; the detailed suite, live query, and receipts follow.
    render_proof_summary_strip()

    st.markdown("---")
    st.markdown('<div class="rent-tile-label">Fixed regression set (replayed)</div>',
                unsafe_allow_html=True)
    try:
        animate_regression_suite(st.session_state["pruned"])
    except Exception as e:  # noqa: BLE001
        st.warning(f"regression capture unavailable ({e}) — needs {PRE_CAPTURE} / {POST_CAPTURE}.")

    st.markdown("---")
    st.markdown('<div class="rent-tile-label">One query — against the current (pruned) registry</div>',
                unsafe_allow_html=True)
    try:
        world = load_world()
        qmap = {q["question_id"]: q for q in world["questions"]}
        qid = st.selectbox("Question", list(qmap), index=0)
        if st.button("Run query", key="run_scripted"):
            run_query(qmap[qid], REPLAY_MODE, RUN_ID)
    except Exception as e:  # noqa: BLE001
        st.warning(f"query control unavailable ({e}).")

    st.markdown("---")
    render_receipts(REPLAY_MODE)

else:  # "5 · Autopilot" — closing beat: it does this by itself. Audit log leads, run-cycle button follows.
    render_autopilot_panel(REPLAY_MODE)

render_about_expander()   # moved to the bottom of every screen, just above the footer
render_footer()
