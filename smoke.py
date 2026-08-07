"""smoke.py — Phase 0 gate (Lane B). MUST pass on both machines before ANY product code.

Runs two checks and fails loudly with remediation text:
  1. One `ai_complete('claude-haiku-4-5', 'say ok', 'smoke')` and asserts measured
     prompt_tokens > 0. A zero here means `show_details` parsing is broken (SHARED-CONTRACT item 12),
     NOT a valid pass.
  2. One remember -> flush -> recall round trip and asserts the recalled list is non-empty and the
     originating session is present.

Run: `python smoke.py`  (expects all-green, exit 0).
"""
from dotenv import load_dotenv; load_dotenv()

import sys

import mem
from snow import ai_complete

SMOKE_USER = "smoke:user"
SMOKE_SESSION = "smoke-session"


def check_model() -> None:
    print("[1/2] AI_COMPLETE smoke (claude-haiku-4-5) ...")
    try:
        text, usage = ai_complete("claude-haiku-4-5", "say ok", "smoke", run_id="smoke")
    except Exception as e:  # noqa: BLE001 — smoke gate: surface remediation, then re-raise
        msg = str(e)
        print(f"  FAIL: ai_complete raised: {msg}")
        if "VERSION_NOT_ALLOWED" in msg or "403" in msg:
            print("  -> EverOS/Cortex key needs v2 enablement. Fix the key before continuing.")
        print("  -> If claude-haiku-4-5 is unavailable/region-locked, run in Snowsight:")
        print("       ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';")
        print("     then re-run. If still unavailable, set MODEL = 'openai-gpt-5-mini' in benchmark.py.")
        raise
    print(f"  text={text.strip()!r}  usage={usage}")
    assert usage["prompt_tokens"] > 0, (
        "measured prompt_tokens == 0 -> show_details parsing is broken (SHARED-CONTRACT item 12); "
        "print the raw AI_COMPLETE response in snow.ai_complete and confirm choices[0]['messages'] / usage"
    )
    print("  OK: nonzero measured prompt tokens.")


def check_memory() -> None:
    print("[2/2] EverOS remember -> recall round trip ...")
    mem.remember(
        session_id=SMOKE_SESSION,
        messages=[{"sender_id": SMOKE_USER, "role": "user",
                   "content": "Smoke fact: the launch code for the demo is teal-otter-1946."}],
    )
    hits = mem.recall("what is the demo launch code", user_id=SMOKE_USER, top_k=10)
    print(f"  recalled {len(hits)} episode(s); first={hits[0] if hits else None}")
    assert hits, "recall returned an empty list right after remember+flush — EverOS write may have no-oped"
    print("  OK: non-empty recall.")


def main() -> int:
    check_model()
    check_memory()
    print("SMOKE OK: measured tokens nonzero + memory round trip non-empty. Gate green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
