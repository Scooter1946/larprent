"""rent_fixtures.py — fixture loader + answer normalizer (Lane A, Task 1)."""
import json, re

USER_ID = "acme:support"


def load_world(path: str = "fixtures/rent_world.json") -> dict:
    with open(path) as f:
        return json.load(f)


def normalize(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s).replace(",", "")
    s = re.sub(r"\$\s+", "$", s)
    s = re.sub(r"\s+%", "%", s)
    return s.rstrip(".!;: ")   # real models end sentences; graders shouldn't care
