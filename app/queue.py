"""RQ queue helpers with consistent retry policy."""

from redis import Redis
from rq import Queue, Retry

from app.config import settings


def get_queue() -> Queue:
    conn = Redis.from_url(settings.redis_url)
    return Queue(settings.rq_queue_name, connection=conn)


def enqueue_task(func_path: str, job_id: str):
    q = get_queue()
    retry = Retry(max=settings.job_max_retries, interval=[10, 30])
    return q.enqueue(
        func_path,
        job_id,
        job_timeout=settings.job_timeout,
        retry=retry,
    )
