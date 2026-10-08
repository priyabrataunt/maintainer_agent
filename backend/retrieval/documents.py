from backend.models.issue import Issue
from backend.models.issue_comment import IssueComment


def build_issue_document(issue: Issue, comments: list[IssueComment]) -> str:
    """One searchable document per issue: title, body, then comments in order."""
    parts = [issue.title, issue.body or ""]
    for comment in sorted(comments, key=lambda c: c.created_at):
        parts.append(f"@{comment.user_login}: {comment.body}")
    return "\n\n".join(p for p in parts if p)
