import ast
from pathlib import Path
from typing import Literal


Severity = Literal["info", "warning", "error"]

RULE_SEVERITIES: dict[str, Severity] = {
    "todo_comment": "info",
    "bare_except": "warning",
    "print_call": "warning",
    "file_read_error": "error",
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


def analyze_project_folder(
    project_name: str,
    description: str,
    project_path: str,
):
    project_root = resolve_project_folder(project_path)
    python_files = discover_python_files(project_root)
    findings = []
    checked_files = 0

    for source_path in python_files:
        relative_path = source_path.relative_to(project_root).as_posix()

        try:
            code = source_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            findings.append(
                {
                    "file_path": relative_path,
                    "rule": "file_read_error",
                    "severity": severity_for_rule("file_read_error"),
                    "message": f"Could not read file as UTF-8: {exc}",
                }
            )
            continue

        checked_files += 1
        findings.extend(analyze_file(file_path=relative_path, code=code))

    return {
        "project_name": project_name,
        "status": "complete",
        "summary": (
            f"Checked {checked_files} of {len(python_files)} Python file(s) "
            f"from {project_root} for: {description}"
        ),
        "findings": findings,
    }


def resolve_project_folder(project_path: str) -> Path:
    if not project_path.strip():
        raise ValueError("Project path must not be blank.")

    project_root = Path(project_path).expanduser().resolve()

    if not project_root.exists():
        raise FileNotFoundError(f"Project folder does not exist: {project_root}")

    if not project_root.is_dir():
        raise NotADirectoryError(f"Project path is not a directory: {project_root}")

    return project_root


def discover_python_files(project_root: Path) -> list[Path]:
    return sorted(
        (path for path in project_root.rglob("*.py") if path.is_file()),
        key=lambda path: path.as_posix(),
    )


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

    if contains_print_call(code):
        findings.append(
            {
                "file_path": file_path,
                "rule": "print_call",
                "severity": severity_for_rule("print_call"),
                "message": "Print call found. Remove debugging output or use logging.",
            }
        )

    return findings


def contains_print_call(code: str) -> bool:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False

    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
        for node in ast.walk(tree)
    )
