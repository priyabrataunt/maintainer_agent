from sqlalchemy.orm import Session

from backend.services.metrics import model_comparison


def check_run(
    db: Session, run_id: int, min_citation_accuracy: float, min_trajectory_pass_rate: float = 0.0
) -> tuple[bool, str]:
    """Pass/fail for a CI regression gate on one evaluation run."""
    row = next((r for r in model_comparison(db) if r["run_id"] == run_id), None)
    if row is None:
        return False, f"run {run_id} has no results"
    problems = []
    if row["citation_accuracy"] < min_citation_accuracy:
        problems.append(
            f"citation accuracy {row['citation_accuracy']:.2f} < {min_citation_accuracy:.2f}"
        )
    trajectory = row["trajectory_pass_rate"]
    if trajectory is not None and trajectory < min_trajectory_pass_rate:
        problems.append(f"trajectory pass rate {trajectory:.2f} < {min_trajectory_pass_rate:.2f}")
    summary = (
        f"run {run_id} ({row['name']}): {row['cases']} cases, "
        f"citation accuracy {row['citation_accuracy']:.2f}"
    )
    return (not problems), summary + (f" FAILED: {'; '.join(problems)}" if problems else " ok")
