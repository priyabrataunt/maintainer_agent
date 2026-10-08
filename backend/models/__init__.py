"""Import every model so SQLAlchemy can resolve foreign keys between them.

A process that touches only some models (the job worker, the MCP server) would otherwise
fail at flush time with NoReferencedTableError for tables it never imported.
"""
from backend.models import (  # noqa: F401
    agent_run,
    document_chunk,
    evaluation,
    investigation,
    issue,
    issue_comment,
    job,
    model_call,
    prompt_version,
    repository,
    user,
)
