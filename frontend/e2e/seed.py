"""Create the E2E user/repository/issues, print a login JWT, and (with `cleanup`) remove them."""
import sys
from datetime import datetime

from sqlalchemy import delete, select, text

from backend.db import SessionLocal
from backend.models.issue import Issue
from backend.models.repository import Repository
from backend.models.user import User
from backend.retrieval.embedder import HashEmbedder
from backend.retrieval.indexer import index_repository
from backend.security import create_access_token

GITHUB_ID = 424242


def cleanup(db) -> None:
    user = db.scalar(select(User).where(User.github_id == GITHUB_ID))
    repo_ids = db.scalars(select(Repository.id).where(Repository.owner == "e2e")).all()
    if user:
        db.execute(text("DELETE FROM jobs WHERE user_id = :u"), {"u": user.id})
    for rid in repo_ids:
        inv_ids = [r[0] for r in db.execute(
            text("SELECT id FROM investigations WHERE repository_id = :r"), {"r": rid})]
        for iid in inv_ids:
            for table in ("citations", "pending_actions", "tool_calls", "investigation_messages"):
                db.execute(text(f"DELETE FROM {table} WHERE investigation_id = :i"), {"i": iid})
            db.execute(
                text("UPDATE model_calls SET investigation_id = NULL WHERE investigation_id = :i"),
                {"i": iid},
            )
            db.execute(text("DELETE FROM investigations WHERE id = :i"), {"i": iid})
        db.execute(text("DELETE FROM document_chunks WHERE repository_id = :r"), {"r": rid})
        db.execute(
            text("DELETE FROM issue_comments WHERE issue_id IN "
                 "(SELECT id FROM issues WHERE repository_id = :r)"),
            {"r": rid},
        )
        db.execute(delete(Issue).where(Issue.repository_id == rid))
        db.execute(delete(Repository).where(Repository.id == rid))
    if user:
        db.execute(delete(User).where(User.id == user.id))
    db.commit()


def add_pending_action(tool: str, number: int) -> None:
    """Queue a proposed write on the E2E user's latest investigation (as an agent run would)."""
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.github_id == GITHUB_ID))
        inv_id = db.execute(
            text("SELECT id FROM investigations WHERE user_id = :u ORDER BY id DESC LIMIT 1"),
            {"u": user.id},
        ).scalar_one()
        db.execute(
            text("INSERT INTO pending_actions (investigation_id, tool_name, args, status) "
                 "VALUES (:i, :t, CAST(:a AS jsonb), 'pending')"),
            {"i": inv_id, "t": tool, "a": f'{{"number": {number}}}'},
        )
        db.commit()


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "action":
        add_pending_action(sys.argv[2], int(sys.argv[3]))
        return
    with SessionLocal() as db:
        cleanup(db)
        if len(sys.argv) > 1 and sys.argv[1] == "cleanup":
            return
        user = User(github_id=GITHUB_ID, login="e2e-octocat", avatar_url=None)
        repo = Repository(owner="e2e", name="demo", description="E2E demo repo")
        db.add_all([user, repo])
        db.flush()
        for number, title, body, state in [
            (1, "Crash on startup", "segfault when the config file is missing", "open"),
            (2, "Add dark mode", "please support a dark theme", "closed"),
        ]:
            db.add(Issue(repository_id=repo.id, github_number=number, title=title, body=body,
                         state=state, labels=[], created_at=datetime(2026, 1, 1)))
        db.flush()
        index_repository(db, repo.id, HashEmbedder())
        db.commit()
        print(f"{create_access_token(user.id)} {repo.id} {user.id}")


if __name__ == "__main__":
    main()
