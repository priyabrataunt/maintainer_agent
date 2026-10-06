import json
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.ingestion.storage import DATA_DIR
from backend.models.issue import Issue
from backend.models.issue_comment import IssueComment
from backend.models.repository import Repository


def load_repository_data(
    owner: str, name: str, db: Session, data_dir: Path = DATA_DIR
) -> int:
    """Upsert a repository and its issues from the step-1 ingestion files. Returns the repository id."""
    repo_dir = data_dir / f"{owner}_{name}"
    repo_data = json.loads((repo_dir / "repo.json").read_text())

    repo_stmt = (
        insert(Repository)
        .values(owner=owner, name=name, description=repo_data.get("description"))
        .on_conflict_do_update(
            index_elements=["owner", "name"],
            set_={"description": repo_data.get("description")},
        )
        .returning(Repository.id)
    )
    try:
        repository_id = db.execute(repo_stmt).scalar_one()

        issues_data = json.loads((repo_dir / "issues.json").read_text())
        for item in issues_data:
            issue_values = {
                "repository_id": repository_id,
                "github_number": item["number"],
                "title": item["title"],
                "body": item.get("body"),
                "state": item["state"],
                "labels": item.get("labels", []),
                "created_at": item["created_at"],
            }
            issue_stmt = insert(Issue).values(**issue_values).on_conflict_do_update(
                index_elements=["repository_id", "github_number"],
                set_={
                    "title": issue_values["title"],
                    "body": issue_values["body"],
                    "state": issue_values["state"],
                    "labels": issue_values["labels"],
                },
            )
            db.execute(issue_stmt)

        db.commit()
    except Exception:
        db.rollback()
        raise

    return repository_id


def load_issue_comments_data(
    owner: str,
    name: str,
    github_issue_number: int,
    db: Session,
    data_dir: Path = DATA_DIR,
) -> None:
    """Upsert comments for one issue from its step-1 ingestion file."""
    repo_dir = data_dir / f"{owner}_{name}"
    comments_data = json.loads(
        (repo_dir / f"comments_{github_issue_number}.json").read_text()
    )

    issue = (
        db.query(Issue)
        .join(Repository, Repository.id == Issue.repository_id)
        .filter(
            Repository.owner == owner,
            Repository.name == name,
            Issue.github_number == github_issue_number,
        )
        .one()
    )

    try:
        for item in comments_data:
            comment_values = {
                "issue_id": issue.id,
                "github_comment_id": item["id"],
                "user_login": item["user_login"],
                "body": item["body"],
                "created_at": item["created_at"],
            }
            comment_stmt = (
                insert(IssueComment)
                .values(**comment_values)
                .on_conflict_do_update(
                    index_elements=["issue_id", "github_comment_id"],
                    set_={"body": comment_values["body"]},
                )
            )
            db.execute(comment_stmt)

        db.commit()
    except Exception:
        db.rollback()
        raise
