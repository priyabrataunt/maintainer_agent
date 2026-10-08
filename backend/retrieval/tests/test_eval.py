from backend.retrieval.eval import EvalCase, evaluate_retrieval

INDEX = {
    "crash on start": [12, 7, 3],
    "dark mode": [30, 1, 2, 4, 5, 6],
    "login broken": [1, 2, 3, 4, 5, 99],
}


def search(query: str, k: int) -> list[int]:
    return INDEX[query][:k]


def test_hit_rate_counts_cases_with_expected_issue_in_top_k():
    cases = [
        EvalCase("crash on start", frozenset({12})),
        EvalCase("dark mode", frozenset({30})),
        EvalCase("login broken", frozenset({99})),  # rank 6, outside top 5
    ]

    report = evaluate_retrieval(search, cases, k=5)

    assert report.hit_rate == 2 / 3
    assert [r.case.query for r in report.misses] == ["login broken"]


def test_larger_k_recovers_the_miss():
    cases = [EvalCase("login broken", frozenset({99}))]

    assert evaluate_retrieval(search, cases, k=5).hit_rate == 0.0
    assert evaluate_retrieval(search, cases, k=6).hit_rate == 1.0


def test_any_expected_issue_counts():
    cases = [EvalCase("crash on start", frozenset({3, 500}))]

    assert evaluate_retrieval(search, cases, k=3).hit_rate == 1.0


def test_no_cases_gives_zero():
    assert evaluate_retrieval(search, [], k=5).hit_rate == 0.0
