from backend.services.users import get_or_create_user


def test_get_or_create_user_returns_same_row_for_same_github_id(db_session):
    first = get_or_create_user(db_session, github_id=42, login="octocat", name="Octo")
    second = get_or_create_user(db_session, github_id=42, login="octocat", name="Octo")

    assert first.id == second.id
    assert db_session.query(first.__class__).count() == 1
