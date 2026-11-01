import csv
import io
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from . import models, schemas, services
from .database import engine, get_db
from .scheduler import start_scheduler, stop_scheduler

models.Base.metadata.create_all(bind=engine)

STATIC_DIR = Path(__file__).parent / "static"
STATE_PATTERN = "^(up|slow|critical|down|unknown)$"


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Network Quality Monitoring System", lifespan=lifespan)


def get_target_or_404(db: Session, target_id: int) -> models.Target:
    target = db.get(models.Target, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    return target


def all_status(db: Session, state: Optional[str] = None) -> list[dict]:
    targets = db.query(models.Target).order_by(models.Target.id).all()
    rows = [services.build_status(db, t) for t in targets]
    if state:
        rows = [r for r in rows if r["state"] == state]
    return rows


def csv_safe(value) -> str:
    """Stop spreadsheet programs from running a value that starts like a formula."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- Target management (Week 1) ----------

@app.post("/targets", response_model=schemas.TargetOut, status_code=201)
def create_target(data: schemas.TargetBase, db: Session = Depends(get_db)):
    if db.query(models.Target).filter(models.Target.name == data.name).first():
        raise HTTPException(status_code=409, detail="A target with this name already exists")
    target = models.Target(**data.model_dump())
    db.add(target)
    db.commit()
    db.refresh(target)
    return target


@app.get("/targets", response_model=list[schemas.TargetOut])
def list_targets(db: Session = Depends(get_db)):
    return db.query(models.Target).order_by(models.Target.id).all()


@app.get("/targets/{target_id}", response_model=schemas.TargetOut)
def get_target(target_id: int, db: Session = Depends(get_db)):
    return get_target_or_404(db, target_id)


@app.put("/targets/{target_id}", response_model=schemas.TargetOut)
def update_target(target_id: int, data: schemas.TargetBase, db: Session = Depends(get_db)):
    target = get_target_or_404(db, target_id)
    clash = (
        db.query(models.Target)
        .filter(models.Target.name == data.name, models.Target.id != target_id)
        .first()
    )
    if clash:
        raise HTTPException(status_code=409, detail="A target with this name already exists")
    for field, value in data.model_dump().items():
        setattr(target, field, value)
    db.commit()
    db.refresh(target)
    return target


@app.delete("/targets/{target_id}", status_code=204)
def delete_target(target_id: int, db: Session = Depends(get_db)):
    target = get_target_or_404(db, target_id)
    db.delete(target)
    db.commit()


# ---------- Checks and status (Week 2) ----------

@app.post("/targets/{target_id}/check", response_model=schemas.CheckResultOut, status_code=201)
def check_now(target_id: int, db: Session = Depends(get_db)):
    """Run one check right now (useful for testing and demos)."""
    target = get_target_or_404(db, target_id)
    return services.run_check(db, target)


@app.get("/targets/{target_id}/results", response_model=list[schemas.CheckResultOut])
def get_results(
    target_id: int,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    get_target_or_404(db, target_id)
    return (
        db.query(models.CheckResult)
        .filter(models.CheckResult.target_id == target_id)
        .order_by(models.CheckResult.id.desc())
        .limit(limit)
        .all()
    )


@app.get("/targets/{target_id}/status", response_model=schemas.TargetStatus)
def get_status(target_id: int, db: Session = Depends(get_db)):
    target = get_target_or_404(db, target_id)
    return services.build_status(db, target)


# ---------- Filter, events and report (Week 3) ----------

@app.get("/status", response_model=list[schemas.TargetStatus])
def get_all_status(
    state: Optional[str] = Query(None, pattern=STATE_PATTERN),
    db: Session = Depends(get_db),
):
    return all_status(db, state)


@app.get("/events", response_model=list[schemas.EventOut])
def list_events(
    level: Optional[str] = Query(None, pattern="^(warning|critical|recovered)$"),
    target_id: Optional[int] = None,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(models.Event, models.Target.name).join(
        models.Target, models.Event.target_id == models.Target.id
    )
    if level:
        query = query.filter(models.Event.level == level)
    if target_id is not None:
        query = query.filter(models.Event.target_id == target_id)
    rows = query.order_by(models.Event.id.desc()).limit(limit).all()
    return [
        schemas.EventOut(
            id=event.id,
            target_id=event.target_id,
            target_name=name,
            created_at=event.created_at,
            level=event.level,
            message=event.message,
        )
        for event, name in rows
    ]


@app.get("/report.csv")
def report_csv(
    state: Optional[str] = Query(None, pattern=STATE_PATTERN),
    db: Session = Depends(get_db),
):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "Name", "Address", "State", "Last checked (UTC)",
        "Last latency (ms)", "Average latency (ms)", "Uptime (%)", "Total checks",
    ])
    for r in all_status(db, state):
        writer.writerow([
            csv_safe(r["name"]),
            csv_safe(r["address"]),
            csv_safe(r["state"]),
            csv_safe(r["last_checked_at"].isoformat() if r["last_checked_at"] else ""),
            csv_safe(r["last_latency_ms"]),
            csv_safe(r["avg_latency_ms"]),
            csv_safe(r["uptime_percent"]),
            csv_safe(r["total_checks"]),
        ])
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="network-report.csv"'},
    )