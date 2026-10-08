import argparse
import sys
from pathlib import Path

from sqlalchemy import select

from backend.api.investigations import get_llm_provider
from backend.config import settings
from backend.db import SessionLocal
from backend.evals.gate import check_run
from backend.evals.runner import load_cases, rag_answer_fn, run_eval
from backend.models.evaluation import EvaluationCase
from backend.models.repository import Repository
from backend.retrieval.embedder import get_embedder


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Evaluation runner.")
    sub = parser.add_subparsers(dest="command", required=True)

    load = sub.add_parser("load", help="load evaluation cases from a JSON file")
    load.add_argument("--owner", required=True)
    load.add_argument("--repo", required=True)
    load.add_argument("--file", required=True, type=Path)

    run = sub.add_parser("run", help="run all cases of a repository through the RAG pipeline")
    run.add_argument("--owner", required=True)
    run.add_argument("--repo", required=True)
    run.add_argument("--name", required=True, help="label for this run, e.g. 'baseline'")
    run.add_argument("--judge", action="store_true", help="also grade answers with an LLM judge")
    run.add_argument("--min-accuracy", type=float, help="fail below this citation accuracy")

    args = parser.parse_args(argv)
    with SessionLocal() as db:
        repo = db.scalar(
            select(Repository).where(Repository.owner == args.owner, Repository.name == args.repo)
        )
        if repo is None:
            sys.exit(f"{args.owner}/{args.repo} is not in the database; load it first.")

        if args.command == "load":
            cases = load_cases(db, repo.id, args.file)
            print(f"loaded {len(cases)} cases")
            return

        cases = db.scalars(
            select(EvaluationCase).where(EvaluationCase.repository_id == repo.id)
        ).all()
        if not cases:
            sys.exit("no evaluation cases for this repository; run 'load' first.")

        provider = get_llm_provider()
        run = run_eval(
            db, args.name, getattr(provider, "name", "unknown"), list(cases),
            rag_answer_fn(db, provider, get_embedder(), settings.retrieval_min_score),
            judge_provider=provider if args.judge else None,
        )
        ok, summary = check_run(db, run.id, args.min_accuracy or 0.0)
        print(summary)
        if args.min_accuracy is not None and not ok:
            sys.exit(1)


if __name__ == "__main__":
    main()
