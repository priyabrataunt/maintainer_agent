import json

import pytest

from backend.loader import load_issue_comments_data, load_repository_data
from backend.models.issue import Issue
from backend.models.issue_comment import IssueComment
from backend.models.repository import Repository


def _write_fixture(data_dir, owner, name, description, issues):
    repo_dir = data_dir / f"{owner}_{name}"
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / "repo.json").write_text(
        json.dumps({"name": name, "description": description, "stargazers_count": 1})
    )
    (repo_dir / "issues.json").write_text(json.dumps(issues))


def test_loads_repository_and_issues_from_disk(db_session, tmp_path):
    _write_fixture(
        tmp_path,
        "octocat",
        "hello-world",
        "demo repo",
        [
            {
                "number": 1,
                "title": "bug",
                "state": "open",
                "created_at": "2026-01-01T00:00:00Z",
            }
        ],
    )

    load_repository_data("octocat", "hello-world", db_session, data_dir=tmp_path)

    repo = (
        db_session.query(Repository)
        .filter_by(owner="octocat", name="hello-world")
        .one()
    )
    assert repo.description == "demo repo"

    issue = db_session.query(Issue).filter_by(repository_id=repo.id).one()
    assert issue.github_number == 1
    assert issue.title == "bug"
    assert issue.state == "open"


def test_loading_twice_upserts_instead_of_duplicating(db_session, tmp_path):
    issue = {
        "number": 1,
        "title": "bug",
        "state": "open",
        "created_at": "2026-01-01T00:00:00Z",
    }
    _write_fixture(tmp_path, "octocat", "hello-world", "first description", [issue])
    load_repository_data("octocat", "hello-world", db_session, data_dir=tmp_path)

    updated_issue = {**issue, "title": "bug fixed", "state": "closed"}
    _write_fixture(
        tmp_path, "octocat", "hello-world", "updated description", [updated_issue]
    )
    load_repository_data("octocat", "hello-world", db_session, data_dir=tmp_path)

    repos = (
        db_session.query(Repository)
        .filter_by(owner="octocat", name="hello-world")
        .all()
    )
    assert len(repos) == 1
    assert repos[0].description == "updated description"

    issues = db_session.query(Issue).filter_by(repository_id=repos[0].id).all()
    assert len(issues) == 1
    assert issues[0].title == "bug fixed"
    assert issues[0].state == "closed"


def test_bad_row_rolls_back_the_entire_load(db_session, tmp_path):
    good_issue = {
        "number": 1,
        "title": "good issue",
        "state": "open",
        "created_at": "2026-01-01T00:00:00Z",
    }
    bad_issue = {
        "number": 2,
        "state": "open",
        "created_at": "2026-01-01T00:00:00Z",
    }  # missing required "title"
    _write_fixture(
        tmp_path, "octocat", "hello-world", "demo repo", [good_issue, bad_issue]
    )

    with pytest.raises(KeyError):
        load_repository_data("octocat", "hello-world", db_session, data_dir=tmp_path)

    assert (
        db_session.query(Repository)
        .filter_by(owner="octocat", name="hello-world")
        .count()
        == 0
    )
    assert db_session.query(Issue).count() == 0


def test_loads_issue_comments_from_disk(db_session, tmp_path):
    _write_fixture(
        tmp_path,
        "octocat",
        "hello-world",
        "demo repo",
        [
            {
                "number": 1,
                "title": "bug",
                "state": "open",
                "created_at": "2026-01-01T00:00:00Z",
            }
        ],
    )
    load_repository_data("octocat", "hello-world", db_session, data_dir=tmp_path)

    repo_dir = tmp_path / "octocat_hello-world"
    (repo_dir / "comments_1.json").write_text(
        json.dumps(
            [
                {
                    "id": 101,
                    "user_login": "alice",
                    "body": "stack trace?",
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ]
        )
    )

    load_issue_comments_data("octocat", "hello-world", 1, db_session, data_dir=tmp_path)

    issue = db_session.query(Issue).filter_by(github_number=1).one()
    comment = db_session.query(IssueComment).filter_by(issue_id=issue.id).one()
    assert comment.github_comment_id == 101
    assert comment.user_login == "alice"
    assert comment.body == "stack trace?"


def test_loading_comments_twice_upserts_instead_of_duplicating(db_session, tmp_path):
    _write_fixture(
        tmp_path,
        "octocat",
        "hello-world",
        "demo repo",
        [
            {
                "number": 1,
                "title": "bug",
                "state": "open",
                "created_at": "2026-01-01T00:00:00Z",
            }
        ],
    )
    load_repository_data("octocat", "hello-world", db_session, data_dir=tmp_path)

    repo_dir = tmp_path / "octocat_hello-world"
    comment = {
        "id": 101,
        "user_login": "alice",
        "body": "stack trace?",
        "created_at": "2026-01-01T00:00:00Z",
    }
    (repo_dir / "comments_1.json").write_text(json.dumps([comment]))
    load_issue_comments_data("octocat", "hello-world", 1, db_session, data_dir=tmp_path)

    updated_comment = {**comment, "body": "edited: stack trace attached"}
    (repo_dir / "comments_1.json").write_text(json.dumps([updated_comment]))
    load_issue_comments_data("octocat", "hello-world", 1, db_session, data_dir=tmp_path)

    issue = db_session.query(Issue).filter_by(github_number=1).one()
    comments = db_session.query(IssueComment).filter_by(issue_id=issue.id).all()
    assert len(comments) == 1
    assert comments[0].body == "edited: stack trace attached"
