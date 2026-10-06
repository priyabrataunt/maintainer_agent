import argparse
import sys
from itertools import islice

from backend.ingestion.github_client import GitHubClient, RateLimitExceeded
from backend.ingestion.storage import save_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest a GitHub repository.")
    parser.add_argument("--owner", required=True, help="GitHub repository owner")
    parser.add_argument("--repo", required=True, help="GitHub repository name")
    parser.add_argument("--issue", type=int, help="Issue number to fetch comments for")
    parser.add_argument(
        "--limit", type=int, help="Max pull requests and commits to fetch"
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    print(f"owner: {args.owner}")
    print(f"repo: {args.repo}")

    try:
        with GitHubClient() as github:
            repo, rate_limit_remaining = github.get_repo(args.owner, args.repo)
            print(f"name: {repo.name}")
            print(f"description: {repo.description}")
            print(f"stars: {repo.stargazers_count}")
            print(f"rate limit remaining: {rate_limit_remaining}")

            issues = list(github.iter_issues(args.owner, args.repo))
            for issue in issues:
                print(f"#{issue.number} {issue.title}")

            if args.issue is not None:
                comments = github.get_issue_comments(args.owner, args.repo, args.issue)
                for comment in comments:
                    print(f"{comment.user_login}: {comment.body}")
                save_json(
                    args.owner,
                    args.repo,
                    f"comments_{args.issue}.json",
                    [c.model_dump(mode="json") for c in comments],
                )

            prs = list(islice(github.iter_pull_requests(args.owner, args.repo), args.limit))
            for pr in prs:
                print(f"PR #{pr.number} {pr.title}")

            commits = list(islice(github.iter_commits(args.owner, args.repo), args.limit))
            for commit in commits:
                print(f"{commit.sha[:7]} {commit.message.splitlines()[0]}")

            save_json(args.owner, args.repo, "repo.json", repo.model_dump())
            save_json(
                args.owner,
                args.repo,
                "issues.json",
                [i.model_dump(mode="json") for i in issues],
            )
            save_json(
                args.owner, args.repo, "pull_requests.json", [pr.model_dump() for pr in prs]
            )
            save_json(args.owner, args.repo, "commits.json", [c.model_dump() for c in commits])
    except RateLimitExceeded as exc:
        print(f"GitHub rate limit exceeded. Try again at {exc.reset_at.isoformat()}.")
        sys.exit(1)


if __name__ == "__main__":
    main()
