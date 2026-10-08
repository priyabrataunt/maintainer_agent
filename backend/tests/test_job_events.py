import asyncio
import json

import fakeredis
import pytest
from rq import Queue

from backend.api.jobs import stream_job_events
from backend.config import settings
from backend.main import app
from backend.services import jobs as jobs_module
from backend.services.jobs import enqueue_job, get_queue


def collect(read_state, **kwargs) -> list[str]:
    async def go():
        return [frame async for frame in stream_job_events(read_state, **kwargs)]

    return asyncio.run(go())


def scripted(*states):
    """read_state that returns each state once, then repeats the last."""
    items = list(states)

    def read():
        return items.pop(0) if len(items) > 1 else items[0]

    return read


def state(status, attempts=1, **extra):
    return {"status": status, "attempts": attempts, **extra}


def events(frames):
    out = []
    for frame in frames:
        if frame.startswith(":"):
            out.append(("comment", None))
            continue
        name, data = frame.strip().split("\n", 1)
        out.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


def test_emits_each_status_change_then_done():
    frames = collect(
        scripted(
            state("queued", 0), state("running", 1), state("succeeded", 1, result={"a": 1})
        ),
        poll_interval_s=0,
    )

    assert events(frames) == [
        ("status", {"status": "queued", "attempts": 0}),
        ("status", {"status": "running", "attempts": 1}),
        ("status", {"status": "succeeded", "attempts": 1}),
        ("done", state("succeeded", 1, result={"a": 1})),
    ]


def test_unchanged_status_is_not_repeated():
    frames = collect(
        scripted(state("running"), state("running"), state("running"), state("failed")),
        poll_interval_s=0,
    )

    assert [e[0] for e in events(frames)] == ["status", "status", "done"]


def test_retry_shows_as_a_new_status_event():
    frames = collect(
        scripted(
            state("running", 1), state("queued", 1), state("running", 2), state("succeeded", 2)
        ),
        poll_interval_s=0,
    )

    attempts = [e[1]["attempts"] for e in events(frames) if e[0] == "status"]
    assert attempts == [1, 1, 2, 2]


def test_failed_job_ends_the_stream_with_its_error():
    frames = collect(scripted(state("failed", 3, error="boom")), poll_interval_s=0)

    assert events(frames)[-1] == ("done", state("failed", 3, error="boom"))


def test_missing_job_reports_an_error_and_stops():
    frames = collect(lambda: None, poll_interval_s=0)

    assert events(frames) == [("error", {"detail": "Job not found"})]


def test_keep_alive_comments_while_waiting():
    frames = collect(
        scripted(*([state("running")] * 6 + [state("succeeded")])),
        poll_interval_s=0.01, heartbeat_every_s=0.02,
    )

    assert ("comment", None) in events(frames)


def test_gives_up_with_a_timeout_event():
    frames = collect(lambda: state("running"), poll_interval_s=0.01, max_seconds=0.05)

    assert events(frames)[-1][0] == "timeout"


@pytest.fixture
def api(client, db_session, monkeypatch):
    import contextlib

    @contextlib.contextmanager
    def session():
        yield db_session

    monkeypatch.setattr(jobs_module.deps, "session_factory", session)
    queue = Queue("t", connection=fakeredis.FakeRedis(), is_async=False)
    app.dependency_overrides[get_queue] = lambda: queue
    yield client, queue
    app.dependency_overrides.pop(get_queue, None)


def test_endpoint_streams_a_finished_job(api, db_session, user):
    client, queue = api
    job, _ = enqueue_job(db_session, queue, "echo", {"x": 1}, user.id)

    with client.stream("GET", f"/jobs/{job.id}/events") as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache, no-transform"
    parsed = events(body.strip().split("\n\n"))
    assert parsed[-1][0] == "done" and parsed[-1][1]["result"] == {"echo": {"x": 1}}


def test_endpoint_hides_other_users_jobs(api, db_session, user):
    client, queue = api
    job, _ = enqueue_job(db_session, queue, "echo", {}, None)  # owned by nobody

    assert client.get(f"/jobs/{job.id}/events").status_code == 404


def test_endpoint_requires_login(api, db_session, user):
    client, queue = api
    job, _ = enqueue_job(db_session, queue, "echo", {}, user.id)
    client.cookies.clear()

    assert client.get(f"/jobs/{job.id}/events").status_code == 401


def test_login_redirects_to_the_configured_page(anon_client, monkeypatch):
    import httpx
    import respx

    monkeypatch.setattr(settings, "post_login_redirect", "http://localhost:3000/")
    with respx.mock as mock:
        mock.post("https://github.com/login/oauth/access_token").mock(
            return_value=httpx.Response(200, json={"access_token": "t"})
        )
        mock.get("https://api.github.com/user").mock(
            return_value=httpx.Response(200, json={"id": 5, "login": "x", "avatar_url": None})
        )
        anon_client.cookies.set("oauth_state", "s")
        response = anon_client.get("/auth/callback", params={"code": "c", "state": "s"})

    assert response.headers["location"] == "http://localhost:3000/"
