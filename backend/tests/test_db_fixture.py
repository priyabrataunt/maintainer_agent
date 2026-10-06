from sqlalchemy import text


def test_changes_are_visible_within_the_same_test(db_session):
    db_session.execute(text("CREATE TABLE scratch_rollback_check (id int)"))
    db_session.execute(text("INSERT INTO scratch_rollback_check VALUES (1)"))

    result = db_session.execute(text("SELECT count(*) FROM scratch_rollback_check")).scalar()

    assert result == 1


def test_changes_do_not_leak_into_the_next_test(db_session):
    result = db_session.execute(text("SELECT to_regclass('scratch_rollback_check')")).scalar()

    assert result is None
