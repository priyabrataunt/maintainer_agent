from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.llm.base import LLMError, LLMProvider, LLMResponse, Message
from backend.models.model_call import ModelCall
from backend.models.prompt_version import PromptVersion


def get_or_create_prompt_version(db: Session, name: str, content: str) -> PromptVersion:
    """Return the latest version of prompt `name` if its text is unchanged, else add a new one."""
    latest = db.scalar(
        select(PromptVersion)
        .where(PromptVersion.name == name)
        .order_by(PromptVersion.version.desc())
        .limit(1)
    )
    if latest is not None and latest.content == content:
        return latest
    version = PromptVersion(
        name=name, version=1 if latest is None else latest.version + 1, content=content
    )
    db.add(version)
    db.commit()
    return version


class RecordingProvider:
    """Persist every call (success or failure) to `model_calls`, tagged with a prompt version."""

    def __init__(
        self, inner: LLMProvider, db: Session, prompt_version_id: int | None = None
    ) -> None:
        self.inner = inner
        self.db = db
        self.name = inner.name
        self.prompt_version_id = prompt_version_id

    def complete(self, messages: list[Message]) -> LLMResponse:
        try:
            response = self.inner.complete(messages)
        except LLMError as exc:
            self.db.add(ModelCall(
                provider=self.inner.name,
                model=getattr(self.inner, "model", "unknown"),
                prompt_version_id=self.prompt_version_id,
                status="error",
                error=str(exc)[:1000],
                latency_s=0.0,
            ))
            self.db.commit()
            raise
        self.db.add(ModelCall(
            provider=response.provider,
            model=response.model,
            prompt_version_id=self.prompt_version_id,
            status="ok",
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            latency_s=response.latency_s,
            cost_usd=response.cost_usd,
        ))
        self.db.commit()
        return response
