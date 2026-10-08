import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.config import settings
from backend.db import get_db
from backend.main import app
from backend.models.user import User
from backend.security import create_access_token

test_engine = create_engine(settings.test_database_url)


@pytest.fixture
def db_session():
    connection = test_engine.connect()
    transaction = connection.begin()
    # create_savepoint: app-level db.commit() ends a SAVEPOINT, not the
    # outer transaction, so the final rollback below always undoes it.
    session = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")()
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", SecretStr("test-secret-" + "x" * 32))


@pytest.fixture
def anon_client(db_session):
    """A client with no login cookie."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app, follow_redirects=False)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def user(db_session):
    user = User(github_id=1, login="octocat", avatar_url=None)
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def client(anon_client, user):
    """A client logged in as `user`."""
    anon_client.cookies.set("access_token", create_access_token(user.id))
    return anon_client
