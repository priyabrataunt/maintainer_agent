from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.agent.tools import ToolRegistry
from backend.agent.write_tools import build_write_registry
from backend.api.auth import current_user
from backend.api.investigations import _get_own_investigation
from backend.db import get_db
from backend.models.agent_run import PendingAction
from backend.models.repository import Repository
from backend.models.user import User
from backend.services.actions import ActionAlreadyResolved, confirm_action, reject_action

router = APIRouter()

RegistryFactory = Callable[[str, str, User], ToolRegistry]


def get_registry_factory() -> RegistryFactory:
    """Builds the write tools for (owner, repo, user).

    Real GitHub writes need the confirming user's own OAuth token, which this app does
    not store yet, so until it does confirmations fail closed with 503.
    """

    def unavailable(owner: str, repo: str, user: User) -> ToolRegistry:
        raise HTTPException(
            status_code=503, detail="GitHub write access is not configured for this user"
        )

    return unavailable


class ActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tool_name: str
    args: dict
    status: str
    result: str | None


class ActionDecision(BaseModel):
    action_id: int
    approve: bool


@router.get("/investigations/{investigation_id}/actions", response_model=list[ActionRead])
def list_actions(
    investigation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    _get_own_investigation(investigation_id, db, user)
    return db.scalars(
        select(PendingAction)
        .where(PendingAction.investigation_id == investigation_id)
        .order_by(PendingAction.id)
    ).all()


@router.post("/investigations/{investigation_id}/confirm", response_model=ActionRead)
def decide_action(
    investigation_id: int,
    decision: ActionDecision,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    registry_factory: RegistryFactory = Depends(get_registry_factory),
):
    investigation = _get_own_investigation(investigation_id, db, user)
    try:
        if decision.approve:
            repo = db.get(Repository, investigation.repository_id)
            registry = registry_factory(repo.owner, repo.name, user)
            action = confirm_action(db, investigation_id, decision.action_id, registry)
        else:
            action = reject_action(db, investigation_id, decision.action_id)
    except ActionAlreadyResolved as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    return action


def registry_for_writer(writer) -> ToolRegistry:
    return build_write_registry(writer)
