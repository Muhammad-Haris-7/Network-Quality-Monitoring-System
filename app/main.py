from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from . import models, schemas, services
from .database import engine, get_db
from .scheduler import start_scheduler, stop_scheduler

models.Base.metadata.create_all(bind=engine)


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


@app.get("/status", response_model=list[schemas.TargetStatus])
def get_all_status(db: Session = Depends(get_db)):
    targets = db.query(models.Target).order_by(models.Target.id).all()
    return [services.build_status(db, t) for t in targets]