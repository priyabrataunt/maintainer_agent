"""The real FastAPI app with only the LLM, GitHub and write-access registry swapped for fakes."""
import sys

sys.path.insert(0, "frontend/e2e")

import uvicorn  # noqa: E402
from fakes import CitingProvider  # noqa: E402

from backend.agent.write_tools import InMemoryIssueWriter, build_write_registry  # noqa: E402
from backend.api.actions import get_registry_factory  # noqa: E402
from backend.api.investigations import get_llm_provider  # noqa: E402
from backend.main import app  # noqa: E402

writer = InMemoryIssueWriter()
app.dependency_overrides[get_llm_provider] = lambda: CitingProvider()
app.dependency_overrides[get_registry_factory] = lambda: (
    lambda owner, repo, user: build_write_registry(writer)
)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
