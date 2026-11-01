from apscheduler.schedulers.background import BackgroundScheduler

from .database import SessionLocal
from .services import run_due_checks

scheduler = BackgroundScheduler()


def _tick():
    """Runs every few seconds and checks every target that is due."""
    db = SessionLocal()
    try:
        run_due_checks(db)
    finally:
        db.close()


def start_scheduler():
    if not scheduler.running:
        scheduler.add_job(
            _tick, "interval", seconds=5, id="check_tick",
            max_instances=1, coalesce=True, replace_existing=True,
        )
        scheduler.start()


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)