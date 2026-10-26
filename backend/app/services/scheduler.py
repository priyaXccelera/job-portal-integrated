"""Background jobs (APScheduler 3.x BackgroundScheduler): job expiry and job-alert dispatch."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models.enums import AlertFrequency
from app.services import alerts, jobs_lifecycle

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_scheduler: BackgroundScheduler | None = None


def _run_with_session(name: str, task: Callable[[Session], object]) -> None:
    """Run ``task`` in its own session; log DB failures instead of killing the scheduler thread."""
    db = SessionLocal()
    try:
        result = task(db)
        logger.info("Scheduled job %s finished: %s", name, result)
    except SQLAlchemyError:
        logger.exception("Scheduled job %s failed", name)
        db.rollback()
    finally:
        db.close()


def expire_jobs_task() -> None:
    def task(db: Session) -> dict[str, int]:
        now = datetime.now(timezone.utc)
        expired = jobs_lifecycle.expire_jobs(db, now)
        warned = jobs_lifecycle.notify_expiring_soon(db, now)
        return {"expired": expired, "expiringNotified": warned}

    _run_with_session("expire_jobs", task)


def alerts_task(frequency: AlertFrequency) -> None:
    _run_with_session(
        f"alerts_{frequency.value}", lambda db: {"sent": alerts.dispatch_alerts(db, frequency)}
    )


def start_scheduler() -> BackgroundScheduler | None:
    """Start the scheduler once. No-op when disabled or already running."""
    global _scheduler
    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled (SCHEDULER_ENABLED=false)")
        return None
    with _lock:
        if _scheduler is not None and _scheduler.running:
            return _scheduler
        scheduler = BackgroundScheduler(
            timezone="UTC",
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
        )
        scheduler.add_job(
            expire_jobs_task,
            IntervalTrigger(minutes=max(1, settings.scheduler_expiry_minutes)),
            id="expire_jobs",
            replace_existing=True,
        )
        scheduler.add_job(
            alerts_task,
            IntervalTrigger(minutes=max(1, settings.scheduler_alert_instant_minutes)),
            args=[AlertFrequency.instant],
            id="alerts_instant",
            replace_existing=True,
        )
        scheduler.add_job(
            alerts_task,
            CronTrigger(hour=8, minute=0, timezone="UTC"),
            args=[AlertFrequency.daily],
            id="alerts_daily",
            replace_existing=True,
        )
        scheduler.add_job(
            alerts_task,
            CronTrigger(day_of_week="mon", hour=8, minute=0, timezone="UTC"),
            args=[AlertFrequency.weekly],
            id="alerts_weekly",
            replace_existing=True,
        )
        scheduler.start()
        _scheduler = scheduler
        logger.info("Scheduler started with jobs: %s", [j.id for j in scheduler.get_jobs()])
        return scheduler


def stop_scheduler(wait: bool = False) -> None:
    """Stop the scheduler if running; safe to call repeatedly or when never started."""
    global _scheduler
    with _lock:
        scheduler, _scheduler = _scheduler, None
    if scheduler is None:
        return
    if scheduler.running:
        scheduler.shutdown(wait=wait)
    logger.info("Scheduler stopped")
