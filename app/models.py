from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
)
from sqlalchemy.orm import relationship
from .database import Base


class Target(Base):
    __tablename__ = "targets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    address = Column(String(255), nullable=False)
    check_type = Column(String(10), nullable=False, default="http")  # http or ping
    interval_seconds = Column(Integer, nullable=False, default=60)
    warning_ms = Column(Integer, nullable=False, default=500)
    critical_ms = Column(Integer, nullable=False, default=2000)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    results = relationship("CheckResult", back_populates="target",
                           cascade="all, delete-orphan")
    events = relationship("Event", back_populates="target",
                          cascade="all, delete-orphan")


class CheckResult(Base):
    """One row per check. Filled in Week 2."""
    __tablename__ = "check_results"

    id = Column(Integer, primary_key=True, index=True)
    target_id = Column(Integer, ForeignKey("targets.id"), nullable=False, index=True)
    checked_at = Column(DateTime, default=datetime.utcnow, index=True)
    is_up = Column(Boolean, nullable=False)
    status_code = Column(Integer, nullable=True)
    latency_ms = Column(Float, nullable=True)
    error = Column(Text, nullable=True)

    target = relationship("Target", back_populates="results")


class Event(Base):
    """Threshold events (warning, critical, recovered). Filled in Week 3."""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    target_id = Column(Integer, ForeignKey("targets.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    level = Column(String(20), nullable=False)  # warning, critical, recovered
    message = Column(Text, nullable=False)

    target = relationship("Target", back_populates="events")