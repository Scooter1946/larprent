"""seed.py — idempotent EverOS + registry seeding (Lane A, Task 5).

Depends on Task 1 (fixture content) + Task 4 (bundles.reset_active_all). Each bundle becomes
one EverOS session under user_id="acme:support"; a Snowflake bundle_registry row maps
session_id <-> bundle_id and holds the only mutable state (active).

  python seed.py                 full seed (MERGE registry rows, seed support map, all active)
  python seed.py --reset         clear the 3 result/log tables (llm_call_log is intentionally
                                  retained — it is the cost-telemetry record) (NOT bundle_registry)
                                  then re-seed
  python seed.py --restore-active flip bundle_registry.active back to TRUE for all 12 — nothing else
"""
from dotenv import load_dotenv; load_dotenv()
import sys
import mem
from bundles import reset_active_all
from rent_fixtures import load_world
from snow import get_conn

# Pre-fed fallback fact (Lane B lifecycle beat §4): fed via `python seed.py --prefeed` during pre-show
# prep so the on-stage demo NEVER depends on live extraction. If the live feed stalls, the presenter
# pivots to this memory with the fallback line.
PREFEED_FACT = "Initech signed 2026-08-01; we promised them a 99.99% uptime SLA"
PREFEED_SESSION = "prefed-initech"


def upsert_registry_row(bundle: dict, session_id: str) -> None:
    import snow
    conn = get_conn(); cur = conn.cursor()
    params = {"bid": bundle["bundle_id"], "sid": session_id, "title": bundle["title"],
              "cat": bundle["category"], "idle": bundle["is_idle"]}
    if snow.BACKEND == "local":   # SQLite has no MERGE; same semantics via upsert
        cur.execute("""INSERT INTO bundle_registry (bundle_id, session_id, title, category, is_idle)
            VALUES (%(bid)s,%(sid)s,%(title)s,%(cat)s,%(idle)s)
            ON CONFLICT(bundle_id) DO UPDATE SET session_id=excluded.session_id, title=excluded.title,
              category=excluded.category, is_idle=excluded.is_idle""", params)
    else:
        cur.execute("""MERGE INTO bundle_registry t USING (SELECT %(bid)s AS bundle_id) s
            ON t.bundle_id = s.bundle_id
            WHEN MATCHED THEN UPDATE SET session_id=%(sid)s, title=%(title)s, category=%(cat)s, is_idle=%(idle)s
            WHEN NOT MATCHED THEN INSERT (bundle_id, session_id, title, category, is_idle)
              VALUES (%(bid)s,%(sid)s,%(title)s,%(cat)s,%(idle)s)""", params)
    conn.commit()


def _next_bundle_id() -> str:
    """Next free B## id (B13, B14, ...) beyond whatever bundle_registry already holds."""
    cur = get_conn().cursor()
    cur.execute("SELECT bundle_id FROM bundle_registry")
    nums = []
    for (bid,) in cur.fetchall():
        if bid and bid[0] in ("B", "b"):
            try:
                nums.append(int(bid[1:]))
            except ValueError:
                pass
    return f"B{(max(nums) + 1) if nums else 1:02d}"


def upsert_live_bundle(session_id: str, title: str) -> str:
    """Register a live-fed memory as a NEW bundle (category 'live_memory', active, non-idle). Used by
    app.py's feed box and by --prefeed. Idempotent per session_id: reuses the existing bundle_id if
    this session is already registered, else auto-assigns the next free B## (B13, B14, ...). Returns
    the assigned bundle_id."""
    cur = get_conn().cursor()
    cur.execute("SELECT bundle_id FROM bundle_registry WHERE session_id=%s", (session_id,))
    row = cur.fetchone()
    bundle_id = row[0] if row else _next_bundle_id()
    upsert_registry_row({"bundle_id": bundle_id, "title": title, "category": "live_memory",
                         "is_idle": False}, session_id)
    return bundle_id


def seed_bundle(bundle: dict, user_id: str) -> None:
    session_id = f"acme-bundle-{bundle['bundle_id']}"
    try:
        mem.delete(user_id=user_id, session_id=session_id)   # scoped soft-delete — makes reseeding idempotent
    except Exception:
        pass   # first run: nothing to delete yet, ignore
    mem.remember(session_id=session_id,
                 messages=[{"sender_id": user_id, "role": "user", "content": bundle["content"]}])
    episodes = mem.recall(bundle["title"], user_id=user_id, top_k=12)   # list[dict] — Phase 0 adapter
    if not any(ep["session_id"] == session_id for ep in episodes):
        raise RuntimeError(f"seed verify FAILED for {bundle['bundle_id']}: not retrievable after flush")
    upsert_registry_row(bundle, session_id)


def reseed_bundle(bundle_id: str) -> None:
    """Calibration hook (Task 7): after editing rent_world.json, reseed ONLY the changed bundle —
    scoped delete + re-add — never reuse stale indexed text."""
    world = load_world()
    b = next(x for x in world["bundles"] if x["bundle_id"] == bundle_id)
    seed_bundle(b, world["user_id"])


def prefeed(force: bool = False) -> str:
    """--prefeed: feed one KNOWN fact through the exact same remember -> verify -> register path the
    live feed box uses, so the on-stage demo never depends on live extraction. Returns the assigned
    bundle_id. Idempotent (scoped delete + re-add, reused session_id).

    ORDERING GUARD: must run AFTER the show1 capture (reset_prune.py). The Initech fact's
    "99.99% uptime SLA" is semantically adjacent to Q5's Northwind SLA — if it sits in EverOS scope
    during the benchmark it can seat in Q5's context with a CONFLICTING number, breaking the
    calibration matrix and possibly the 8/8. Isolation is real only if the ordering is."""
    import os as _os
    if not _os.path.exists("captures/replay_post_prune.json") and not force:
        raise SystemExit("prefeed BLOCKED: captures/replay_post_prune.json not found — run the "
                         "show1 capture (reset_prune.py) BEFORE prefeeding, or pass --force if you "
                         "know exactly why the ordering doesn't apply (e.g. throwaway rehearsal).")
    world = load_world()
    user_id = world["user_id"]
    try:
        mem.delete(user_id=user_id, session_id=PREFEED_SESSION)   # idempotent re-prefeed
    except Exception:
        pass
    mem.remember(session_id=PREFEED_SESSION,
                 messages=[{"sender_id": user_id, "role": "user", "content": PREFEED_FACT}])
    episodes = mem.recall(PREFEED_FACT, user_id=user_id, top_k=12)
    if not any(ep["session_id"] == PREFEED_SESSION for ep in episodes):
        raise RuntimeError("prefeed verify FAILED: Initech memory not retrievable after flush")
    bundle_id = upsert_live_bundle(PREFEED_SESSION, "Initech SLA (pre-fed)")
    print(f"prefeed OK: {bundle_id} <- session {PREFEED_SESSION} ('{PREFEED_FACT}')")
    return bundle_id


def seed_support_map(world: dict) -> None:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM fixture_support_map")   # idempotent: clear before repopulating
    for q in world["questions"]:
        for bid in q["supporting_bundle_ids"]:
            cur.execute("INSERT INTO fixture_support_map (question_id, bundle_id) VALUES (%s,%s)",
                        (q["question_id"], bid))
    conn.commit()


def main():
    world = load_world()
    for b in world["bundles"]:
        seed_bundle(b, world["user_id"])
    seed_support_map(world)
    reset_active_all()   # every fresh seed starts with all 12 active
    print(f"seeded {len(world['bundles'])} bundles, {len(world['questions'])} support rows")


if __name__ == "__main__":
    if "--prefeed" in sys.argv:
        prefeed(force="--force" in sys.argv)   # AFTER reset_prune only (ordering guard inside)
    elif "--restore-active" in sys.argv:
        reset_active_all()   # ONLY the active flag — EverOS content, show1 captures, and ledger rows untouched
        print("bundle_registry: all 12 bundles restored to active=TRUE (show1's captures/ledger rows untouched)")
    elif "--reset" in sys.argv:
        conn = get_conn(); cur = conn.cursor()
        for t in ("eval_results", "retrieval_log", "rent_ledger"):
            cur.execute(f"DELETE FROM {t}")
        conn.commit()
        main()
    else:
        main()
