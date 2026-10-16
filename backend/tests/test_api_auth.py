from urllib.parse import parse_qs, urlparse


def test_login_redirects_to_github_with_matching_state_cookie(client):
    response = client.get("/auth/login", follow_redirects=False)

    assert response.status_code == 307

    location = urlparse(response.headers["location"])
    assert location.netloc == "github.com"
    assert location.path == "/login/oauth/authorize"

    query = parse_qs(location.query)
    state_in_url = query["state"][0]
    assert response.cookies["oauth_state"] == state_in_url
