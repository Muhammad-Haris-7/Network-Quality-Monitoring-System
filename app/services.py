from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models
from .checker import check_http, check_ping


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def evaluate(target: models.Target, is_up: bool, latency_ms):
    """Return (state, level) for one check result.

    state: up, slow, critical, down
    level: ok, warning, critical
    """
    if not is_up:
        return "down", "critical"
    if latency_ms is not None:
        if latency_ms >= target.critical_ms:
            return "critical", "critical"
        if latency_ms >= target.warning_ms:
            return "slow", "warning"
    return "up", "ok"


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


def _event_message(target: models.Target, level: str, result: dict) -> str:
    if not result["is_up"]:
        return f"{target.name} is unreachable ({result['error'] or 'no response'})"
    latency = result["latency_ms"]
    if level == "critical":
        return (f"{target.name} response time {latency} ms is above the "
                f"critical threshold ({target.critical_ms} ms)")
    if level == "warning":
        return (f"{target.name} response time {latency} ms is above the "
                f"warning threshold ({target.warning_ms} ms)")
    suffix = f" ({latency} ms)" if latency is not None else ""
    return f"{target.name} has recovered{suffix}"


def record_event_if_changed(db: Session, target: models.Target, previous, result: dict):
    """Create an event only when the level changes, so repeated checks do not spam the log."""
    previous_level = "ok"
    if previous is not None:
        _, previous_level = evaluate(target, previous.is_up, previous.latency_ms)
    _, new_level = evaluate(target, result["is_up"], result["latency_ms"])
    if new_level == previous_level:
        return None

    level = "recovered" if new_level == "ok" else new_level
    event = models.Event(
        target_id=target.id,
        created_at=utc_now(),
        level=level,
        message=_event_message(target, level, result),
    )
    db.add(event)
    return event


def run_check(db: Session, target: models.Target) -> models.CheckResult:
    previous = (
        db.query(models.CheckResult)
        .filter(models.CheckResult.target_id == target.id)
        .order_by(models.CheckResult.id.desc())
        .first()
    )
    result = perform_check(target)
    row = models.CheckResult(target_id=target.id, checked_at=utc_now(), **result)
    db.add(row)
    record_event_if_changed(db, target, previous, result)
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

    state = "unknown" if last is None else evaluate(target, last.is_up, last.latency_ms)[0]

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