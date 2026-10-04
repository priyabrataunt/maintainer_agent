from backend.ingestion.github_client import parse_link_header

LINK = (
    '<https://api.github.com/repositories/1/issues?page=2>; rel="next", '
    '<https://api.github.com/repositories/1/issues?page=5>; rel="last"'
)


def test_parses_next_and_last():
    assert parse_link_header(LINK) == {
        "next": "https://api.github.com/repositories/1/issues?page=2",
        "last": "https://api.github.com/repositories/1/issues?page=5",
    }


def test_last_page_has_no_next():
    header = '<https://api.github.com/repositories/1/issues?page=1>; rel="prev"'
    assert "next" not in parse_link_header(header)


def test_missing_header_returns_empty():
    assert parse_link_header(None) == {}
    assert parse_link_header("") == {}
