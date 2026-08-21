def analyze_project(
    project_name: str,
    description: str,
    code: str,
):
    findings = []

    if "TODO" in code:
        findings.append("TODO comment found. Decide whether it still needs work.")

    if "except:" in code:
        findings.append(
            "Bare except found. Catch a specific exception where possible."
        )

    if not findings:
        findings.append("No simple issues found in this code snippet.")

    return {
        "project_name": project_name,
        "status": "complete",
        "summary": f"Checked code submitted for: {description}",
        "findings": findings,
    }