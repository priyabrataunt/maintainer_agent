# Maintainer Agent

![lint](https://github.com/priyabrataunt/maintainer_agent/actions/workflows/lint.yml/badge.svg)
![tests](https://github.com/priyabrataunt/maintainer_agent/actions/workflows/tests.yml/badge.svg)

An assistant for open-source maintainers: it ingests a GitHub repository, indexes its issues,
and answers questions about them with cited sources, finds duplicate issues, and can propose
(but never silently perform) changes.

## How an agent request flows

```mermaid
graph TD;
    start([request]) --> router{router};
    router -. lookup .-> lookup[lookup sub-graph<br/>read tools only, small context];
    router -. action .-> action[action sub-graph<br/>read + write tools, confirm gate];
    router -. escalate .-> escalate[escalate sub-graph<br/>no tools, summary for a human];
    lookup --> done([answer]);
    action --> done;
    escalate --> done;
```

The router is one LLM call that returns `lookup`, `action` or `escalate`. Anything it cannot
parse goes to `escalate`, so a confused router sends the request to a human instead of to the
write tools.

Each of `lookup` and `action` is the same two-node loop:

```mermaid
graph TD;
    start([question]) --> model[model: choose tools or answer];
    model -. tool calls .-> tools[tools: validate, gate, run];
    tools --> model;
    model -. answer / step limit / context limit .-> done([result]);
```

Code: `backend/agent/graph.py` (graphs), `backend/agent/loop.py` (the original plain loop the
graph reproduces; both are tested against the same suite), `backend/agent/tools.py`
(registry, validation, timeouts, output truncation).

### The confirmation gate

`post_comment`, `add_label` and `close_issue` never run on the model's say-so. Two modes:

- **queue** (default, used by the API): the call comes back as a *pending action*, stored in
  `pending_actions`; a human approves with `POST /investigations/{id}/confirm`. The row is
  locked while it runs, so two confirms cannot both execute it.
- **interrupt** (`InterruptibleRun`): the LangGraph run pauses before the gated tool and
  resumes with approve/reject. All decisions are collected before anything executes, so
  resuming never re-runs a tool.

### Failure modes the agent is built to survive

| Failure | What happens |
| --- | --- |
| Model loops forever | Hard step cap (default 8); returns a partial answer built from the tool results so far. |
| Model calls a tool that does not exist | The error lists the available tools; the model can recover. |
| Model sends bad arguments | Pydantic validation errors go back to the model as text. |
| A tool raises or hangs | Per-tool timeout; a crash returns only the exception type, never its message. |
| Huge tool output | Truncated with `…[truncated N tokens]` before it enters the context. |
| Context grows too large | Oldest tool results are shrunk first; if it still does not fit, the run stops with a partial answer. |
| Model cites an issue it was not shown | The answer is re-asked once, then rejected and withheld. |
| Issue text tries to give instructions | Issue text is delimited as data and the system prompt says so; the router and judge treat inputs the same way. |

## Running it

```bash
uv sync
cp .env.example .env        # fill in values
docker compose up -d        # Postgres with pgvector
uv run alembic upgrade head
uv run uvicorn backend.main:app --reload
uv run pytest
```

Ingest and index a repository:

```bash
uv run python -m backend.ingestion.cli --owner OWNER --repo REPO
uv run python -m backend.retrieval.cli --owner OWNER --repo REPO
```

Evaluate it (needs cases in a JSON file and an LLM key):

```bash
uv run python -m backend.evals.cli load --owner OWNER --repo REPO --file cases.json
uv run python -m backend.evals.cli run  --owner OWNER --repo REPO --name baseline --judge
```

Embeddings default to a local hash embedder so everything runs without keys; set
`EMBEDDING_PROVIDER=openai` and `OPENAI_API_KEY` for real retrieval quality.
