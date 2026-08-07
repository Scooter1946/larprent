# EverOS (EverMind) — Hackathon Integration Brief

**Product confirmed real and found.** This is `EverMind-AI/EverOS` on GitHub — "the
open-source memory layer for AI agents," matching the hackathon's description exactly.
Do NOT confuse it with: (1) "Evermind" health-tech wearables, (2) `@evermind-sh/sdk`
on npm — an unrelated distributed-locking SaaS also called "Evermind", (3)
`docs.everos.dev` / "EVER SDK" — an Everscale/TON **blockchain** SDK, totally
unrelated despite the near-identical name. Use only these canonical sources:
github.com/EverMind-AI/EverOS, pypi.org/project/everos, pypi.org/project/everos-cloud,
evermind.ai, docs.evermind.ai.

Repo stats (as of 2026-08-07): 11.8k stars, 883 forks, 70 open issues, created
2025-10-28, **pushed today** — very active but also very young (~9 months old) and
churning fast. Latest `everos` PyPI release (1.2.2) shipped 3 days ago.

## Two ways to use it — pick ONE for the hackathon

| | Self-hosted OSS (`pip install everos`) | Managed Cloud (`pip install everos-cloud`) |
|---|---|---|
| Runs where | Your laptop, as a local HTTP server | evermind.ai's servers |
| Needs API key? | No key to **run** the demo; needs LLM+embedding+rerank keys for **real** memory extraction | Yes — one EverOS API key from console (everos.evermind.ai) |
| Storage | Local Markdown + SQLite + LanceDB (no external DB) | Fully managed |
| Best for hackathon | Full control, works offline once configured, but more setup steps | **Fastest path to a working demo** — one API key, no server to babysit |

**Recommendation for a 5-hour hackathon, 1-hour integration budget: use `everos-cloud`.**
Skip running your own server unless you specifically want to show off the
Markdown-files-as-memory / local-first story.

## Install

```bash
# Cloud SDK (recommended for hackathon speed)
pip install everos-cloud

# OR self-hosted OSS
pip install everos            # Python 3.12+ required
uv pip install everos          # or via uv
uv pip install 'everos[multimodal]'   # optional: PDFs/images/audio ingestion
```

No official JS/TS SDK from EverMind itself yet (a community `pi-everos-memory`
npm package exists — thin REST wrapper, not officially maintained; the self-hosted
server is a plain REST API so any language can call it with `curl`/`fetch`).

## Core API — Cloud SDK (fastest path)

```python
from everos_cloud import EverOS

client = EverOS(api_key="sk-...")   # get key at https://everos.evermind.ai

# Store a memory (async by default — extraction happens in background)
client.add(session_id="session-1", messages=[
    {"sender_id": "user-1", "role": "user", "content": "I love hiking in the mountains"},
])

# Force extraction now instead of waiting for a topic shift (good for demos)
client.flush("session-1")

# Search / retrieve memory, scoped to a user
result = client.search("outdoor hobbies", user_id="user-1", top_k=10,
                        include_profile=True)
print(result.episodes)

# List memories by type: episode | profile | agent_case | agent_skill
page = client.get("episode", user_id="user-1", page=1, page_size=20)

# Edit a user's profile directly (structured facts, not raw chat)
client.edit("user-1", operations=[
    {"action": "add", "type": "explicit_info",
     "data": {"category": "hobby", "description": "Enjoys hiking in the mountains"},
     "reason": "Stated in session-1"},
])

client.delete(user_id="user-1", session_id="session-1")   # scoped soft-delete
```

`search()` supports `method`: `keyword | vector | hybrid (default) | agentic`.
Every call raises `EverOSError` on failure. Use `with EverOS(api_key=...) as client:`
for clean connection handling.

## Core API — Self-hosted OSS (REST, no SDK)

```bash
everos init                 # writes everos.toml — fill in LLM/embedding/rerank keys
everos server start         # runs on http://127.0.0.1:8000

curl -X POST http://127.0.0.1:8000/api/v2/memory/add -H 'Content-Type: application/json' -d '{
  "session_id": "demo-001", "app_id": "default", "project_id": "default",
  "messages": [{"sender_id": "alice", "role": "user", "timestamp": 1700000000000,
                "content": "I love climbing in Yosemite every spring."}]
}'

curl -X POST http://127.0.0.1:8000/api/v2/memory/flush -d '{"session_id":"demo-001"}'

curl -X POST http://127.0.0.1:8000/api/v2/memory/search -H 'Content-Type: application/json' -d '{
  "user_id": "alice", "app_id": "default", "project_id": "default",
  "query": "Where do I like to climb?", "top_k": 5
}'
```

`everos demo` runs a **zero-config terminal visualizer** with no keys and no
server — good for a 2-minute "here's the concept" pitch but not real memory.
`everos demo --live` hits your real running server.

## Scoping model (multi-user / multi-agent from day one)

Every add/search call scopes orthogonally by up to 5 dimensions:
`user_id`, `agent_id`, `app_id`, `project_id`, `session_id`. That's your
per-user personalization and per-conversation isolation, built in — no need
to hand-roll a namespace scheme. Memory is split into two tracks: **user-side**
(episodes, profile, facts) and **agent-side** (cases → distilled into reusable
skills — the "agent learns from experience" story).

## LLM-provider agnosticism

Fully provider-agnostic via OpenAI-compatible endpoints. Self-hosted config
(`everos.toml`) needs THREE separate provider slots — chat/LLM, embedding,
rerank — each independently pointed at any OpenAI-protocol-compatible base URL:

```toml
[llm]
model = "gpt-4.1-mini"
base_url = "https://openrouter.ai/api/v1"   # or OpenAI, vLLM, Ollama, DeepInfra...
api_key = "sk-..."

[embedding]
model = "Qwen/Qwen3-Embedding-4B"
base_url = "https://api.deepinfra.com/v1/openai"
api_key = "..."

[rerank]
provider = "deepinfra"
model = "Qwen/Qwen3-Reranker-4B"
```

Default docs steer you toward **OpenRouter** (LLM+multimodal) + **DeepInfra**
(embedding+rerank) — that's TWO separate signups if you self-host for real,
on top of whatever LLM key your own agent uses. Anthropic/Claude works fine
as the `[llm]` provider via any OpenAI-compatible proxy, but isn't a first-class
default. The Cloud SDK sidesteps all of this — one EverOS key, EverMind runs
the LLM/embedding pipeline for you.

## Latency & quality (vendor-reported — treat as marketing, not measured)

- Claimed "sub-500ms p95 retrieval latency"
- Benchmarks: LoCoMo 93.05%, LongMemEval 83.00%, HaluMem 93.04% — cited in
  EverMind's own blog, which (unsurprisingly) ranks EverOS #1 against Mem0,
  Letta, and Graphiti/Zep. Mem0 and Graphiti post comparable or higher numbers
  on some of the same benchmarks (e.g. Mem0 94.8 LongMemEval vs EverOS 83.0) —
  don't repeat EverOS's "best" claim uncritically in your pitch.
- An open GitHub issue notes dense vector recall is currently "a full scan"
  (81ms → 2.2ms after an unmerged indexing fix) — self-hosted search perf may
  vary release to release right now.

## What a memory layer unlocks in a few hackathon hours

1. **Cross-session personalization** — user says something in session 1,
   agent recalls it unprompted in session 3 tomorrow. This is the single most
   demo-able moment: show a fresh chat window "just knowing" a fact.
2. **Agent that learns you over time** — profile fields (`explicit_info`,
   `implicit_traits`) accumulate; show a profile view growing across a live
   multi-turn demo.
3. **Context compression** — instead of stuffing full chat history into every
   prompt, call `search()` for the top-k relevant memories and inject only
   those. Great for a "before/after token count" slide (fewer tokens per call,
   same or better answer quality).
4. **Agent skill learning** — repeated task patterns become reusable "Skills"
   (self-hosted OSS feature: Cases → Distillation). Neat but likely too slow
   to observably trigger in a few hours; mention it, don't rely on demoing it live.
5. **Memory analytics** — `get()`/list endpoints expose stored episodes/profile
   directly; a simple dashboard panel showing "what the agent remembers about you"
   is a cheap, high-impact UI addition.

## Gotchas / setup-time risks

- **Two separate packages, easy to grab the wrong one**: `everos` (self-hosted
  server) vs `everos-cloud` (managed API client). They are not interchangeable
  and have different quickstarts — decide up front which one your team is using.
- **Self-hosted needs 3 provider keys minimum** (LLM, embedding, rerank) before
  you get real (non-demo) results — budget 10-15 min for signups if you go
  this route. Cloud SDK needs exactly one key.
- **`everos server start` needs a raised file-descriptor `ulimit`** on macOS
  (default 256, they recommend 4096+) — a slightly obscure fix (`ulimit -n 4096`
  in the same shell before starting) that will bite anyone who skips the README.
- **Multimodal ingestion needs LibreOffice installed system-wide** for Office
  doc parsing (`brew install --cask libreoffice`) — skip multimodal features
  entirely unless you actually need them; office uploads just 415 without it
  (PDF/image/audio still work).
- **Young, fast-moving repo**: 70 open issues at time of writing, including a
  reported bug where write failures are silently reported as success, and a
  reported non-English (Chinese) query bug — sample size of one team's few
  hours is enough to hit an edge case. Have a fallback plan (e.g. keep raw
  chat history around) if memory extraction silently no-ops.
- **Docs quality**: README/QUICKSTART are genuinely good and copy-pasteable
  (verified above). API reference site (docs.evermind.ai) is thinner and some
  pages 404/redirect — expect to lean on the GitHub README and the
  `everos-cloud-sdk-python` repo's `quickstart.md` more than the docs site.
- **No first-party JS/TS SDK** — if your team is JS-only, you're calling the
  self-hosted REST API directly (fine, just no typed client) or using an
  unofficial community npm package at your own risk.
- **Async by default**: `client.add()` on the Cloud SDK enqueues extraction in
  the background (returns 202) — searching immediately after adding may return
  nothing yet. Call `client.flush(session_id)` right after `add()` in demos to
  force synchronous extraction, or your live demo will look broken.

## Suggested 60-minute integration plan for a 2-person team

1. (5 min) One person signs up at everos.evermind.ai, grabs API key.
2. (10 min) `pip install everos-cloud`, run the 6-line quickstart snippet above
   against your own agent's user turns — confirm add → flush → search round-trip.
3. (15 min) Wire `client.add()` into your chat loop after each user turn;
   wire `client.search(query, user_id=...)` into your prompt-construction step,
   replacing/augmenting full chat history with retrieved memories.
4. (15 min) Add a minimal "memory panel" in the UI calling `client.get("episode",
   user_id=...)` / `client.get("profile", ...)` so judges can see the agent's
   memory growing — this is your demo's money shot.
5. (15 min) Buffer for the async-extraction gotcha, scoping bugs, and a
   pre-loaded seed conversation so the demo doesn't rely on live extraction timing.

---
Sources: github.com/EverMind-AI/EverOS (README, QUICKSTART.md, GitHub API repo
metadata/issues), pypi.org/project/everos, pypi.org/project/everos-cloud,
github.com/EverMind-AI/everos-cloud-sdk-python/blob/v1/quickstart.md,
evermind.ai, docs.evermind.ai, marktechpost.com (2026-06-29 EverOS architecture
writeup), evermind.ai/blogs/best-open-source-agent-memory-frameworks-2026.
