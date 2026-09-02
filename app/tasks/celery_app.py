from celery import Celery

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery("ragbot", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    imports=("app.tasks.jobs",),
)
