import httpx

GITHUB_API_URL = "https://api.github.com"


def get_repo(owner: str, repo: str) -> dict:
    response = httpx.get(f"{GITHUB_API_URL}/repos/{owner}/{repo}")
    response.raise_for_status()
    return response.json()
