"""seed.py — idempotent EverOS + registry seeding (Lane A, Task 5).

Depends on Task 1 (fixture content) + Task 4 (bundles.reset_active_all). Each bundle becomes
one EverOS session under user_id="acme:support"; a Snowflake bundle_registry row maps
session_id <-> bundle_id and holds the only mutable state (active).

  python seed.py                 full seed (MERGE registry rows, seed support map, all active)
  python seed.py --reset         clear the 4 result/log tables (NOT bundle_registry) then re-seed
  python seed.py --restore-active flip bundle_registry.active back to TRUE for all 12 — nothing else
"""
from dotenv import load_dotenv; load_dotenv()
import sys
import mem
from bundles import reset_active_all
from rent_fixtures import load_world
from snow import get_conn


def upsert_registry_row(bundle: dict, session_id: str) -> None:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""MERGE INTO bundle_registry t USING (SELECT %(bid)s AS bundle_id) s
        ON t.bundle_id = s.bundle_id
        WHEN MATCHED THEN UPDATE SET session_id=%(sid)s, title=%(title)s, category=%(cat)s, is_idle=%(idle)s
        WHEN NOT MATCHED THEN INSERT (bundle_id, session_id, title, category, is_idle)
          VALUES (%(bid)s,%(sid)s,%(title)s,%(cat)s,%(idle)s)""",
        {"bid": bundle["bundle_id"], "sid": session_id, "title": bundle["title"],
         "cat": bundle["category"], "idle": bundle["is_idle"]})
    conn.commit()


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
    if "--restore-active" in sys.argv:
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
