from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.agent.loop import AgentResult
from backend.agent.tools import ToolRegistry
from backend.models.agent_run import PendingAction, ToolCall


class ActionAlreadyResolved(Exception):
    pass


def persist_agent_run(
    db: Session, investigation_id: int, result: AgentResult
) -> list[PendingAction]:
    """Store every tool call and queue the gated ones as pending actions."""
    pending = []
    for execution in result.executions:
        db.add(ToolCall(
            investigation_id=investigation_id,
            name=execution.name,
            args=execution.args,
            ok=execution.ok,
            result_size=len(execution.output),
            duration_s=execution.duration_s,
        ))
        if execution.pending:
            action = PendingAction(
                investigation_id=investigation_id,
                tool_name=execution.name,
                args=execution.args,
            )
            db.add(action)
            pending.append(action)
    db.commit()
    return pending


def _lock_pending(db: Session, investigation_id: int, action_id: int) -> PendingAction | None:
    """Fetch the action with a row lock so two concurrent confirms cannot both run it."""
    action = db.scalar(
        select(PendingAction)
        .where(PendingAction.id == action_id, PendingAction.investigation_id == investigation_id)
        .with_for_update()
    )
    if action is not None and action.status != "pending":
        raise ActionAlreadyResolved(f"Action {action_id} is already {action.status}")
    return action


def confirm_action(
    db: Session, investigation_id: int, action_id: int, registry: ToolRegistry
) -> PendingAction | None:
    """Run a pending action for real. Returns None if it does not exist."""
    action = _lock_pending(db, investigation_id, action_id)
    if action is None:
        return None
    execution = registry.execute(action.tool_name, action.args, confirmed=True)
    action.status = "confirmed" if execution.ok else "failed"
    action.result = execution.output
    action.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return action


def reject_action(db: Session, investigation_id: int, action_id: int) -> PendingAction | None:
    action = _lock_pending(db, investigation_id, action_id)
    if action is None:
        return None
    action.status = "rejected"
    action.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return action
