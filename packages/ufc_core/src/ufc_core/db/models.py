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


class FightFeatures(Base):
    __tablename__ = "fight_features"
    id = Column(Integer, primary_key=True)
    fight_id = Column(Integer, ForeignKey("fight.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    feature_set = Column(String(10), nullable=False)
    vector = Column(JSONB, nullable=False)
    computed_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: datetime.now(UTC))
    before_event_date = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("fight_id", "feature_set", name="uq_fight_features_set"),
    )


class TapologyPicks(Base):
    __tablename__ = "tapology_picks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    fight_id = Column(Integer, ForeignKey("fight.id", ondelete="CASCADE"),
                      nullable=False, unique=True, index=True)
    total_picks = Column(Integer, nullable=False, default=0)
    fighter_a_id = Column(Integer, ForeignKey("fighter.id"), nullable=False)
    fighter_b_id = Column(Integer, ForeignKey("fighter.id"), nullable=False)
    fighter_a_win_pct = Column(Float, nullable=True)
    fighter_b_win_pct = Column(Float, nullable=True)
    fighter_a_methods = Column(JSONB, nullable=True)
    fighter_b_methods = Column(JSONB, nullable=True)
    matchup_url = Column(Text, nullable=True)
    source_event_url = Column(Text, nullable=True)
    scraped_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class TapologyEventMatch(Base):
    __tablename__ = "tapology_event_match"
    id = Column(Integer, primary_key=True)
    ufcstats_event_id = Column(Integer, ForeignKey("event.id", ondelete="CASCADE"),
                               nullable=False, index=True)
    tapology_slug = Column(String(255), nullable=False)
    confidence = Column(Float, nullable=True)
    resolved_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint("ufcstats_event_id", "tapology_slug",
                         name="uq_tap_event_match"),
    )


class Model(Base):
    __tablename__ = "model"
    id = Column(Integer, primary_key=True)
    short = Column(String(50), nullable=False, unique=True, index=True)
    family = Column(String(20), nullable=False)             # sklearn|pytorch
    default_feat_type = Column(String(10), nullable=False)  # 35f|52f
    description = Column(Text, nullable=True)


class ModelVersion(Base):
    __tablename__ = "model_version"
    id = Column(Integer, primary_key=True)
    model_id = Column(Integer, ForeignKey("model.id", ondelete="CASCADE"), nullable=False, index=True)
    version_idx = Column(Integer, nullable=False)
    feature_set = Column(String(10), nullable=False)
    hp_json = Column(JSONB, nullable=True)
    metrics_json = Column(JSONB, nullable=True)
    artifact_uri = Column(Text, nullable=False)
    sagemaker_model_name = Column(String(63), nullable=True)
    trained_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    was_production = Column(Boolean, nullable=False, default=False)
    starred = Column(Boolean, nullable=False, default=False)
    note = Column(Text, nullable=True)

    __table_args__ = (UniqueConstraint("model_id", "version_idx", name="uq_model_version_idx"),)


class ActiveModel(Base):
    __tablename__ = "active_model"
    model_id = Column(Integer, ForeignKey("model.id", ondelete="CASCADE"), primary_key=True)
    version_id = Column(Integer, ForeignKey("model_version.id"), nullable=False)
    activated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    sagemaker_target_model = Column(String(255), nullable=True)


class TrainingSession(Base):
    __tablename__ = "training_session"
    id = Column(Integer, primary_key=True)
    model_id = Column(Integer, ForeignKey("model.id"), nullable=True)
    request = Column(JSONB, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    finished_at = Column(DateTime(timezone=True), nullable=True)
    error_msg = Column(Text, nullable=True)
    result_version_id = Column(Integer, ForeignKey("model_version.id"), nullable=True)


class PredictionSession(Base):
    __tablename__ = "prediction_session"
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("event.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    source = Column(String(20), nullable=False)   # lab_preview|production
    status = Column(String(20), nullable=False, default="open")


class Prediction(Base):
    __tablename__ = "prediction"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("prediction_session.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    fight_id = Column(Integer, ForeignKey("fight.id"), nullable=False, index=True)
    model_short = Column(String(50), nullable=False)
    version_idx = Column(Integer, nullable=False)
    prob_f1 = Column(Float, nullable=False)
    prob_f2 = Column(Float, nullable=False)
    method_pred = Column(String(50), nullable=True)
    raw_response = Column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("session_id", "fight_id", "model_short",
                         name="uq_prediction_session_fight_model"),
    )


class PredictionCache(Base):
    __tablename__ = "prediction_cache"
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("event.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    model_version_id = Column(Integer, ForeignKey("model_version.id"), nullable=False)
    payload = Column(JSONB, nullable=False)
    computed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    expires_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("event_id", "model_version_id", name="uq_prediction_cache_ev_mv"),
    )
