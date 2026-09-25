# Maintainer Agent — Feature Checklist

A tiny-feature build sequence mapped to the 12-Week Roadmap v3.

**Workflow for every feature:** implement → see it work → write one test → commit. One commit per feature.

**Current position:** 1.1 and 1.2 complete. Next action: **1.3 — Settings module**.

---

## Corrections made to the original PRD sequence

Keep these in mind; they are already applied below.

- **No FastAPI app step existed.** The old 2.1 added `/db-health` and 5.1 tested `/health`, but nothing created the app or `/health`. Now it's 2.2.
- **Postgres arrived too late.** The old 2.1 needed Postgres, but Docker didn't appear until step 6. Postgres now starts at 2.1.
- **Alembic came after the tables.** Creating tables directly and then "autogenerating" migrations produces empty or conflicting migrations. Alembic is now set up before the first model, and every table is created through a migration.
- **Tests were batched at the end.** Each test now sits next to its feature.
- **SQLite test DB was a trap.** JSONB and pgvector don't work there. Use a separate Postgres test database.
- **GitHub's `/issues` endpoint also returns PRs.** Skip items with a `pull_request` key or issue counts will be wrong.
- **The loader would duplicate rows.** Unique constraints + upserts added.
- **Missing Week 1–3 roadmap topics added:** generators, context managers, Pydantic models, dependency injection, settings module, indexes, EXPLAIN, transactions, joins.
- **CRUD was incomplete.** PATCH, DELETE, 404/409, and pagination added.
- **OAuth was missing the `state` parameter.** Added as 3.7.

---

# Phase 1 — Backend core (Weeks 1–3)

## Week 1 — Ingestion CLI

- [x] **1.1 CLI skeleton** — entrypoint (argparse or typer) accepting `--owner` and `--repo`, printing them back. No GitHub calls.
- [x] **1.2 Fetch repo metadata** — call `GET /repos/{owner}/{repo}`, print name, description, star count.
- [ ] **1.3 Settings module** — load `GITHUB_TOKEN` from `.env` with pydantic-settings. Add `.env` to `.gitignore`.
- [ ] **1.4 Auth header + rate limits** — send the token as an `Authorization` header, print `X-RateLimit-Remaining`. Watching it jump from 60 → 5000 proves auth works.
- [ ] **1.5 Reuse one client** — a single `httpx.Client` inside a `with` block (context managers).
- [ ] **1.6 Fetch page 1 of issues** — print title and number. Skip any item with a `pull_request` key.
- [ ] **1.7 Paginate with a generator** — `iter_issues()` follows the `Link` header and yields one issue at a time (generators).
- [ ] **1.8 Typed models** — convert raw dicts into `Repo` and `Issue` Pydantic models, keeping only the fields you need.
- [ ] **1.9 Fetch comments for one issue** — given an issue number, fetch and print its comments.
- [ ] **1.10 Fetch PRs and commits** — reuse the generator. Add a `--limit` flag so big repos don't burn quota.
- [ ] **1.11 Save to disk** — write to `data/{owner}_{repo}/*.json`. This is the input the DB loader reads.
- [ ] **1.12 Handle rate-limit exhaustion** — when remaining hits 0, print the reset time and exit cleanly.
- [ ] **1.13 First test** — pytest on the Link-header parser using a hardcoded string. No network.

## Week 2 — FastAPI + database

- [ ] **2.1 Postgres in compose** — `docker-compose.yml` with only a `postgres` service, pgvector-enabled image.
- [ ] **2.2 FastAPI app + `/health`** — create the app, add `GET /health`, test it with TestClient.
- [ ] **2.3 DB session + DI** — SQLAlchemy engine, a `get_db` dependency (dependency injection practice), and `GET /db-health` running `SELECT 1`.
- [ ] **2.4 Test DB fixture** — a separate `maintainer_test` Postgres database, rolled back after each test.
- [ ] **2.5 Alembic setup** — `alembic init`, read the DB URL from settings rather than hardcoding it in `alembic.ini`.
- [ ] **2.6 `repositories` model + migration** — fields: id, owner, name, description. `unique(owner, name)`. Autogenerate, then `upgrade head`.
- [ ] **2.7 Pydantic schemas** — `RepositoryCreate` and `RepositoryRead`, kept separate from the ORM model.
- [ ] **2.8 `POST /repositories`** — return 409 on duplicates.
- [ ] **2.9 `GET /repositories` and `GET /repositories/{id}`** — 404 when missing.
- [ ] **2.10 `PATCH` and `DELETE /repositories/{id}`**
- [ ] **2.11 Pagination** — `?limit=&offset=`.
- [ ] **2.12 `issues` model + migration** — FK to `repositories`; fields `github_number`, `title`, `body`, `state`, `labels` (JSONB), `created_at`; `unique(repository_id, github_number)`.
- [ ] **2.13 Rollback check** — verify `alembic downgrade -1` and `alembic upgrade head` both run cleanly.
- [ ] **2.14 Issue endpoints** — `POST` and `GET /repositories/{id}/issues`, with a `?state=open` filter.

## Week 3 — SQL, auth, Docker, CI, deploy

- [ ] **3.1 JSON loader** — read the step-1 files and insert via the models using upserts (`ON CONFLICT DO UPDATE`). First time the CLI meets the DB.
- [ ] **3.2 Transactions** — wrap the load in one transaction; test that one bad row rolls everything back.
- [ ] **3.3 Index + EXPLAIN** — add an index on `issues(repository_id, state)`, compare `EXPLAIN` output before and after.
- [ ] **3.4 Stats endpoint** — `GET /repositories/{id}/stats`: open/closed counts via JOIN + GROUP BY.
- [ ] **3.5 `issue_comments` table + loader** — you need comments as documents in Week 5.
- [ ] **3.6 Register the OAuth app** — client id/secret into settings.
- [ ] **3.7 `GET /auth/login`** — redirect to GitHub's authorize URL with a random `state` stored in a cookie.
- [ ] **3.8 `GET /auth/callback`** — verify `state`, exchange the code for a token, fetch the user profile.
- [ ] **3.9 `users` model + migration** — create-or-find by `github_id`.
- [ ] **3.10 Issue a JWT** — in an httpOnly cookie.
- [ ] **3.11 `current_user` dependency + `GET /me`**
- [ ] **3.12 Protect endpoints** — POST, PATCH, DELETE on repositories.
- [ ] **3.13 Mocked OAuth test** — test the callback with GitHub's token/user calls mocked (`respx`).
- [ ] **3.14 Dockerfile** — confirm `/health` works inside the container.
- [ ] **3.15 App in compose** — confirm `/db-health` works there.
- [ ] **3.16 Migrations on container start**
- [ ] **3.17 CI: lint** — run `ruff` on every push.
- [ ] **3.18 CI: tests** — pytest with a Postgres service container.
- [ ] **3.19 CI badge in README**
- [ ] **3.20 Deploy** — Render / Railway / Fly; confirm the public `/health` URL.
- [ ] **3.21 Managed Postgres** — pgvector-enabled; run migrations against it.
- [ ] **3.22 Auto-deploy** — only when CI passes on `main`.

**Milestone:** live URL + CI badge. Start applying.

> Week 3 is the heaviest week. If it overflows, keep OAuth minimal (3.6–3.12) and push 3.13 to Week 4.

---

# Phase 2 — Applied AI (Weeks 4–9)

*Never cut from this phase.*

## Week 4 — LLM provider abstraction

- [ ] **4.1 First LLM call** — script that calls OpenAI to summarize one issue from your DB.
- [ ] **4.2 Same with Anthropic**
- [ ] **4.3 `LLMProvider` interface** — `complete(messages) -> LLMResponse`, two implementations.
- [ ] **4.4 Pin model versions** — exact versions in settings. Never "latest" in code.
- [ ] **4.5 Log tokens + latency** — tokens in, tokens out, duration for every call.
- [ ] **4.6 Cost calculator** — driven by a price table in config.
- [ ] **4.7 `model_calls` table** — persist every call.
- [ ] **4.8 Structured output** — issue triage returning `{type, priority, summary}`, validated with Pydantic.
- [ ] **4.9 Retry with backoff** — on 429/5xx, for both the LLM client and the GitHub client.
- [ ] **4.10 Provider fallback** — if provider A fails, use provider B.
- [ ] **4.11 Prompt caching** — static system prompt first; check the cached-token count in the response.
- [ ] **4.12 Streaming** — `POST /issues/{id}/summarize/stream` over SSE.
- [ ] **4.13 `prompt_versions` table** — record the prompt version on each `model_call`.
- [ ] **4.14 Tests with a fake provider** — no network.

## Week 5 — Retrieval + context engineering

Flagship domain: **issue triage for maintainers**. Not generic chat-with-PDF.

- [ ] **5.1 Enable pgvector** — via migration.
- [ ] **5.2 Build documents** — one per issue: title + body + comments.
- [ ] **5.3 Chunker** — split by tokens with overlap. Unit test it.
- [ ] **5.4 `document_chunks` table** — `text`, `embedding`, `repository_id`, `issue_id`, `source_type`, `metadata`.
- [ ] **5.5 Embed and store one chunk**
- [ ] **5.6 Batch embed a repo** — as a CLI command.
- [ ] **5.7 Skip unchanged chunks** — content hash.
- [ ] **5.8 Top-k cosine search**
- [ ] **5.9 Metadata filters** — repo, state, source type.
- [ ] **5.10 HNSW index** — confirm `EXPLAIN` shows it's used.
- [ ] **5.11 Search endpoint** — `GET /repositories/{id}/search?q=`.
- [ ] **5.12 Token counter utility**
- [ ] **5.13 Token budgeter** — slots for system prompt, retrieved chunks, history, tool outputs; drop lowest-scoring chunks first when over budget.
- [ ] **5.14 Truncate tool outputs** — before they enter context: `…[truncated 3,200 tokens]`.
- [ ] **5.15 Log the budget breakdown** — per request. Feeds the Wk8 cost table.
- [ ] **5.16 Mini retrieval eval** — 10 queries with known correct issues, scored as hit@5.

## Week 6 — RAG + first milestone

- [ ] **6.1 `investigations` table**
- [ ] **6.2 Investigation endpoint** — `POST /repositories/{id}/investigations`: retrieve → prompt → answer.
- [ ] **6.3 Citations in the prompt** — answers must cite `[#123]`.
- [ ] **6.4 `citations` table** — parse and store them.
- [ ] **6.5 Reject invented citations** — anything not in the retrieved set.
- [ ] **6.6 "No relevant result"** — below a score threshold, answer without calling the LLM.
- [ ] **6.7 Reranking** — retrieve 20, rerank to 5, compare hit@5 against 5.16.
- [ ] **6.8 Duplicate-issue finder** — new issue text in, similar issues + reasons out. **This is the demo feature.**
- [ ] **6.9 Prompt-injection mitigation** — delimit issue text as data, validate output, test with an issue saying "ignore previous instructions."
- [ ] **6.10 Name the OWASP items** — LLM01 (Prompt Injection), LLM06 (Excessive Agency).
- [ ] **6.11 Multi-turn** — store messages so users can ask follow-ups.
- [ ] **6.12 Compaction** — when history exceeds budget, summarize older turns into a compact state block.
- [ ] **6.13 Test compaction** — confirm it triggers at the threshold.
- [ ] **6.14 Deploy + video** — 2–3 min, framed as a business problem ("maintainers lose time finding duplicates").

**Milestone:** application blitz #1. Referral outreach starts (5–10/week).

## Week 7 — Agent loop from scratch

No framework this week.

- [ ] **7.1 First tool** — `search_issues` with a JSON schema.
- [ ] **7.2 One round trip** — model calls the tool → you run it → send the result back → model answers.
- [ ] **7.3 The loop** — repeat until the model stops calling tools.
- [ ] **7.4 Max steps** — cap at ~8; return a partial answer when hit.
- [ ] **7.5 More read tools** — `get_issue`, `list_recent_commits`, `get_pr`.
- [ ] **7.6 Tool registry + allow-list** — per request.
- [ ] **7.7 Recoverable error messages** — "#999 not found; call search_issues first."
- [ ] **7.8 Validate tool args** — Pydantic; return validation errors to the model.
- [ ] **7.9 Tool timeouts**
- [ ] **7.10 `tool_calls` table** — args, result size, duration.
- [ ] **7.11 Agent state object** — messages, steps, tokens; apply the budgeter at each step.
- [ ] **7.12 Dry-run write tools** — `draft_comment`, `suggest_labels`.
- [ ] **7.13 Permission layer** — `post_comment`, `add_label`, `close_issue` pause and return a pending action; only run after `POST /investigations/{id}/confirm`.
- [ ] **7.14 Scope writes** — use the logged-in user's token; only repos they own.
- [ ] **7.15 Tests with a scripted fake model** — loop terminates, max steps enforced, confirm gate blocks.
- [ ] **7.16 Failure-modes README section** — loops, hallucinated tools, huge outputs.

## Week 8 — LangGraph + evals + observability

- [ ] **8.1 Port to LangGraph** — the same tests must still pass.
- [ ] **8.2 Confirm gate as an interrupt**
- [ ] **8.3 Router node** — classify as lookup / action / escalate.
- [ ] **8.4 Lookup sub-graph** — search tools only, small context.
- [ ] **8.5 Action sub-graph** — read + write tools, confirm gate.
- [ ] **8.6 Escalate sub-graph** — no tools; summarize for a human.
- [ ] **8.7 Graph diagram in the README**
- [ ] **8.8 Langfuse setup** — trace one run.
- [ ] **8.9 Trace everything** — every LLM and tool call; store the trace id on the investigation.
- [ ] **8.10 Build the eval set** — 30–50 cases from real traces, each with expected issue ids and expected tools.
- [ ] **8.11 Eval tables** — `evaluation_cases`, `evaluation_runs`, `evaluation_results`.
- [ ] **8.12 Eval runner CLI**
- [ ] **8.13 Deterministic checks first** — "was the correct issue cited?"
- [ ] **8.14 LLM-as-judge** — 1–5 scale with a reason.
- [ ] **8.15 Validate the judge** — hand-label 20 cases, measure agreement.
- [ ] **8.16 Trajectory scoring** — right tool chosen, steps within bound, no forbidden tool calls.
- [ ] **8.17 Model comparison table** — accuracy, p50 latency, cost.
- [ ] **8.18 Eval regression gate in CI** — ~15 cases in GitHub Actions; fail the build below threshold. Only run on PRs touching prompts or agent code, to save money.
- [ ] **8.19 Eval write-up** — your single most differentiating artifact.

## Week 9 — MCP, queue, UI

- [ ] **9.1 Read the current MCP spec** — the July 28, 2026 revision (stateless core, Tasks, MCP Apps). Not 2025 tutorials.
- [ ] **9.2 FastMCP server** — expose `search_issues`; test with MCP Inspector.
- [ ] **9.3 Remaining read tools** — connect to Claude Desktop or Claude Code.
- [ ] **9.4 Write tools with confirmation** — separate repo, own README.
- [ ] **9.5 Redis in compose**
- [ ] **9.6 RQ worker** — running a dummy job.
- [ ] **9.7 Enqueue investigations** — `POST /investigations` returns 202 + job id.
- [ ] **9.8 `GET /jobs/{id}`** — job status.
- [ ] **9.9 Idempotency keys** — same `Idempotency-Key` header returns the same job.
- [ ] **9.10 Bounded retries with backoff** — in the worker.
- [ ] **9.11 Backpressure** — max-concurrency limit; 429 when the queue is full.
- [ ] **9.12 Sync job** — `POST /repositories/{id}/sync` runs ingestion + embedding as a job. Connects Week 1 to Week 5.
- [ ] **9.13 Next.js app + login button**
- [ ] **9.14 Repo list page**
- [ ] **9.15 Chat page**
- [ ] **9.16 Stream status and tokens** — over SSE.
- [ ] **9.17 Sources panel** — links to the GitHub issues.
- [ ] **9.18 Confirm / Reject buttons** — for pending actions.
- [ ] **9.19 Deploy frontend + worker** — Vercel for the frontend.
- [ ] **9.20 Architecture note** — queue, idempotency, retries.
- [ ] **9.21 Refresh the demo video + resume v2**

**Milestone:** full showcase. Application blitz #2.

---

# Phase 3 — Depth + interviews (Weeks 10–12)

*Cut here first if time is short.*

## Week 10 — SQL on your own logs

- [ ] **10.1 Cost per investigation** — JOIN on `model_calls`.
- [ ] **10.2 Latency percentiles** — p50/p95 with `percentile_cont`.
- [ ] **10.3 Retrieval hit rate** — from your eval results.
- [ ] **10.4 Tool failure rate by tool** — ranked with a window function.
- [ ] **10.5 Daily cost** — with a running total.
- [ ] **10.6 CTE** — find runs that hit the max-step limit.
- [ ] **10.7 `EXPLAIN ANALYZE`** — on the slowest query; fix it.
- [ ] **10.8 `GET /admin/metrics`** — expose these numbers.

## Week 11 — Reps + polish

- [ ] **11.1 Two timed take-homes** — 2–3 hours each.
- [ ] **11.2 Debug a failing trace out loud** — record yourself.
- [ ] **11.3 Whiteboard the router + queue** — why a router, why a queue, what fails without idempotency.
- [ ] **11.4 Every README readable in 5 minutes**
- [ ] **11.5 One-page case study** — FDE roles weigh written communication heavily.

## Week 12 — Interviews

- [ ] **12.1 System design: your own architecture**
- [ ] **12.2 One classic** — e.g. a rate limiter.
- [ ] **12.3 STAR stories** — from real bugs you hit in this project.
- [ ] **12.4 Mock interviews**

---

## Running habits (from Week 1, not Week 12)

- [ ] AI coding tools daily — all build work in Claude Code or Cursor.
- [ ] DS&A — 5–7 LeetCode problems/week, never backloaded.
- [ ] Model landscape — ~30 min/week on frontier models and pricing tiers.
- [ ] Vocabulary discipline — name each piece as interviews name it: context engineering, harness, dynamic workflow, trajectory eval.
- [ ] Referral outreach — 5–10/week from Week 6.
- [ ] Applications — start Week 3, blitz at Weeks 6 and 9.

---

## Artifact checklist by end of Week 9

1. [ ] Live CRUD API URL with CI badge (Wk3)
2. [ ] Flagship vertical RAG + agent app, live (Wk5–9)
3. [ ] 2–3 min demo video framed as a business problem (Wk6, refreshed Wk9)
4. [ ] Eval write-up — 30–50 cases from traces, judge validation, trajectory scores, accuracy/latency/cost table (Wk8)
5. [ ] CI pipeline screenshot showing the eval regression gate (Wk8)
6. [ ] Trace/observability screenshots (Wk8)
7. [ ] Router/sub-agent graph diagram in the flagship README (Wk8)
8. [ ] MCP server repo (Wk9)
9. [ ] Queue-backed execution — architecture note + idempotency/retry code (Wk9)
10. [ ] Resume v2 + one-page case study (Wk9–11)
