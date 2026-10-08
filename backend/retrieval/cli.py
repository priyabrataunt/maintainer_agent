import argparse
import sys

from sqlalchemy import select

from backend.db import SessionLocal
from backend.models.repository import Repository
from backend.retrieval.embedder import get_embedder
from backend.retrieval.indexer import index_repository


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Embed all issues of a loaded repository.")
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repo", required=True)
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        repo = db.scalar(
            select(Repository).where(Repository.owner == args.owner, Repository.name == args.repo)
        )
        if repo is None:
            print(f"{args.owner}/{args.repo} is not in the database; load it first.")
            sys.exit(1)
        stats = index_repository(db, repo.id, get_embedder())
    print(
        f"created={stats.created} updated={stats.updated} "
        f"skipped={stats.skipped} deleted={stats.deleted}"
    )


if __name__ == "__main__":
    main()
