from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models
from .checker import check_http, check_ping


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def perform_check(target: models.Target) -> dict:
    if target.check_type == "ping":
        result = check_ping(target.address)
        if not result["is_up"]:
            # Many servers block ping, so try HTTP before calling it down
            fallback = check_http(f"http://{target.address}")
            if fallback["is_up"]:
                fallback["error"] = "Ping blocked, HTTP fallback used"
                return fallback
        return result
    return check_http(target.address)


def run_check(db: Session, target: models.Target) -> models.CheckResult:
    result = perform_check(target)
    row = models.CheckResult(target_id=target.id, checked_at=utc_now(), **result)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def is_due(db: Session, target: models.Target) -> bool:
    last = (
        db.query(func.max(models.CheckResult.checked_at))
        .filter(models.CheckResult.target_id == target.id)
        .scalar()
    )
    if last is None:
        return True
    return (utc_now() - last).total_seconds() >= target.interval_seconds


def run_due_checks(db: Session) -> int:
    targets = db.query(models.Target).filter(models.Target.is_active.is_(True)).all()
    count = 0
    for target in targets:
        if is_due(db, target):
            run_check(db, target)
            count += 1
    return count


def build_status(db: Session, target: models.Target) -> dict:
    results = db.query(models.CheckResult).filter(models.CheckResult.target_id == target.id)
    total = results.count()
    up_count = results.filter(models.CheckResult.is_up.is_(True)).count()
    avg_latency = (
        db.query(func.avg(models.CheckResult.latency_ms))
        .filter(models.CheckResult.target_id == target.id, models.CheckResult.is_up.is_(True))
        .scalar()
    )
    last = results.order_by(models.CheckResult.id.desc()).first()

    if last is None:
        state = "unknown"
    elif not last.is_up:
        state = "down"
    elif last.latency_ms is not None and last.latency_ms >= target.warning_ms:
        state = "slow"
    else:
        state = "up"

    return {
        "target_id": target.id,
        "name": target.name,
        "address": target.address,
        "state": state,
        "last_checked_at": last.checked_at if last else None,
        "last_latency_ms": last.latency_ms if last else None,
        "avg_latency_ms": round(avg_latency, 1) if avg_latency is not None else None,
        "uptime_percent": round(up_count / total * 100, 2) if total else None,
        "total_checks": total,
    }