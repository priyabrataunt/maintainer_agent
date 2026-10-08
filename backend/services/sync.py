import json
from itertools import islice
from pathlib import Path

from sqlalchemy.orm import Session

from backend.ingestion.github_client import GitHubClient
from backend.ingestion.storage import DATA_DIR
from backend.loader import load_issue_comments_data, load_repository_data
from backend.retrieval.embedder import Embedder
from backend.retrieval.indexer import index_repository


def _write(data_dir: Path, owner: str, repo: str, filename: str, data: object) -> None:
    repo_dir = data_dir / f"{owner}_{repo}"
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / filename).write_text(json.dumps(data, indent=2))


def sync_repository(
    db: Session,
    github: GitHubClient,
    embedder: Embedder,
    owner: str,
    repo: str,
    max_issues: int = 200,
    data_dir: Path = DATA_DIR,
) -> dict:
    """Ingest from GitHub, load into Postgres, then embed: the whole Week 1 -> Week 5 path.

    Raises RateLimitExceeded if GitHub's quota runs out; the files written so far stay on disk.
    """
    repo_info, _ = github.get_repo(owner, repo)
    issues = list(islice(github.iter_issues(owner, repo), max_issues))
    _write(data_dir, owner, repo, "repo.json", repo_info.model_dump())
    _write(data_dir, owner, repo, "issues.json", [i.model_dump(mode="json") for i in issues])

    with_comments = []
    for issue in issues:
        comments = github.get_issue_comments(owner, repo, issue.number)
        if comments:
            _write(
                data_dir, owner, repo, f"comments_{issue.number}.json",
                [c.model_dump(mode="json") for c in comments],
            )
            with_comments.append(issue.number)

    repository_id = load_repository_data(owner, repo, db, data_dir=data_dir)
    for number in with_comments:
        load_issue_comments_data(owner, repo, number, db, data_dir=data_dir)
    stats = index_repository(db, repository_id, embedder)

    return {
        "repository_id": repository_id,
        "issues": len(issues),
        "issues_with_comments": len(with_comments),
        "chunks_created": stats.created,
        "chunks_updated": stats.updated,
        "chunks_skipped": stats.skipped,
        "chunks_deleted": stats.deleted,
    }
