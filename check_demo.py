"""check_demo.py — single end-to-end demo gate (Task 10, Lane B).

Checks BOTH capture files (still 8/8 both arms, both phases; post-prune cheaper) AND that show1's
live Snowflake rows exist AND that the registry is staged for a REAL demo transition (B09/B10
currently active=TRUE, i.e. `python seed.py --restore-active` has already run). Run right before the
15:40 buffer, never followed by a destructive reset.
"""
from dotenv import load_dotenv; load_dotenv()

import json

from rent_fixtures import load_world
from snow import get_conn


def main():
    world = load_world()
    assert len(world["bundles"]) == 12 and len(world["questions"]) == 8
    pre = json.load(open("captures/replay_pre_prune.json"))
    post = json.load(open("captures/replay_post_prune.json"))
    for cap, name in ((pre, "pre"), (post, "post")):
        assert sum(e["naive"]["is_correct"] for e in cap["events"]) == 8, f"{name}: naive arm not 8/8"
        assert sum(e["memory"]["is_correct"] for e in cap["events"]) == 8, f"{name}: memory arm not 8/8"
    pre_mean = sum(e["memory"]["prompt_tokens"] for e in pre["events"]) / 8
    post_mean = sum(e["memory"]["prompt_tokens"] for e in post["events"]) / 8
    assert post_mean < pre_mean, "post-prune cost/query did not decrease"
    assert set(json.load(open("captures/prune_candidates.json"))) == {"B09", "B10"}
    cur = get_conn().cursor()
    cur.execute("SELECT COUNT(*) FROM rent_ledger WHERE run_id='show1'")
    assert cur.fetchone()[0] > 0, "show1 rows missing from Snowflake — was a destructive reset run after capture?"
    cur.execute("SELECT active FROM bundle_registry WHERE bundle_id IN ('B09','B10')")
    # bool(): SQLite returns 1 where Snowflake returns True — same truth, different dialect
    assert all(bool(r[0]) for r in cur.fetchall()), \
        "B09/B10 are not active — run `python seed.py --restore-active` (Task 7) so the live PRUNE click has a real transition to perform, then rerun this check"
    print(f"check_demo OK: pre_mean={pre_mean:.1f} tok, post_mean={post_mean:.1f} tok, show1 rows verified live, B09/B10 staged ACTIVE")


if __name__ == "__main__":
    main()
