import pytest

from backend.agent.graph import run_agent_graph
from backend.agent.loop import run_agent as run_agent_loop


@pytest.fixture(params=["loop", "graph"])
def run_agent(request):
    """The plain loop and the LangGraph port must behave identically."""
    return run_agent_loop if request.param == "loop" else run_agent_graph
