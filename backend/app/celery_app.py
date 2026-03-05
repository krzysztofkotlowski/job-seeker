"""Celery application and import tasks for background work."""

import os

from celery import Celery

from app.import_engine import SOURCES, _prepare_source, _run_justjoin, _run_nofluffjobs


def _make_celery() -> Celery:
  broker_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
  result_backend = os.environ.get("CELERY_RESULT_BACKEND", broker_url)
  app = Celery("jobseeker", broker=broker_url, backend=result_backend)
  app.conf.task_default_queue = "jobseeker"
  # Run tasks eagerly by default so imports work without a separate worker/broker.
  # When you later add a real Celery worker + Redis, set CELERY_ALWAYS_EAGER=0.
  if os.environ.get("CELERY_ALWAYS_EAGER", "1") == "1":
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = True
  return app


celery_app = _make_celery()


@celery_app.task(name="imports.run_source")
def run_import_source(source: str) -> None:
  """Run import for a single source in the worker process."""
  if source not in SOURCES:
    return
  _prepare_source(source)
  if source == "justjoin.it":
    _run_justjoin()
  elif source == "nofluffjobs.com":
    _run_nofluffjobs()


@celery_app.task(name="imports.run_all")
def run_import_all() -> None:
  """Run imports for all configured sources."""
  for src in SOURCES:
    run_import_source.delay(src)

