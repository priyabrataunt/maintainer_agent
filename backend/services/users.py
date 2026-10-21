from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.models.user import User


def get_or_create_user(
    db: Session, github_id: int, login: str, name: str | None = None
) -> User:
    """Return the existing user for `github_id`, creating one if it doesn't exist."""
    user = db.query(User).filter(User.github_id == github_id).one_or_none()
    if user is not None:
        return user

    user = User(
        github_id=github_id,
        login=login,
        name=name,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
