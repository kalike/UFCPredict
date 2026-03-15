from datetime import datetime, UTC

from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, ForeignKey,
    DateTime, UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from ufc_core.db.base import Base


class Event(Base):
    __tablename__ = "event"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    date = Column(DateTime(timezone=True), nullable=True)
    location = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False, default="scheduled")  # scheduled|completed|cancelled
    is_dwcs = Column(Boolean, nullable=False, default=False)
    source_url = Column(Text, nullable=True)


class Fighter(Base):
    __tablename__ = "fighter"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, index=True)
    slug = Column(String(255), nullable=False, unique=True)
    ufcstats_url = Column(Text, nullable=False, unique=True)
    tapology_url = Column(Text, nullable=True)
    record = Column(String(20), nullable=True)
    stance = Column(String(20), nullable=True)
    height_cm = Column(Float, nullable=True)
    reach_cm = Column(Float, nullable=True)
    dob = Column(DateTime(timezone=True), nullable=True)
    photo_url = Column(Text, nullable=True)
    last_scraped_at = Column(DateTime(timezone=True), nullable=True)


class Fight(Base):
    __tablename__ = "fight"
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("event.id", ondelete="CASCADE"), nullable=False, index=True)
    fighter_1_id = Column(Integer, ForeignKey("fighter.id"), nullable=False)
    fighter_2_id = Column(Integer, ForeignKey("fighter.id"), nullable=False)
    weight_class = Column(String(50), nullable=True)
    card_position = Column(String(20), nullable=True)   # main|co_main|prelim|early_prelim
    scheduled_rounds = Column(Integer, nullable=True)
    result = Column(String(20), nullable=True)
    method = Column(String(50), nullable=True)
    round = Column(Integer, nullable=True)
    time = Column(String(10), nullable=True)
    odds_f1_american = Column(Integer, nullable=True)
    odds_f2_american = Column(Integer, nullable=True)
    real_winner = Column(String(255), nullable=True)
    fight_order = Column(Integer, nullable=True)

    event = relationship("Event")
    fighter_1 = relationship("Fighter", foreign_keys=[fighter_1_id])
    fighter_2 = relationship("Fighter", foreign_keys=[fighter_2_id])

    __table_args__ = (
        UniqueConstraint("event_id", "fighter_1_id", "fighter_2_id", name="uq_fight_event_pair"),
        Index("ix_fight_event_order", "event_id", "fight_order"),
    )


class FighterRaw(Base):
    __tablename__ = "fighter_raw"
    id = Column(Integer, primary_key=True)
    fighter_id = Column(Integer, ForeignKey("fighter.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    scraped_at = Column(DateTime(timezone=True), nullable=False,
                       default=lambda: datetime.now(UTC))
    payload = Column(JSONB, nullable=False)
