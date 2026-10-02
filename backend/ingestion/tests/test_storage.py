import json

from backend.ingestion import storage


def test_save_json_writes_file_under_owner_repo_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)

    path = storage.save_json("octocat", "hello-world", "issues.json", [{"number": 1}])

    assert path == tmp_path / "octocat_hello-world" / "issues.json"
    assert json.loads(path.read_text()) == [{"number": 1}]
