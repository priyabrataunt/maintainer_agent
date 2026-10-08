from datetime import datetime

import pytest

from backend.config import settings
from backend.models.agent_run import ToolCall
from backend.models.investigation import Investigation
from backend.models.model_call import ModelCall
from backend.models.repository import Repository
from backend.services.metrics import (
    cost_per_investigation,
    daily_cost,
    latency_percentiles,
    runs_at_step_limit,
    tool_failure_rates,
)


@pytest.fixture
def investigations(db_session):
    repo = Repository(owner="o", name="r")
    db_session.add(repo)
    db_session.flush()
    made = []
    for _ in range(3):
        inv = Investigation(repository_id=repo.id, question="q", status="answered", answer="a")
        db_session.add(inv)
        made.append(inv)
    db_session.flush()
    return made


def call(db, inv, cost, latency=1.0, day=1, status="ok", model="m1", tin=10, tout=5):
    db.add(ModelCall(
        provider="p", model=model, investigation_id=inv.id if inv else None, status=status,
        input_tokens=tin, output_tokens=tout, latency_s=latency, cost_usd=cost,
        created_at=datetime(2026, 1, day, 12),
    ))
    db.flush()


def tool(db, inv, name, ok=True):
    db.add(ToolCall(
        investigation_id=inv.id, name=name, args={}, ok=ok, result_size=10, duration_s=0.1
    ))
    db.flush()


def test_cost_per_investigation_sums_and_orders(db_session, investigations):
    a, b, c = investigations
    call(db_session, a, 0.10)
    call(db_session, a, 0.20)
    call(db_session, b, 0.50)

    rows = cost_per_investigation(db_session)

    assert [r["investigation_id"] for r in rows] == [b.id, a.id]  # c has no calls: excluded
    assert rows[1]["cost_usd"] == pytest.approx(0.30)
    assert rows[1]["calls"] == 2 and rows[1]["input_tokens"] == 20


def test_cost_per_investigation_ignores_unlinked_calls(db_session, investigations):
    call(db_session, None, 9.99)

    assert cost_per_investigation(db_session) == []


def test_latency_percentiles_use_continuous_interpolation(db_session, investigations):
    for latency in (1.0, 2.0, 3.0, 4.0, 5.0):
        call(db_session, None, 0.0, latency=latency)
    call(db_session, None, 0.0, latency=100.0, status="error")  # errors are excluded

    (row,) = latency_percentiles(db_session)

    assert row["calls"] == 5
    assert row["p50_s"] == pytest.approx(3.0)
    assert row["p95_s"] == pytest.approx(4.8)


def test_latency_percentiles_group_by_model(db_session, investigations):
    call(db_session, None, 0.0, model="a")
    call(db_session, None, 0.0, model="b")

    assert [r["model"] for r in latency_percentiles(db_session)] == ["a", "b"]


def test_tool_failure_rates_ranked_worst_first(db_session, investigations):
    inv = investigations[0]
    for ok in (True, True, True, False):
        tool(db_session, inv, "search_issues", ok)
    for ok in (False, False):
        tool(db_session, inv, "get_issue", ok)
    tool(db_session, inv, "get_pr", True)

    rows = tool_failure_rates(db_session)

    assert [(r["name"], r["failure_rank"]) for r in rows] == [
        ("get_issue", 1), ("search_issues", 2), ("get_pr", 3),
    ]
    assert rows[0]["failure_rate"] == 1.0 and rows[1]["failure_rate"] == 0.25


def test_tool_failure_ties_share_a_rank(db_session, investigations):
    inv = investigations[0]
    tool(db_session, inv, "a", False)
    tool(db_session, inv, "b", False)

    assert [r["failure_rank"] for r in tool_failure_rates(db_session)] == [1, 1]


def test_daily_cost_has_running_total(db_session, investigations):
    call(db_session, None, 1.00, day=1)
    call(db_session, None, 0.50, day=1)
    call(db_session, None, 2.00, day=3)

    rows = daily_cost(db_session)

    assert [(str(r["day"]), r["cost_usd"], r["running_total_usd"]) for r in rows] == [
        ("2026-01-01", 1.5, 1.5), ("2026-01-03", 2.0, 3.5),
    ]


def test_runs_at_step_limit_finds_long_runs(db_session, investigations):
    short, long_, exact = investigations
    for _ in range(3):
        tool(db_session, short, "search_issues")
    for _ in range(12):
        tool(db_session, long_, "search_issues")
    for _ in range(8):
        tool(db_session, exact, "search_issues")

    rows = runs_at_step_limit(db_session, max_steps=8)

    assert [(r["investigation_id"], r["tool_calls"]) for r in rows] == [
        (long_.id, 12), (exact.id, 8),
    ]


def test_metrics_endpoint_for_admin(client, db_session, investigations, monkeypatch):
    monkeypatch.setattr(settings, "admin_logins", "OctoCat, someone")
    call(db_session, investigations[0], 0.25)

    response = client.get("/admin/metrics")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "cost_per_investigation", "latency_percentiles", "tool_failure_rates",
        "daily_cost", "runs_at_step_limit",
    }
    assert body["cost_per_investigation"][0]["cost_usd"] == pytest.approx(0.25)


def test_metrics_endpoint_forbidden_for_non_admin(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_logins", "someone-else")

    assert client.get("/admin/metrics").status_code == 403


def test_metrics_endpoint_forbidden_when_no_admins_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_logins", "")

    assert client.get("/admin/metrics").status_code == 403


def test_metrics_endpoint_requires_login(anon_client):
    assert anon_client.get("/admin/metrics").status_code == 401
