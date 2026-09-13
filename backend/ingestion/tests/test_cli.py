from backend.ingestion.cli import main


def test_prints_owner_and_repo(capsys):
    main(["--owner", "octocat", "--repo", "hello-world"])

    captured = capsys.readouterr()
    assert "octocat" in captured.out
    assert "hello-world" in captured.out
