def analyze_project(
    project_name: str,
    description: str,
    file_path:str,
    code: str,
):
    findings = []

    if "TODO" in code:
        findings.append(
            f"{file_path}: TODO comment found. Decide whether it still needs work."
        )
    if "except:" in code:
        findings.append(
            f"{file_path}: Bare except found. Catch a specific exception where possible."
        )

    if not findings:
        findings.append(f"{file_path}: No simple issues found in this code snippet.")

    return {
        "project_name": project_name,
        "status": "complete",
        "summary": f"Checked {file_path} code submitted for: {description}",
        "findings": findings,
    }