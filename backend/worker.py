"""Run the job worker: `uv run python -m backend.worker`."""
from redis import Redis
from rq import Worker

from backend.config import settings
from backend.services.jobs import get_queue


def main() -> None:
    queue = get_queue()
    # The scheduler moves delayed retries back onto the queue; without it they never run.
    Worker([queue], connection=Redis.from_url(settings.redis_url)).work(with_scheduler=True)


if __name__ == "__main__":
    main()
