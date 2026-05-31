from datetime import datetime, UTC

from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, Numeric, ForeignKey,
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
    # Promotion origin. "scraped" = a real UFCStats card (UFC/DWCS), "promoted" =
    # an upcoming UFC card, "fighter_history" = a non-UFC event (PRIDE, Strikeforce,
    # ONE, ...) that only appears referenced in a fighter's history. Only UFC events
    # feed the ELO/training universe — fighter_history events are excluded so ELO
    # matches the legacy backend. See DataStoreDB._load_event_dates.
    source = Column(String(20), nullable=True, default="scraped")
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


# ─── Betting ──────────────────────────────────────────
class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    cognito_sub = Column(String(64), nullable=False, unique=True, index=True)
    email = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class UserBet(Base):
    __tablename__ = "user_bet"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    fight_id = Column(Integer, ForeignKey("fight.id"), nullable=False)
    stake = Column(Numeric(12, 2), nullable=False)
    predicted_pick = Column(String(255), nullable=False)
    odds_taken_american = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="open")
    placed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    settled_at = Column(DateTime(timezone=True), nullable=True)


class Parlay(Base):
    __tablename__ = "parlay"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    parlay_type = Column(String(10), nullable=False)  # single|double|triple
    legs = Column(JSONB, nullable=False)
    stake = Column(Numeric(12, 2), nullable=False)
    payout = Column(Numeric(12, 2), nullable=True)
    status = Column(String(20), nullable=False, default="open")
    placed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    settled_at = Column(DateTime(timezone=True), nullable=True)


class BetConfig(Base):
    __tablename__ = "bet_config"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    params = Column(JSONB, nullable=False)
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_bet_config_user_name"),)


class UserPreference(Base):
    __tablename__ = "user_preference"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(100), nullable=False)
    value = Column(JSONB, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_user_pref"),)


class UserViewState(Base):
    __tablename__ = "user_view_state"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    view = Column(String(100), nullable=False)
    state = Column(JSONB, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    __table_args__ = (UniqueConstraint("user_id", "view", name="uq_user_view"),)


# ─── Lab single-tenant ────────────────────────────────
class LabPreference(Base):
    __tablename__ = "lab_preference"
    id = Column(Integer, primary_key=True)
    key = Column(String(100), nullable=False, unique=True)
    value = Column(JSONB, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class LabBetConfig(Base):
    __tablename__ = "lab_bet_config"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    params = Column(JSONB, nullable=False)
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


# ─── Experimentacion (solo lab) ───────────────────────
class HpSearchStudy(Base):
    __tablename__ = "hp_search_study"
    id = Column(Integer, primary_key=True)
    model_short = Column(String(50), nullable=False)
    feature_set = Column(String(10), nullable=False)
    feat_type = Column(String(10), nullable=False)
    dataset = Column(String(20), nullable=False)
    n_trials = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="running")
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    finished_at = Column(DateTime(timezone=True), nullable=True)
    params = Column(JSONB, nullable=True)


class HpSearchTrial(Base):
    __tablename__ = "hp_search_trial"
    id = Column(Integer, primary_key=True)
    study_id = Column(Integer, ForeignKey("hp_search_study.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    trial_idx = Column(Integer, nullable=False)
    params = Column(JSONB, nullable=False)
    value = Column(Float, nullable=True)
    # Per-trial CV metrics: mean_* (mean over folds, the objective space),
    # prod_* (last/production fold), realworld_* (held-out TTA eval), is_pareto.
    metrics = Column(JSONB, nullable=True)
    status = Column(String(20), nullable=False, default="running")


class ComboSearchStudy(Base):
    __tablename__ = "combo_search_study"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    status = Column(String(20), nullable=False, default="running")
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    finished_at = Column(DateTime(timezone=True), nullable=True)
    params = Column(JSONB, nullable=True)


class ComboSearchTrial(Base):
    __tablename__ = "combo_search_trial"
    id = Column(Integer, primary_key=True)
    study_id = Column(Integer, ForeignKey("combo_search_study.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    trial_idx = Column(Integer, nullable=False)
    params = Column(JSONB, nullable=False)
    value = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="running")


class BacktestRun(Base):
    __tablename__ = "backtest_run"
    id = Column(Integer, primary_key=True)
    strategy = Column(String(100), nullable=False)
    params = Column(JSONB, nullable=False)
    roi = Column(Float, nullable=True)
    sharpe = Column(Float, nullable=True)
    drawdown = Column(Float, nullable=True)
    sessions_used = Column(Integer, nullable=True)
    ran_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


# ─── Observabilidad ───────────────────────────────────
class ScrapingRun(Base):
    __tablename__ = "scraping_run"
    id = Column(Integer, primary_key=True)
    source = Column(String(20), nullable=False)   # ufcstats|tapology|fotos
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    finished_at = Column(DateTime(timezone=True), nullable=True)
    new_count = Column(Integer, nullable=False, default=0)
    updated_count = Column(Integer, nullable=False, default=0)
    error_msg = Column(Text, nullable=True)
    recent_event_names = Column(JSONB, nullable=True)


class PublishRun(Base):
    __tablename__ = "publish_run"
    id = Column(Integer, primary_key=True)
    model_version_id = Column(Integer, ForeignKey("model_version.id"), nullable=False, index=True)
    phase = Column(String(20), nullable=False)   # s3|sagemaker|rds_slice
    status = Column(String(20), nullable=False)
    payload_hash = Column(String(64), nullable=True)
    log_excerpt = Column(Text, nullable=True)
    ran_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class AppLog(Base):
    __tablename__ = "app_log"
    id = Column(Integer, primary_key=True)
    level = Column(String(10), nullable=False)    # debug|info|warn|error
    module = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    context = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
