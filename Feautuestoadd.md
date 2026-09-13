PRD Build Sequence — Phase 1: Backend Foundation (PRD.md §46, Weeks 1–3)

Do not build the agent yet. This phase only stands up the backend
skeleton the agent will later run on top of. Each numbered item below
is meant to be one sitting of work — implement it, see it work, then
move to the next.

Note: PRD §31 lists 15 database entities, but most of them
(document_chunks, investigations, tool_calls, model_calls, citations,
evaluation_*, prompt_versions) belong to later phases (retrieval,
agent, eval). Phase 1 only needs `users`, `repositories`, and `issues`
— the rest get created when their phase is reached, not now.

---

## 1. Repository-ingestion CLI

1.1 CLI skeleton
    A CLI entrypoint (argparse or typer) that accepts --owner and
    --repo flags and just prints them back. No GitHub calls yet.
1.2 Fetch repo metadata
    Add a GitHub API client function that calls
    GET /repos/{owner}/{repo} and prints the name, description, and
    star count.
1.3 Add auth + rate limits
    Read a GitHub personal access token from an env var, send it as
    an Authorization header, and print the rate-limit headers from
    the response so you can see the limit change.
1.4 Fetch one page of issues
    Call GET /repos/{owner}/{repo}/issues and print the title and
    number of each issue on the first page.
1.5 Paginate through all issues
    Follow the `Link` header (or `page` param) until every issue is
    fetched, not just page one.
1.6 Fetch comments for one issue
    Given an issue number, fetch and print its comments.
1.7 Fetch pull requests and commits
    Add two more client functions: list pull requests, list commits.
    Print counts for each.
1.8 Save fetched data to disk
    Instead of printing, write the fetched repo/issues/PRs/commits to
    local JSON files. This is the input the DB step below will load.

1.1 is complete. Next feature: 1.2 — Fetch repo metadata.

## 2. CRUD/backend API + database schema

2.1 DB connection only
    Add SQLAlchemy engine/session setup and a `/db-health` endpoint
    that runs `SELECT 1` against Postgres. No models yet.
2.2 `repositories` model
    Define the `repositories` table (id, owner, name, description)
    and create it directly (no Alembic yet — that's step 3).
2.3 Repository CRUD endpoints
    Add POST /repositories, GET /repositories, GET /repositories/{id}.
2.4 `issues` model
    Define the `issues` table with a foreign key to `repositories`.
2.5 Issue CRUD endpoints
    Add POST /repositories/{id}/issues and
    GET /repositories/{id}/issues.
2.6 Load step-1 JSON into the DB
    Write a small script that reads the JSON files from 1.8 and
    inserts them via the models from 2.2/2.4 — connects the ingestion
    CLI to the database for the first time.

Next feature: 2.1 — DB connection only.

## 3. Alembic migrations

3.1 Install and configure Alembic
    `alembic init`, point `sqlalchemy.url` at the app's DB URL.
3.2 First migration
    Autogenerate a migration from the `repositories` model and run
    `alembic upgrade head`.
3.3 Second migration + rollback check
    Autogenerate a migration for `issues`, then verify
    `alembic downgrade -1` and `alembic upgrade head` both work
    cleanly.

Next feature: 3.1 — Install and configure Alembic.

## 4. GitHub OAuth authentication

4.1 Register the OAuth app
    Create a GitHub OAuth App, store client id/secret in env vars.
4.2 Login redirect
    Add GET /auth/login that redirects the browser to GitHub's
    authorize URL.
4.3 OAuth callback
    Add GET /auth/callback that exchanges the returned code for a
    GitHub access token and prints the authenticated user's profile.
4.4 `users` table
    Define the `users` model and create-or-find a user row from the
    GitHub profile fetched in 4.3.
4.5 Issue a session
    After login, issue a JWT (or secure cookie) containing the
    user id.
4.6 Protect one endpoint
    Add a dependency that reads the JWT/session and returns 401 if
    missing/invalid; apply it to POST /repositories only.

Next feature: 4.1 — Register the OAuth app.

## 5. Test suite

5.1 First test
    Add pytest + httpx TestClient, write one test for GET /health.
5.2 Test DB fixture
    Add a fixture that creates a fresh test database (or in-memory
    SQLite) per test run so tests don't touch your real data.
5.3 Repository endpoint tests
    Test POST/GET /repositories using the fixture from 5.2.
5.4 Issue endpoint tests
    Test POST/GET /repositories/{id}/issues.
5.5 Mocked OAuth test
    Test the /auth/callback flow with GitHub's token/user calls
    mocked out (no real network call).

Next feature: 5.1 — First test.

## 6. Docker environment

6.1 Dockerfile
    Write a Dockerfile that runs the FastAPI app; confirm
    `docker build` + `docker run` serves /health locally.
6.2 docker-compose with Postgres
    Add docker-compose.yml with an `app` service and a `postgres`
    service (pgvector-enabled image).
6.3 Wire app to compose Postgres
    Point the app's DB URL at the compose Postgres service; confirm
    `docker compose up` serves /db-health successfully.
6.4 Run migrations in compose
    Run `alembic upgrade head` against the compose Postgres (as a
    documented command or a compose `command:` step).

Next feature: 6.1 — Dockerfile.

## 7. GitHub Actions CI

7.1 Lint workflow
    A workflow that installs dependencies and runs the linter on
    every push.
7.2 Test workflow
    Add a step that runs the pytest suite from section 5.
7.3 Postgres service in CI
    Add a Postgres service container to the workflow so DB-backed
    tests (5.3, 5.4) pass in CI, not just locally.

Next feature: 7.1 — Lint workflow.

## 8. Deployed API

8.1 First manual deploy
    Deploy the FastAPI app to a host (Render/Fly.io/Railway); confirm
    /health responds on a public URL.
8.2 Managed Postgres
    Provision a managed Postgres (pgvector-enabled) and point the
    deployed app at it via env var.
8.3 Migrate the deployed DB
    Run `alembic upgrade head` against the deployed database.
8.4 Auto-deploy from CI
    Wire the host to redeploy automatically when CI passes on main.

Next feature: 8.1 — First manual deploy.

---

Overall next action: 1.2 — Fetch repo metadata.

---

Later PRD phases (not yet scoped into small features):
Week 4 — LLM provider abstraction (PRD §14)
Week 5 — Retrieval: chunking, embeddings, pgvector, reranking (PRD §10–11)
Week 6 — RAG investigation product with citations (PRD §9, §28)
Week 7 — Agent loop from scratch (PRD §15–17)
Week 8 — LangGraph routing + evaluation suite (PRD §18–26)
Week 9 — MCP server, Next.js UI, queue-backed execution (PRD §33–38)
Weeks 10–12 — SQL analytics depth, case study, portfolio polish (PRD §42, §47–49)
