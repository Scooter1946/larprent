"""bundles.py — TRUE no-backfill retrieval + prune primitives (Task 4, Lane B cross-lane assist).

True no-backfill: freeze the first top_k UNIQUE bundle_ids by rank — active or not — BEFORE looking
at `active` status at all. Only after that freeze do we drop any frozen seat whose bundle is
inactive; a dropped seat stays EMPTY. Ranks beyond the freeze point are never consulted, so nothing
downstream can ever fill a pruned seat (the deterministic check in Task 4 Part B proves rank 7 never
enters a top-6 window after the rank-1 bundle is pruned).
"""
import mem
from snow import get_conn

TOP_K_DEFAULT, OVERFETCH_PAD = 6, 4   # pad only absorbs duplicate episodes of the SAME session; never a backfill source


def get_session_to_bundle_map() -> dict[str, dict]:
    """{session_id: {'bundle_id': str, 'active': bool}} — fresh 12-row read, cheap."""
    cur = get_conn().cursor()
    cur.execute("SELECT session_id, bundle_id, active FROM bundle_registry")
    return {r[0]: {"bundle_id": r[1], "active": r[2]} for r in cur.fetchall()}


def recall_bundles(query: str, user_id: str, top_k: int = TOP_K_DEFAULT) -> list[dict]:
    hits = mem.recall(query, user_id=user_id, top_k=top_k + OVERFETCH_PAD)   # list[dict], already normalized by mem.py's adapter
    reg = get_session_to_bundle_map()
    seen, frozen_seats = set(), []
    for rank, ep in enumerate(hits, start=1):
        info = reg.get(ep["session_id"])
        if info is None or info["bundle_id"] in seen:
            continue
        seen.add(info["bundle_id"])
        frozen_seats.append({"bundle_id": info["bundle_id"], "score": ep["score"], "rank": rank,
                             "active": info["active"]})
        if len(frozen_seats) == top_k:
            break   # SEATS FROZEN HERE — ranks beyond this point are never read, ever
    return [s for s in frozen_seats if s.pop("active")]   # drop inactive seats, no replacement


def apply_prune(bundle_ids: list[str]) -> None:
    """Real, live SQL. Zero LLM calls. Zero EverOS delete calls — application-level demotion only."""
    conn = get_conn(); cur = conn.cursor()
    cur.executemany("UPDATE bundle_registry SET active=FALSE, pruned_ts=CURRENT_TIMESTAMP() "
                    "WHERE bundle_id = %s", [(b,) for b in bundle_ids])
    conn.commit()


def reset_active_all() -> None:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("UPDATE bundle_registry SET active=TRUE, pruned_ts=NULL")
    conn.commit()
