import asyncio
import contextlib
import json
from datetime import datetime

import pytest
from mcp.client import Client

from backend.mcp_server import build_server
from backend.models.issue import Issue
from backend.models.repository import Repository
from backend.retrieval.embedder import HashEmbedder
from backend.retrieval.indexer import index_repository

NOW = datetime(2026, 1, 1)


@pytest.fixture
def server(db_session, tmp_path):
    repo = Repository(owner="o", name="r")
    db_session.add(repo)
    db_session.flush()
    for number, title, body, state in [
        (1, "Crash on startup", "segfault when config file is missing", "open"),
        (2, "Add dark mode", "please support a dark theme", "closed"),
    ]:
        db_session.add(Issue(
            repository_id=repo.id, github_number=number, title=title, body=body,
            state=state, labels=["bug"] if number == 1 else [], created_at=NOW,
        ))
    db_session.flush()
    index_repository(db_session, repo.id, HashEmbedder())

    data = tmp_path / "o_r"
    data.mkdir()
    (data / "commits.json").write_text(json.dumps([
        {"sha": "abcdef1234567", "message": "Fix crash\n\nlong description"},
        {"sha": "1234567abcdef", "message": "Add docs"},
    ]))
    (data / "pull_requests.json").write_text(json.dumps([{"number": 9, "title": "Add dark mode"}]))

    @contextlib.contextmanager
    def session():
        yield db_session

    return build_server(session, lambda: HashEmbedder(), tmp_path)


def call(server, name, **args):
    async def go():
        async with Client(server) as client:
            return await client.call_tool(name, args)

    return asyncio.run(go())


def text(result) -> str:
    return result.content[0].text


def test_lists_only_read_only_tools(server):
    async def go():
        async with Client(server) as client:
            return (await client.list_tools()).tools

    tools = asyncio.run(go())

    assert {t.name for t in tools} == {
        "search_issues", "get_issue", "list_recent_commits", "get_pr",
    }
    assert all(t.annotations.read_only_hint is True for t in tools)
    assert not {"post_comment", "add_label", "close_issue"} & {t.name for t in tools}


def test_tools_have_descriptions_and_typed_schemas(server):
    async def go():
        async with Client(server) as client:
            return {t.name: t for t in (await client.list_tools()).tools}

    tools = asyncio.run(go())

    assert "Search a repository" in tools["search_issues"].description
    props = tools["search_issues"].input_schema["properties"]
    assert set(props) == {"owner", "repo", "query", "limit", "state"}
    assert tools["search_issues"].input_schema["required"] == ["owner", "repo", "query"]


def test_search_issues_ranks_and_formats(server):
    result = call(server, "search_issues", owner="o", repo="r", query="app crashes at startup")

    assert not result.is_error
    first_line = text(result).splitlines()[0]
    assert first_line.startswith("#1 [open] Crash on startup (score ")


def test_search_issues_state_filter_and_limit(server):
    result = call(server, "search_issues", owner="o", repo="r", query="theme crash", state="closed")

    assert [line[:2] for line in text(result).splitlines() if line.startswith("#")] == ["#2"]
    one = call(server, "search_issues", owner="o", repo="r", query="theme crash", limit=1)
    assert len([ln for ln in text(one).splitlines() if ln.startswith("#")]) == 1


def test_search_without_matches_says_so(server):
    result = call(server, "search_issues", owner="o", repo="r", query="zzzz qqqq", state="closed")

    assert not result.is_error
    assert "#2" in text(result) or "No issues matched" in text(result)


def test_get_issue(server):
    result = call(server, "get_issue", owner="o", repo="r", number=1)

    assert text(result) == (
        "#1 [open] Crash on startup\nlabels: bug\n\nsegfault when config file is missing"
    )


def test_get_issue_truncates_huge_bodies(server, db_session):
    issue = db_session.query(Issue).filter_by(github_number=1).one()
    issue.body = "x" * 10_000
    db_session.flush()

    result = call(server, "get_issue", owner="o", repo="r", number=1)

    assert text(result).endswith("[body truncated]") and len(text(result)) < 4200


def test_missing_issue_is_a_recoverable_tool_error(server):
    result = call(server, "get_issue", owner="o", repo="r", number=999)

    assert result.is_error
    assert "#999 not found" in text(result) and "search_issues" in text(result)


def test_unknown_repository_is_a_recoverable_tool_error(server):
    result = call(server, "search_issues", owner="nobody", repo="nothing", query="x")

    assert result.is_error and "has not been ingested" in text(result)


def test_list_recent_commits(server):
    result = call(server, "list_recent_commits", owner="o", repo="r", limit=1)

    assert text(result) == "abcdef1 Fix crash"


def test_get_pr(server):
    assert text(call(server, "get_pr", owner="o", repo="r", number=9)) == "PR #9: Add dark mode"
    missing = call(server, "get_pr", owner="o", repo="r", number=1)
    assert missing.is_error and "PR #1 not found" in text(missing)


def test_missing_ingestion_files_are_reported(server):
    result = call(server, "list_recent_commits", owner="o", repo="other")

    assert result.is_error and "needs a sync" in text(result)


def test_invalid_arguments_are_rejected(server):
    result = call(server, "get_issue", owner="o", repo="r", number="not-a-number")

    assert result.is_error


def test_unexpected_crash_does_not_leak_internals(db_session, tmp_path):
    @contextlib.contextmanager
    def broken_session():
        raise RuntimeError("password=hunter2 host=db.internal")
        yield  # pragma: no cover

    server = build_server(broken_session, lambda: HashEmbedder(), tmp_path)

    result = call(server, "get_issue", owner="o", repo="r", number=1)

    assert result.is_error
    assert text(result) == "Error executing tool get_issue"
    assert "hunter2" not in text(result)
