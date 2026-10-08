from sqlalchemy import text
from sqlalchemy.orm import Session


def _rows(db: Session, sql: str, **params) -> list[dict]:
    return [
        {k: (float(v) if hasattr(v, "as_tuple") else v) for k, v in row._mapping.items()}
        for row in db.execute(text(sql), params)
    ]


def cost_per_investigation(db: Session, limit: int = 20) -> list[dict]:
    """Spend, tokens and call count per investigation (JOIN + GROUP BY), costliest first."""
    return _rows(db, """
        SELECT i.id AS investigation_id,
               COUNT(mc.id) AS calls,
               SUM(mc.input_tokens) AS input_tokens,
               SUM(mc.output_tokens) AS output_tokens,
               SUM(mc.cost_usd) AS cost_usd
        FROM investigations i
        JOIN model_calls mc ON mc.investigation_id = i.id
        GROUP BY i.id
        ORDER BY cost_usd DESC NULLS LAST, i.id
        LIMIT :limit
    """, limit=limit)


def latency_percentiles(db: Session) -> list[dict]:
    """p50 / p95 latency of successful calls per provider and model."""
    return _rows(db, """
        SELECT provider, model, COUNT(*) AS calls,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_s) AS p50_s,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_s) AS p95_s
        FROM model_calls
        WHERE status = 'ok'
        GROUP BY provider, model
        ORDER BY provider, model
    """)


def tool_failure_rates(db: Session) -> list[dict]:
    """Failure rate per tool, ranked worst first with a window function."""
    return _rows(db, """
        SELECT name, calls, failures, failure_rate,
               RANK() OVER (ORDER BY failure_rate DESC) AS failure_rank
        FROM (
            SELECT name,
                   COUNT(*) AS calls,
                   COUNT(*) FILTER (WHERE NOT ok) AS failures,
                   COUNT(*) FILTER (WHERE NOT ok)::float / COUNT(*) AS failure_rate
            FROM tool_calls
            GROUP BY name
        ) per_tool
        ORDER BY failure_rank, name
    """)


def daily_cost(db: Session) -> list[dict]:
    """Cost per day with a running total (window function over the daily sums)."""
    return _rows(db, """
        SELECT day, cost_usd, SUM(cost_usd) OVER (ORDER BY day) AS running_total_usd
        FROM (
            SELECT created_at::date AS day, SUM(cost_usd) AS cost_usd
            FROM model_calls
            GROUP BY created_at::date
        ) per_day
        ORDER BY day
    """)


def runs_at_step_limit(db: Session, max_steps: int = 8) -> list[dict]:
    """Investigations whose tool-call count reached the step cap (CTE).

    A proxy for "hit the max-step limit": the agent loop makes one model step per tool
    round, so a run with >= max_steps tool calls almost certainly ran into the cap.
    """
    return _rows(db, """
        WITH tool_counts AS (
            SELECT investigation_id, COUNT(*) AS tool_calls
            FROM tool_calls
            GROUP BY investigation_id
        )
        SELECT i.id AS investigation_id, tc.tool_calls
        FROM tool_counts tc
        JOIN investigations i ON i.id = tc.investigation_id
        WHERE tc.tool_calls >= :max_steps
        ORDER BY tc.tool_calls DESC, i.id
    """, max_steps=max_steps)


def all_metrics(db: Session) -> dict:
    return {
        "cost_per_investigation": cost_per_investigation(db),
        "latency_percentiles": latency_percentiles(db),
        "tool_failure_rates": tool_failure_rates(db),
        "daily_cost": daily_cost(db),
        "runs_at_step_limit": runs_at_step_limit(db),
    }


def model_comparison(db: Session) -> list[dict]:
    """One row per evaluation run: accuracy, trajectory pass rate, judge score, latency, cost."""
    return _rows(db, """
        SELECT r.id AS run_id, r.name, r.model,
               COUNT(*) AS cases,
               AVG(res.citation_correct::int)::float AS citation_accuracy,
               AVG(res.trajectory_ok::int)::float AS trajectory_pass_rate,
               AVG(res.judge_score)::float AS avg_judge_score,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY res.latency_s) AS p50_latency_s,
               SUM(res.cost_usd) AS total_cost_usd
        FROM evaluation_runs r
        JOIN evaluation_results res ON res.run_id = r.id
        GROUP BY r.id
        ORDER BY r.id
    """)
