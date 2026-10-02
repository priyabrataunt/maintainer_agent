import json
from pathlib import Path

DATA_DIR = Path("data")


def save_json(owner: str, repo: str, filename: str, data: object) -> Path:
    """Write `data` as JSON to data/{owner}_{repo}/{filename}, creating dirs as needed."""
    repo_dir = DATA_DIR / f"{owner}_{repo}"
    repo_dir.mkdir(parents=True, exist_ok=True)
    path = repo_dir / filename
    path.write_text(json.dumps(data, indent=2))
    return path
