import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.llm.base import LLMError, Message
from backend.llm.fake import FakeProvider
from backend.llm.recording import RecordingProvider, get_or_create_prompt_version
from backend.models.model_call import ModelCall
from backend.models.prompt_version import PromptVersion

MESSAGES = [Message(role="user", content="hi")]


def test_first_prompt_is_version_1(db_session):
    version = get_or_create_prompt_version(db_session, "triage", "You triage issues.")

    assert version.version == 1


def test_unchanged_prompt_reuses_version(db_session):
    first = get_or_create_prompt_version(db_session, "triage", "same")
    second = get_or_create_prompt_version(db_session, "triage", "same")

    assert first.id == second.id


def test_changed_prompt_bumps_version(db_session):
    get_or_create_prompt_version(db_session, "triage", "v1 text")
    second = get_or_create_prompt_version(db_session, "triage", "v2 text")

    assert second.version == 2


def test_prompt_names_version_independently(db_session):
    get_or_create_prompt_version(db_session, "triage", "a")
    other = get_or_create_prompt_version(db_session, "summarize", "b")

    assert other.version == 1


def test_duplicate_name_and_version_rejected(db_session):
    db_session.add(PromptVersion(name="p", version=1, content="a"))
    db_session.flush()
    db_session.add(PromptVersion(name="p", version=1, content="b"))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_successful_call_is_recorded_with_prompt_version(db_session):
    version = get_or_create_prompt_version(db_session, "triage", "text")
    provider = RecordingProvider(FakeProvider(["ok"]), db_session, version.id)

    provider.complete(MESSAGES)

    (call,) = db_session.scalars(select(ModelCall)).all()
    assert call.status == "ok"
    assert (call.provider, call.model) == ("fake", "fake-1")
    assert (call.input_tokens, call.output_tokens) == (10, 5)
    assert call.prompt_version_id == version.id
    assert call.created_at is not None


def test_failed_call_is_recorded_and_reraised(db_session):
    provider = RecordingProvider(FakeProvider([LLMError("503 boom", True)]), db_session)

    with pytest.raises(LLMError):
        provider.complete(MESSAGES)

    (call,) = db_session.scalars(select(ModelCall)).all()
    assert call.status == "error"
    assert "503 boom" in call.error
    assert call.prompt_version_id is None
