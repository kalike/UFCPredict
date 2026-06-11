"""
UFC Predictor — Feature Engineering Pipeline.

Builds fighter histories from JSON data and computes all features
(26 base STAT_COLS → 35 delta features + 52 individual features).
"""

from datetime import datetime

import numpy as np
import pandas as pd

from ufc_core.parsers import (
    aggregate_stats,
    american_to_decimal,
    extract_fight_stats,
    parse_dob,
    parse_height_inches,
    parse_reach_inches,
)

# Stance encoding: Southpaw=1, Switch=0.5, everything else (Orthodox/unknown)=0
_STANCE_MAP = {"Southpaw": 1.0, "Switch": 0.5}

# The 26 base statistical columns produced by aggregate_stats()
STAT_COLS = [
    "win_rate",
    "total_fights",
    "kd_differential",
    "sig_str_accuracy",
    "sig_str_defense",
    "td_accuracy",
    "td_defense",
    "ctrl_time_differential",
    "avg_sub_attempts",
    "avg_reversals",
    "ko_rate",
    "sub_rate",
    "dec_rate",
    "avg_sig_str_landed",
    "avg_sig_str_received",
    "avg_td_landed",
    "avg_td_received",
    "recent_win_rate",
    "win_streak",
    "lose_streak",
    "avg_head_landed",
    "avg_body_landed",
    "avg_leg_landed",
    "avg_distance_landed",
    "avg_clinch_landed",
    "avg_ground_landed",
]


def build_fighter_histories(fighters_raw: list[dict]) -> dict[str, list[dict]]:
    """Build a dict mapping fighter name → list of per-fight stat dicts.

    Each entry includes the parsed fight stats plus result, opponent,
    event, and method metadata.
    """
    histories: dict[str, list[dict]] = {}
    for ftr in fighters_raw:
        name = ftr["name"]
        history = []
        for fight in ftr.get("fights", []):
            try:
                entry = extract_fight_stats(fight, name)
                entry["result"] = 1 if fight.get("result") == "win" else 0
                entry["opponent"] = fight.get("opponent", "")
                entry["event"] = fight.get("event", "")
                entry["method"] = fight.get("method", "")
                history.append(entry)
            except Exception:
                pass
        histories[name] = history
    return histories


def compute_fight_features(
    f1_name: str,
    f2_name: str,
    fighter_histories: dict[str, list[dict]],
    fighter_lookup: dict[str, dict],
    event_dates: dict[str, datetime],
    event: str = "",
    odds_f1_american: int | None = None,
    odds_f2_american: int | None = None,
    result: int | float = np.nan,
    before_event_date: datetime | None = None,
    event_date: datetime | None = None,
    elo_pre_fight: dict[tuple[str, str], float] | None = None,
    elo_ratings: dict[str, float] | None = None,
    base_elo: float = 1500,
    tapology_picks: dict | None = None,
) -> dict | None:
    """Compute the full feature row for a single fight.

    Returns None if both fighters have no history.
    Returns a dict with all 35 delta features, 52 individual features,
    and metadata columns.

    If *before_event_date* is given (Point-in-Time mode), only fights
    that occurred strictly before that date are considered when
    aggregating each fighter's career statistics.

    *event_date* is always used as temporal anchor for days_inactive
    and age, even without full PIT mode. Falls back to now() for live
    predictions.
    """
    # Normalize tz-aware anchors to naive. event_dates (and the datetime.min /
    # datetime.now fallbacks below) are naive throughout the pipeline (see
    # DataStoreDB, which strips tzinfo), so an aware Event.date passed by a
    # caller would raise "can't compare offset-naive and offset-aware" on every
    # date comparison.
    if event_date is not None and event_date.tzinfo is not None:
        event_date = event_date.replace(tzinfo=None)
    if before_event_date is not None and before_event_date.tzinfo is not None:
        before_event_date = before_event_date.replace(tzinfo=None)

    # Temporal anchor: event_date (hybrid) > before_event_date (full PIT) > now()
    ref_date = event_date or before_event_date or datetime.now()

    hist_f1 = fighter_histories.get(f1_name, [])
    hist_f2 = fighter_histories.get(f2_name, [])

    # PIT filtering: keep only fights before the event date.
    # Fights with unknown event dates (e.g. DWCS) are assumed to have
    # occurred before the current event (they precede a fighter's UFC debut).
    if before_event_date is not None:
        hist_f1 = [
            h
            for h in hist_f1
            if event_dates.get(h.get("event", ""), datetime.min) < before_event_date
        ]
        hist_f2 = [
            h
            for h in hist_f2
            if event_dates.get(h.get("event", ""), datetime.min) < before_event_date
        ]

    if len(hist_f1) == 0 and len(hist_f2) == 0:
        return None

    # If one fighter has no history, use zero stats
    stats_f1 = aggregate_stats(hist_f1) if hist_f1 else {col: 0 for col in STAT_COLS}
    stats_f2 = aggregate_stats(hist_f2) if hist_f2 else {col: 0 for col in STAT_COLS}

    row: dict = {
        "fighter_1": f1_name,
        "fighter_2": f2_name,
        "event": event,
        "result": result,
        "odds_f1": american_to_decimal(odds_f1_american)
        if odds_f1_american is not None
        else np.nan,
        "odds_f2": american_to_decimal(odds_f2_american)
        if odds_f2_american is not None
        else np.nan,
        "odds_f1_american": odds_f1_american,
        "odds_f2_american": odds_f2_american,
    }

    # f1_*, f2_* (for 52f model)
    for col in STAT_COLS:
        row[f"f1_{col}"] = stats_f1[col]
        row[f"f2_{col}"] = stats_f2[col]

    # delta_* (for 35f models)
    for col in STAT_COLS:
        row[f"delta_{col}"] = stats_f1[col] - stats_f2[col]

    # Derived features — Phase 1
    row["f1_momentum"] = stats_f1["recent_win_rate"] - stats_f1["win_rate"]
    row["f2_momentum"] = stats_f2["recent_win_rate"] - stats_f2["win_rate"]
    row["delta_momentum"] = row["f1_momentum"] - row["f2_momentum"]

    row["f1_finish_rate"] = stats_f1["ko_rate"] + stats_f1["sub_rate"]
    row["f2_finish_rate"] = stats_f2["ko_rate"] + stats_f2["sub_rate"]
    row["delta_finish_rate"] = row["f1_finish_rate"] - row["f2_finish_rate"]

    f1_tf = stats_f1["total_fights"]
    f2_tf = stats_f2["total_fights"]
    row["f1_exp_ratio"] = f1_tf / (f1_tf + f2_tf) if (f1_tf + f2_tf) > 0 else 0.5
    row["f2_exp_ratio"] = f2_tf / (f1_tf + f2_tf) if (f1_tf + f2_tf) > 0 else 0.5
    row["delta_exp_ratio"] = row["f1_exp_ratio"] - row["f2_exp_ratio"]

    row["f1_striking_volume"] = stats_f1["avg_sig_str_landed"] + stats_f1["avg_sig_str_received"]
    row["f2_striking_volume"] = stats_f2["avg_sig_str_landed"] + stats_f2["avg_sig_str_received"]
    row["delta_striking_volume"] = row["f1_striking_volume"] - row["f2_striking_volume"]

    # Derived features — Phase 2 (physical)
    f1_data = fighter_lookup.get(f1_name, {})
    f2_data = fighter_lookup.get(f2_name, {})

    f1_h = parse_height_inches(f1_data.get("stats", {}).get("Height", "--"))
    f2_h = parse_height_inches(f2_data.get("stats", {}).get("Height", "--"))
    row["f1_height_in"] = f1_h
    row["f2_height_in"] = f2_h
    row["delta_height_in"] = (
        (f1_h - f2_h)
        if not (np.isnan(f1_h) if isinstance(f1_h, float) else False)
        and not (np.isnan(f2_h) if isinstance(f2_h, float) else False)
        else 0
    )

    f1_r = parse_reach_inches(f1_data.get("stats", {}).get("Reach", "--"))
    f2_r = parse_reach_inches(f2_data.get("stats", {}).get("Reach", "--"))
    row["f1_reach_in"] = f1_r
    row["f2_reach_in"] = f2_r
    row["delta_reach_in"] = (
        (f1_r - f2_r)
        if not (np.isnan(f1_r) if isinstance(f1_r, float) else False)
        and not (np.isnan(f2_r) if isinstance(f2_r, float) else False)
        else 0
    )

    f1_dob = parse_dob(f1_data.get("stats", {}).get("DOB", "--"))
    f2_dob = parse_dob(f2_data.get("stats", {}).get("DOB", "--"))
    f1_age = (ref_date - f1_dob).days / 365.25 if f1_dob else np.nan
    f2_age = (ref_date - f2_dob).days / 365.25 if f2_dob else np.nan
    row["f1_age"] = f1_age
    row["f2_age"] = f2_age
    row["delta_age"] = (f1_age - f2_age) if not np.isnan(f1_age) and not np.isnan(f2_age) else 0

    def get_days_inactive(fname: str) -> float:
        hist = fighter_histories.get(fname, [])
        # PIT: only consider fights before ref_date
        past_fights = [
            h for h in hist
            if event_dates.get(h.get("event", ""), ref_date) < ref_date
        ]
        if not past_fights:
            return np.nan
        # Find the most recent fight date before ref_date
        last_dt = None
        for h in past_fights:
            dt = event_dates.get(h.get("event", ""))
            if dt is not None and (last_dt is None or dt > last_dt):
                last_dt = dt
        if last_dt is None:
            return np.nan
        return (ref_date - last_dt).days

    f1_days = get_days_inactive(f1_name)
    f2_days = get_days_inactive(f2_name)
    row["f1_days_inactive"] = f1_days
    row["f2_days_inactive"] = f2_days
    row["delta_days_inactive"] = (
        (f1_days - f2_days) if not np.isnan(f1_days) and not np.isnan(f2_days) else 0
    )

    # Stance (guard)
    f1_stance = f1_data.get("stats", {}).get("STANCE", "").strip()
    f2_stance = f2_data.get("stats", {}).get("STANCE", "").strip()
    f1_sp = _STANCE_MAP.get(f1_stance, 0.0)
    f2_sp = _STANCE_MAP.get(f2_stance, 0.0)
    row["f1_southpaw"] = f1_sp
    row["f2_southpaw"] = f2_sp
    row["delta_southpaw"] = f1_sp - f2_sp

    # --- V2 features (always PIT via ref_date) ---

    def _pit_history(fname: str) -> list[dict]:
        """Fighter history filtered to fights before ref_date."""
        hist = fighter_histories.get(fname, [])
        return [
            h for h in hist
            if event_dates.get(h.get("event", ""), ref_date) < ref_date
        ]

    pit_f1 = _pit_history(f1_name)
    pit_f2 = _pit_history(f2_name)

    # Feature 1: chin_damage_score — recency-weighted accumulated damage
    _CHIN_DECAY = 0.85
    _KO_LOSS_W = 3.0
    _KD_W = 1.0

    def _chin_damage(hist: list[dict]) -> float:
        if not hist:
            return 0.0
        raw, wsum = 0.0, 0.0
        for i, f in enumerate(hist):
            w = _CHIN_DECAY ** i
            is_ko_loss = f["result"] == 0 and "ko" in f.get("method", "").lower()
            raw += w * (_KO_LOSS_W * int(is_ko_loss) + _KD_W * f.get("kd_received", 0))
            wsum += w
        return raw / wsum if wsum > 0 else 0.0

    row["f1_chin_damage_score"] = _chin_damage(pit_f1)
    row["f2_chin_damage_score"] = _chin_damage(pit_f2)
    row["delta_chin_damage_score"] = row["f1_chin_damage_score"] - row["f2_chin_damage_score"]

    # Feature 2: recent_damage_trend — recent vs career sig strikes received
    def _damage_trend(hist: list[dict]) -> float:
        if len(hist) < 3:
            return 0.0
        career_avg = np.mean([f["sig_str_received"] for f in hist])
        recent_avg = np.mean([f["sig_str_received"] for f in hist[:3]])
        return (recent_avg / career_avg - 1.0) if career_avg > 0 else 0.0

    row["f1_recent_damage_trend"] = _damage_trend(pit_f1)
    row["f2_recent_damage_trend"] = _damage_trend(pit_f2)
    row["delta_recent_damage_trend"] = (
        row["f1_recent_damage_trend"] - row["f2_recent_damage_trend"]
    )

    # Features 3-4: Strength of Schedule (avg_opp_elo, recent_opp_elo, avg_opp_elo_of_losses)
    _base = base_elo

    def _compute_sos(hist: list[dict]) -> tuple[float, float, float]:
        if not hist:
            return _base, _base, _base
        opp_elos: list[float] = []
        for h in hist:
            opp, ev = h.get("opponent", ""), h.get("event", "")
            if elo_pre_fight and (opp, ev) in elo_pre_fight:
                opp_elos.append(elo_pre_fight[(opp, ev)])
            elif elo_ratings and opp in elo_ratings:
                opp_elos.append(elo_ratings[opp])
            else:
                opp_elos.append(_base)
        avg_all = float(np.mean(opp_elos))
        avg_recent = float(np.mean(opp_elos[:5]))
        loss_elos = [opp_elos[i] for i, h in enumerate(hist) if h["result"] == 0]
        avg_losses = float(np.mean(loss_elos)) if loss_elos else _base
        return avg_all, avg_recent, avg_losses

    f1_sos = _compute_sos(pit_f1)
    f2_sos = _compute_sos(pit_f2)

    for idx, suffix in enumerate(["avg_opp_elo", "recent_opp_elo", "avg_opp_elo_of_losses"]):
        row[f"f1_{suffix}"] = f1_sos[idx]
        row[f"f2_{suffix}"] = f2_sos[idx]
        row[f"delta_{suffix}"] = f1_sos[idx] - f2_sos[idx]

    # --- V7: Tapology community picks ---
    if tapology_picks is not None and tapology_picks.get("total_picks", 0) > 0:
        total = int(tapology_picks["total_picks"])
        f1_pct = float(tapology_picks.get("fighter_1_win_pct", 0.5))
        f2_pct = float(tapology_picks.get("fighter_2_win_pct", 0.5))
        row["f1_tap_win_pct"] = f1_pct
        row["f2_tap_win_pct"] = f2_pct
        row["delta_tap_win_pct"] = f1_pct - f2_pct
        row["tap_consensus_strength"] = abs(0.5 - f1_pct)
        row["tap_log_volume"] = float(np.log1p(total))
        row["tap_has_data"] = 1
    else:
        row["f1_tap_win_pct"] = 0.5
        row["f2_tap_win_pct"] = 0.5
        row["delta_tap_win_pct"] = 0.0
        row["tap_consensus_strength"] = 0.0
        row["tap_log_volume"] = 0.0
        row["tap_has_data"] = 0

    return row


def compute_features_for_fights(
    fights: list[dict],
    fighter_histories: dict[str, list[dict]],
    fighter_lookup: dict[str, dict],
    event_dates: dict[str, datetime],
    elo_ratings: dict[str, float] | None = None,
    base_elo: float = 1500,
    elo_pre_fight: dict[tuple[str, str], float] | None = None,
    event_date: datetime | None = None,
    before_event_date: datetime | None = None,
    tapology_picks_by_key: dict[tuple[str, frozenset], dict] | None = None,
) -> pd.DataFrame:
    """Compute features for a list of fights and return as DataFrame.

    Each fight dict must have keys:
        - fighter_1, fighter_2, event
        - odds_f1_american, odds_f2_american (optional)
        - result (optional, for past fights)

    tapology_picks_by_key maps (event_name, frozenset({f1, f2})) to a picks
    dict. Pre-oriented format (has "fighter_1_win_pct") is passed through
    directly. Repo format (Task 3) with "fighter_a_name" is ignored for now.
    """
    rows = []
    skipped = []
    picks_lookup = tapology_picks_by_key or {}

    for fight in fights:
        f1 = fight.get("fighter_1") or fight.get("f1", "")
        f2 = fight.get("fighter_2") or fight.get("f2", "")
        ev = fight.get("event", "")
        picks_entry = picks_lookup.get((ev, frozenset({f1, f2})))
        # Two formats accepted:
        #   1. Pre-oriented {total_picks, fighter_1_win_pct, fighter_2_win_pct}
        #   2. Repo format {total_picks, fighter_a_name, fighter_b_name, fighter_a_win_pct, fighter_b_win_pct}
        if picks_entry is None:
            picks = None
        elif "fighter_a_name" in picks_entry:
            from ufc_core.tapology.picks_repo import orient_picks_for_fight
            picks = orient_picks_for_fight(picks_entry, f1)
        else:
            picks = picks_entry  # already pre-oriented

        row = compute_fight_features(
            f1_name=f1,
            f2_name=f2,
            fighter_histories=fighter_histories,
            fighter_lookup=fighter_lookup,
            event_dates=event_dates,
            event=ev,
            odds_f1_american=fight.get("odds_f1_american") or fight.get("odds1"),
            odds_f2_american=fight.get("odds_f2_american") or fight.get("odds2"),
            result=fight.get("result", np.nan),
            elo_pre_fight=elo_pre_fight,
            elo_ratings=elo_ratings,
            base_elo=base_elo,
            event_date=event_date,
            before_event_date=before_event_date,
            tapology_picks=picks,
        )

        if row is None:
            skipped.append(f"{f1} vs {f2} (ambos sin historial)")
            continue
        rows.append(row)

    df = pd.DataFrame(rows)

    # Add ELO if available
    if elo_ratings is not None and len(df) > 0:
        df["f1_elo"] = df["fighter_1"].map(lambda n: elo_ratings.get(n, base_elo))
        df["f2_elo"] = df["fighter_2"].map(lambda n: elo_ratings.get(n, base_elo))
        df["delta_elo"] = df["f1_elo"] - df["f2_elo"]

    return df, skipped
