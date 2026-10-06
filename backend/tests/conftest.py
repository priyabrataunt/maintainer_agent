import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.config import settings
from backend.db import get_db
from backend.main import app

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


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
