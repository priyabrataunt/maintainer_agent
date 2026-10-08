from dataclasses import dataclass, field


def citation_correct(expected_issues: list[int], cited: list[int]) -> bool:
    """Deterministic check: did the answer cite a correct issue?

    With expected issues, at least one must be cited. With none expected (a case where the
    right behaviour is to find nothing), the answer must cite nothing.
    """
    if not expected_issues:
        return not cited
    return bool(set(expected_issues) & set(cited))


@dataclass
class TrajectoryScore:
    ok: bool
    problems: list[str] = field(default_factory=list)


def score_trajectory(
    tools_used: list[str],
    steps: int,
    expected_tools: list[str],
    forbidden_tools: list[str],
    max_steps: int,
) -> TrajectoryScore:
    """Right tools chosen, steps within bound, no forbidden tool called."""
    problems = []
    for tool in expected_tools:
        if tool not in tools_used:
            problems.append(f"expected tool not used: {tool}")
    for tool in sorted(set(tools_used) & set(forbidden_tools)):
        problems.append(f"forbidden tool used: {tool}")
    if steps > max_steps:
        problems.append(f"too many steps: {steps} > {max_steps}")
    return TrajectoryScore(ok=not problems, problems=problems)


def judge_agreement(pairs: list[tuple[int, int]]) -> dict[str, float]:
    """How closely judge scores match hand labels: [(human, judge), ...]."""
    if not pairs:
        raise ValueError("need at least one (human, judge) pair")
    n = len(pairs)
    diffs = [abs(h - j) for h, j in pairs]
    return {
        "n": n,
        "exact": sum(d == 0 for d in diffs) / n,
        "within_one": sum(d <= 1 for d in diffs) / n,
        "mean_abs_error": sum(diffs) / n,
    }
