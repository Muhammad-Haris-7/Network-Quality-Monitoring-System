from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from . import models, schemas
from .database import engine, get_db

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Network Quality Monitoring System")


@app.get("/health")
def health():
    return {"status": "ok"}


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
    target = db.get(models.Target, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    return target


@app.put("/targets/{target_id}", response_model=schemas.TargetOut)
def update_target(target_id: int, data: schemas.TargetBase, db: Session = Depends(get_db)):
    target = db.get(models.Target, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
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
    target = db.get(models.Target, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    db.delete(target)
    db.commit()