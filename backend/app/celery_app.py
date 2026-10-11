"""Redis workers are optional; local jobs use FastAPI's background thread pool."""

import os

from celery import Celery

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "").strip()
EAGER_MODE = not CELERY_BROKER_URL
celery_app = Celery("ledger_recon", broker=CELERY_BROKER_URL or "memory://", include=["app.tasks"])
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_always_eager=EAGER_MODE,
    task_eager_propagates=False,
    task_ignore_result=True,
    broker_connection_timeout=3,
    broker_connection_retry_on_startup=True,
)
