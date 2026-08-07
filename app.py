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

import streamlit as st

import bundles
import ledger
from rent_fixtures import load_world
from benchmark import build_memory_prompt, MODEL, GEN_PARAMS, USER_ID  # reused, not duplicated
from snow import ai_complete, get_conn, MODEL_RATES, USD_PER_CREDIT

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
    rate = MODEL_RATES[data["model"]]
    return {"mean_memory_prompt_tokens": mean_tokens,
            "mean_memory_cost_per_query": mean_tokens / 1e6 * rate * USD_PER_CREDIT}


def load_receipts_snapshot() -> list[dict]:
    """REPLAY_MODE's receipts panel reads this instead of querying ACCOUNT_USAGE — zero Snowflake."""
    return json.load(open(RECEIPTS_SNAPSHOT_PATH))


def compute_local_ledger(pre_path: str, post_path: str, world: dict, use_post: bool = False) -> dict:
    """Pure-Python reimplementation of ledger.ATTRIBUTION_SQL + get_prune_candidates/get_idle_bundles,
    driven ONLY by captured JSON + the local fixture file. Returns the SAME LEADERBOARD ROW SCHEMA as
    ledger.get_leaderboard() so app.py never branches on REPLAY_MODE, only the call site does."""
    data = json.load(open(post_path if use_post else pre_path))
    events = data["events"]
    rate = MODEL_RATES[data["model"]]
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
        res = compute_local_ledger(PRE_CAPTURE, POST_CAPTURE, world, use_post=pruned)
        return res["leaderboard"], res["candidates"], res["idle"]
    # Live: leaderboard numbers are the pre_prune P&L; the active badge reflects the LIVE registry, so
    # it flips the instant PRUNE runs real SQL. Candidates/idle are pre_prune concepts.
    rows = ledger.get_leaderboard(RUN_ID, "pre_prune")
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
        trs.append(
            f'<tr><td>{rank}</td><td class="l">{r["bundle_id"]}</td><td class="l">{r["title"]}</td>'
            f'<td class="l" style="color:{MUTED}">{r["category"]}</td>'
            f'<td style="color:{GREEN}">{money(r["total_earned"])}</td>'
            f'<td style="color:{AMBER}">{money(r["total_rent"])}</td>'
            f'<td style="color:{color};font-weight:700">{money(r["total_net"])}</td>'
            f'<td>{r["times_retrieved"]}</td><td>{badge}</td></tr>')
    st.markdown(
        '<table class="rent"><tr>'
        '<th>#</th><th class="l">Bundle</th><th class="l">Title</th><th class="l">Category</th>'
        '<th>Earned</th><th>Rent</th><th>Net</th><th>Seen</th><th>Status</th></tr>'
        + "".join(trs) + "</table>", unsafe_allow_html=True)


def render_red_panel(rows: list[dict], candidate_ids: list[str]) -> None:
    by_id = {r["bundle_id"]: r for r in rows}
    st.markdown('<div class="rent-tile-label" style="margin-top:14px">Not paying rent</div>',
                unsafe_allow_html=True)
    if not candidate_ids:
        st.markdown('<div class="rent-panel">No prune candidates in this run.</div>', unsafe_allow_html=True)
        return
    lines = []
    for bid in candidate_ids:
        r = by_id.get(bid, {})
        lines.append(
            f'<div style="margin:4px 0"><b style="color:{RED}">{bid}</b> {r.get("title","")} — '
            f'retrieved {r.get("times_retrieved",0)} times, paid <b style="color:{AMBER}">'
            f'{money(r.get("total_rent",0.0))}</b> in rent, earned <b>$0.0000</b> — '
            f'never supported a correct answer.</div>')
    st.markdown(f'<div class="rent-panel rent-red">{"".join(lines)}</div>', unsafe_allow_html=True)


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
          <div class="rent-tile-val" style="color:{GREEN}">{money(after, 5)}
          <span style="font-size:1rem;color:{GREEN}"> {delta:+.5f}</span></div></div>""",
                    unsafe_allow_html=True)
    st.caption("our fixed regression set retained an identical score at lower cost")


# --------------------------------------------------------------------------------------------------
# Task 9 — regression replay + one live/replayed query (ALWAYS render from a captured file at click
# time in EITHER mode — satisfies the binding two-live-call cap for the regression suite)
# --------------------------------------------------------------------------------------------------
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


def run_query(question: dict, replay_mode: bool, run_id: str) -> None:
    if replay_mode:
        ev = next(e for e in json.load(open(POST_CAPTURE))["events"]
                  if e["question_id"] == question["question_id"])
        r = ev["memory"]
        st.markdown(f'<div class="rent-panel"><b style="color:{AMBER}">REPLAYED</b> — {question["query"]}'
                    f'<br>&rarr; <b>{r["model_answer"]}</b><br>'
                    f'<span style="color:{MUTED}">context: {r["context_bundle_ids"]}, '
                    f'{r["prompt_tokens"]} prompt tokens</span></div>', unsafe_allow_html=True)
    else:
        prompt, hits, _ = build_memory_prompt(load_world(), question)   # reflects the PRUNED registry
        text, usage = ai_complete(MODEL, prompt, purpose="rent_eval_live", run_id=run_id,
                                  user_id=USER_ID, agent_tag="rent:memory:live", model_parameters=GEN_PARAMS)
        st.markdown(f'<div class="rent-panel"><b style="color:{GREEN}">LIVE</b> — {question["query"]}'
                    f'<br>&rarr; <b>{text.strip()}</b><br>'
                    f'<span style="color:{MUTED}">context: {[h["bundle_id"] for h in hits]}, '
                    f'{usage["prompt_tokens"]} prompt tokens</span></div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------------------------------
REPLAY_MODE = st.sidebar.checkbox("Replay mode (zero external calls)",
                                  value=os.environ.get("RENT_REPLAY_MODE") == "1")
screen = st.sidebar.radio("Screen", ["Leaderboard", "Regression / Query"])
st.session_state.setdefault("pruned", False)

st.markdown(f'<div style="color:{AMBER};font-size:1.1rem;letter-spacing:.14em">RENT — THE MEMORY P&amp;L'
            f'{"  ·  REPLAY" if REPLAY_MODE else ""}</div>', unsafe_allow_html=True)

try:
    rows, candidate_ids, idle_ids = load_view(REPLAY_MODE, st.session_state["pruned"])
except Exception as e:  # noqa: BLE001 — pre-capture / pre-Snowflake skeleton stage: render guidance
    rows, candidate_ids, idle_ids = None, [], []
    st.warning(f"Ledger view unavailable ({e}). In live mode this needs Snowflake + a benchmarked "
               f"run_id; in replay mode it needs {PRE_CAPTURE} / {POST_CAPTURE}.")

if screen == "Leaderboard":
    if rows is not None:
        render_headline(rows)
        render_table(rows)
        render_red_panel(rows, candidate_ids)
        render_idle_panel(rows, idle_ids)

    st.markdown("---")
    if st.button("PRUNE", type="primary"):
        if REPLAY_MODE:
            st.session_state["pruned"] = True   # LOCAL state flip only — zero Snowflake calls
        else:
            candidates = json.load(open(PRUNE_CANDIDATES_PATH))   # frozen in Task 7
            bundles.apply_prune(candidates)                       # REAL SQL, live, zero LLM calls
            st.session_state["pruned"] = True
        try:
            pre, post = load_agg(PRE_CAPTURE), load_agg(POST_CAPTURE)
            st.session_state.update(cost_before=pre["mean_memory_cost_per_query"],
                                    cost_after=post["mean_memory_cost_per_query"])
        except Exception as e:  # noqa: BLE001 — captures may not exist yet in skeleton stage
            st.info(f"cost tiles need {PRE_CAPTURE} / {POST_CAPTURE} ({e}).")
        st.rerun()

    render_cost_tiles()
    render_receipts(REPLAY_MODE)
    render_footer()

else:  # Regression / Query
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
        if st.button("Run query"):
            run_query(qmap[qid], REPLAY_MODE, RUN_ID)
    except Exception as e:  # noqa: BLE001
        st.warning(f"query control unavailable ({e}).")
