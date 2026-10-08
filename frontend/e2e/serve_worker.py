"""The real RQ worker, with the LLM and GitHub faked."""
import sys

sys.path.insert(0, "frontend/e2e")

from fakes import CitingProvider, github_transport  # noqa: E402

from backend.ingestion.github_client import GitHubClient  # noqa: E402
from backend.services import jobs  # noqa: E402
from backend.worker import main  # noqa: E402

jobs.deps.llm_provider = lambda: CitingProvider(delay_s=2.0)
jobs.deps.github = lambda: GitHubClient(token="e2e", transport=github_transport())

if __name__ == "__main__":
    main()
