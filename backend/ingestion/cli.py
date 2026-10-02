import argparse

from backend.ingestion.github_client import GitHubClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest a GitHub repository.")
    parser.add_argument("--owner", required=True, help="GitHub repository owner")
    parser.add_argument("--repo", required=True, help="GitHub repository name")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    print(f"owner: {args.owner}")
    print(f"repo: {args.repo}")

    with GitHubClient() as github:
        data, rate_limit_remaining = github.get_repo(args.owner, args.repo)
        issues, rate_limit_remaining = github.get_issues(args.owner, args.repo)
    print(f"name: {data['name']}")
    print(f"description: {data['description']}")
    print(f"stars: {data['stargazers_count']}")
    print(f"rate limit remaining: {rate_limit_remaining}")

    for issue in issues:
        if "pull_request" in issue:
            continue
        print(f"#{issue['number']} {issue['title']}")


if __name__ == "__main__":
    main()
