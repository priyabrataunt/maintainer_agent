from typing import Literal


Severity = Literal["info", "warning", "error"]

RULE_SEVERITIES: dict[str, Severity] = {
    "todo_comment": "info",
    "bare_except": "warning",
}


def severity_for_rule(rule: str) -> Severity:
    try:
        return RULE_SEVERITIES[rule]
    except KeyError:
        raise ValueError(f"Unknown analysis rule: {rule}") from None


def analyze_project(
    project_name: str,
    description: str,
    file_path: str,
    code: str,
    files: list[dict[str, str]] | None = None,
):
    source_files = [
        {"file_path": file_path, "code": code},
        *(files or []),
    ]
    findings = []

    for source_file in source_files:
        findings.extend(
            analyze_file(
                file_path=source_file["file_path"],
                code=source_file["code"],
            )
        )

    return {
        "project_name": project_name,
        "status": "complete",
        "summary": f"Checked {len(source_files)} file(s) submitted for: {description}",
        "findings": findings,
    }


def analyze_file(file_path: str, code: str) -> list[dict[str, str]]:
    findings = []

    if "TODO" in code:
        findings.append(
            {
                "file_path": file_path,
                "rule": "todo_comment",
                "severity": severity_for_rule("todo_comment"),
                "message": "TODO comment found. Decide whether it still needs work.",
            }
        )

    if "except:" in code:
        findings.append(
            {
                "file_path": file_path,
                "rule": "bare_except",
                "severity": severity_for_rule("bare_except"),
                "message": "Bare except found. Catch a specific exception where possible.",
            }
        )

    return findings
