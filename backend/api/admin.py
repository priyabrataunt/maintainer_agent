from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.api.auth import current_user
from backend.config import settings
from backend.db import get_db
from backend.models.user import User
from backend.services.metrics import all_metrics

router = APIRouter()


def require_admin(user: User = Depends(current_user)) -> User:
    admins = {a.strip().lower() for a in settings.admin_logins.split(",") if a.strip()}
    if user.login.lower() not in admins:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("/admin/metrics")
def metrics(db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    return all_metrics(db)
