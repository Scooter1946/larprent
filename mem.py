"""mem.py — the ONE module through which all EverOS Cloud access happens (Phase 0, Lane B).

Binding conventions honored here (SHARED-CONTRACT items 12/14, PLAN-rent Phase 0 step 6):
  * A single EverOS client with a FIXED scope (app_id="rent", project_id="rent") is reused for
    every call. `EverOS._scope(None, None)` falls back to the client's construction-time scope,
    so as long as no function below passes app_id/project_id, every add/flush/search/delete shares
    one scope — mixed scopes silently break add->flush->search round trips.
  * `_normalize_episode` is the ONE adapter that turns a typed SDK episode into a plain dict, so
    every caller downstream (bundles.py, seed.py) works with dicts and indexes ep["session_id"] /
    ep["score"], never the raw SDK attributes.

Deviations from the plan sketch, made deliberately and disclosed:
  1. The client is a lazily-constructed module singleton (via `_get_client()`), not built at import
     time. This preserves the plan's "constructed ONCE, one fixed scope, reused everywhere"
     invariant while letting `import mem` (and therefore `import bundles`, Task 4 acceptance Part A)
     succeed without EVEROS_API_KEY set — the key is only needed to actually talk to EverOS.
  2. The plan sketch reads `ep.content`, but the real everos-cloud==1.0.0 `SearchEpisodeItem` has
     NO `content` field — its text lives in `.episode` (full text) / `.summary`. Reading
     `ep.content` would AttributeError on every recall and break the entire retrieval path. Per the
     escalation rules ("an API contradicts the research briefs") the fix belongs in this one
     adapter, which is exactly where the contract says the real SDK shape gets normalized. Nothing
     downstream consumes ep["content"] (bundles/benchmark format prompt text from the fixture file),
     so this only affects the adapter itself.
"""
import os

from everos_cloud import EverOS

APP_ID = "rent"
PROJECT_ID = "rent"

_client = None


def _get_client() -> EverOS:
    """Construct the single fixed-scope EverOS client once, then reuse it for every call."""
    global _client
    if _client is None:
        _client = EverOS(api_key=os.environ["EVEROS_API_KEY"], app_id=APP_ID, project_id=PROJECT_ID)
    return _client


def _normalize_episode(ep) -> dict:
    """The ONE adapter: typed SDK episode -> plain dict, and the single place we verify that a result
    actually originates from a session. `content` is sourced from the real SDK text fields
    (`episode`, then `summary`) because SearchEpisodeItem has no `content` attribute."""
    session_id = getattr(ep, "session_id", None)
    assert session_id, "episode missing originating-session field"
    content = getattr(ep, "episode", None) or getattr(ep, "summary", None) or ""
    return {"session_id": session_id, "score": getattr(ep, "score", None), "content": content}


def remember(session_id: str, messages: list[dict]) -> None:
    """add(async_mode=False) ALWAYS immediately followed by flush() — never skip flush.
    DRY-RUN FINDING (2026-08-07, verified live): EverOS extraction DECLINES single terse messages
    (flush returns status='no_extraction'); it extracts reliably only from multi-turn conversations
    (status='extracted', retrievable ~2s later). Callers must pass a conversation — see
    seed.wrap_conversation(). Also: what's stored is a SUMMARY REWRITE, not verbatim text —
    retrieval matches against the summary."""
    client = _get_client()
    client.add(session_id, messages, async_mode=False)
    client.flush(session_id)


def recall(query: str, user_id: str, top_k: int = 10, min_score: float | None = None,
           method: str = "keyword") -> list[dict]:
    """Hybrid search scoped to a user; returns normalized dicts (NOT the raw SearchData). `min_score`,
    when not None, is a calibration gate passed through to search() (EverOS v2 search supports
    min_score)."""
    kwargs = {"top_k": top_k, "method": method}   # keyword default: vector/hybrid index drops embeddings (verified live 2026-08-07)
    if min_score is not None:
        kwargs["min_score"] = min_score
    result = _get_client().search(query, user_id=user_id, **kwargs)
    return [_normalize_episode(ep) for ep in result.episodes]


def delete(user_id: str, session_id: str) -> None:
    """Scoped soft-delete pass-through — used by seed.py for idempotent reseeding. EverOS has no
    per-memory-ID delete; this is a user/session-scoped soft delete only."""
    _get_client().delete(user_id=user_id, session_id=session_id)
