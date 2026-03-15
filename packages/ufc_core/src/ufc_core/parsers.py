"""
UFC Predictor — Parsing functions for fight statistics.

Extracted from NB10 Cell 4 (extract_fight_stats FIXED version).
Handles the combined-field JSON format where both fighters' stats
are concatenated in a single string per field.
"""

import re
from datetime import datetime

import numpy as np

# ---------------------------------------------------------------------------
# Basic parsers
# ---------------------------------------------------------------------------


def parse_pair(text: str) -> tuple[int, int]:
    """Parse 'X of Y' -> (X, Y)."""
    if not text or text == "---":
        return (0, 0)
    parts = text.split(" of ")
    if len(parts) == 2:
        try:
            return (int(parts[0]), int(parts[1]))
        except Exception:
            return (0, 0)
    return (0, 0)


def parse_ctrl_time(text: str) -> int:
    """Parse 'M:SS' -> seconds."""
    if not text or text == "---":
        return 0
    parts = text.split(":")
    try:
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Combined-field helpers (both fighters in one string)
# ---------------------------------------------------------------------------


def _split_pair_combined(text: str) -> list[tuple[int, int]]:
    """Split 'X1 of Y1 X2 of Y2' -> [(X1,Y1), (X2,Y2)]."""
    if not text or text == "---":
        return [(0, 0), (0, 0)]
    nums = re.findall(r"\d+", text)
    if len(nums) >= 4:
        return [(int(nums[0]), int(nums[1])), (int(nums[2]), int(nums[3]))]
    return [(0, 0), (0, 0)]


def _split_single_combined(text: str) -> list[int]:
    """Split 'V1 V2' -> [V1, V2]."""
    if not text or text == "---":
        return [0, 0]
    nums = re.findall(r"\d+", text)
    if len(nums) >= 2:
        return [int(nums[0]), int(nums[1])]
    return [0, 0]


def _split_ctrl_combined(text: str) -> list[int]:
    """Split 'M1:SS1 M2:SS2' -> [secs1, secs2]."""
    if not text or text == "---":
        return [0, 0]
    parts = text.strip().split()
    results = [parse_ctrl_time(p) for p in parts]
    return results[:2] if len(results) >= 2 else [0, 0]


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------

_ZEROS = {
    "kd_landed": 0,
    "kd_received": 0,
    "sig_str_landed": 0,
    "sig_str_attempted": 0,
    "sig_str_received": 0,
    "sig_str_received_attempted": 0,
    "td_landed": 0,
    "td_attempted": 0,
    "td_received": 0,
    "td_received_attempted": 0,
    "sub_att": 0,
    "reversals": 0,
    "ctrl_seconds": 0,
    "opp_ctrl_seconds": 0,
    "head_landed": 0,
    "body_landed": 0,
    "leg_landed": 0,
    "distance_landed": 0,
    "clinch_landed": 0,
    "ground_landed": 0,
}


def extract_fight_stats(fight_dict: dict, fighter_name: str) -> dict:
    """Extract per-fighter stats from a fight JSON entry.

    The JSON structure has combined fields:
        fight_dict['details']['tables']['totals'][0] = {
            'Fighter': 'Name1 Name2', 'KD': '0 1', 'Sig. str.': '9 of 17 28 of 48', ...
        }
    Both fighters are concatenated in each field.
    """
    tables = fight_dict.get("details", {}).get("tables", {})
    totals_list = tables.get("totals", [])
    sig_list = tables.get("significant_strikes", [])

    if not totals_list:
        return dict(_ZEROS)

    totals = totals_list[0]
    sig = sig_list[0] if sig_list else {}

    # Determine if the fighter is first or second in the combined fields
    fighter_field = totals.get("Fighter", "")
    is_first = fighter_field.strip().lower().startswith(fighter_name.strip().lower())
    idx = 0 if is_first else 1
    opp = 1 - idx

    # --- Totals ---
    kd = _split_single_combined(totals.get("KD", "0 0"))
    sig_str = _split_pair_combined(totals.get("Sig. str.", ""))
    td = _split_pair_combined(totals.get("Td", ""))
    sub = _split_single_combined(totals.get("Sub. att", "0 0"))
    rev = _split_single_combined(totals.get("Rev.", "0 0"))
    ctrl = _split_ctrl_combined(totals.get("Ctrl", "0:00 0:00"))

    # --- Significant strikes by position ---
    head = _split_pair_combined(sig.get("Head", ""))
    body = _split_pair_combined(sig.get("Body", ""))
    leg = _split_pair_combined(sig.get("Leg", ""))
    dist = _split_pair_combined(sig.get("Distance", ""))
    clin = _split_pair_combined(sig.get("Clinch", ""))
    gnd = _split_pair_combined(sig.get("Ground", ""))

    return {
        "kd_landed": kd[idx],
        "kd_received": kd[opp],
        "sig_str_landed": sig_str[idx][0],
        "sig_str_attempted": sig_str[idx][1],
        "sig_str_received": sig_str[opp][0],
        "sig_str_received_attempted": sig_str[opp][1],
        "td_landed": td[idx][0],
        "td_attempted": td[idx][1],
        "td_received": td[opp][0],
        "td_received_attempted": td[opp][1],
        "sub_att": sub[idx],
        "reversals": rev[idx],
        "ctrl_seconds": ctrl[idx],
        "opp_ctrl_seconds": ctrl[opp],
        "head_landed": head[idx][0],
        "body_landed": body[idx][0],
        "leg_landed": leg[idx][0],
        "distance_landed": dist[idx][0],
        "clinch_landed": clin[idx][0],
        "ground_landed": gnd[idx][0],
    }


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def aggregate_stats(fight_list: list[dict]) -> dict:
    """Aggregate per-fight stats into career summary statistics."""
    n = len(fight_list)
    if n == 0:
        return {
            k: 0
            for k in [
                "total_fights",
                "wins",
                "losses",
                "win_rate",
                "avg_kd_landed",
                "avg_kd_received",
                "kd_differential",
                "sig_str_accuracy",
                "sig_str_defense",
                "td_accuracy",
                "td_defense",
                "avg_ctrl_time",
                "avg_opp_ctrl_time",
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
        }

    def avg(key):
        return np.mean([f[key] for f in fight_list])

    wins = sum(1 for f in fight_list if f["result"] == 1)
    losses = n - wins

    total_sig_a = sum(f["sig_str_attempted"] for f in fight_list)
    total_sig_l = sum(f["sig_str_landed"] for f in fight_list)
    sig_str_accuracy = total_sig_l / total_sig_a if total_sig_a > 0 else 0

    total_sig_ra = sum(f["sig_str_received_attempted"] for f in fight_list)
    total_sig_r = sum(f["sig_str_received"] for f in fight_list)
    sig_str_defense = 1 - (total_sig_r / total_sig_ra) if total_sig_ra > 0 else 0

    total_td_a = sum(f["td_attempted"] for f in fight_list)
    total_td_l = sum(f["td_landed"] for f in fight_list)
    td_accuracy = total_td_l / total_td_a if total_td_a > 0 else 0

    total_td_ra = sum(f["td_received_attempted"] for f in fight_list)
    total_td_r = sum(f["td_received"] for f in fight_list)
    td_defense = 1 - (total_td_r / total_td_ra) if total_td_ra > 0 else 0

    ko_wins = sum(1 for f in fight_list if f["result"] == 1 and "ko" in f.get("method", "").lower())
    sub_wins = sum(
        1 for f in fight_list if f["result"] == 1 and "sub" in f.get("method", "").lower()
    )
    dec_wins = sum(
        1 for f in fight_list if f["result"] == 1 and "dec" in f.get("method", "").lower()
    )
    ko_losses = sum(1 for f in fight_list if f["result"] == 0 and "ko" in f.get("method", "").lower())
    sub_losses = sum(
        1 for f in fight_list if f["result"] == 0 and "sub" in f.get("method", "").lower()
    )
    dec_losses = sum(
        1 for f in fight_list if f["result"] == 0 and "dec" in f.get("method", "").lower()
    )

    recent = fight_list[:5]
    recent_win_rate = sum(1 for f in recent if f["result"] == 1) / len(recent)

    streak = 0
    streak_type = fight_list[0]["result"] if fight_list else 0
    for f in fight_list:
        if f["result"] == streak_type:
            streak += 1
        else:
            break
    win_streak = streak if streak_type == 1 else 0
    lose_streak = streak if streak_type == 0 else 0

    return {
        "total_fights": n,
        "wins": wins,
        "losses": losses,
        "win_rate": wins / n,
        "avg_kd_landed": avg("kd_landed"),
        "avg_kd_received": avg("kd_received"),
        "kd_differential": avg("kd_landed") - avg("kd_received"),
        "sig_str_accuracy": sig_str_accuracy,
        "sig_str_defense": sig_str_defense,
        "td_accuracy": td_accuracy,
        "td_defense": td_defense,
        "avg_ctrl_time": avg("ctrl_seconds"),
        "avg_opp_ctrl_time": avg("opp_ctrl_seconds"),
        "ctrl_time_differential": avg("ctrl_seconds") - avg("opp_ctrl_seconds"),
        "avg_sub_attempts": avg("sub_att"),
        "avg_reversals": avg("reversals"),
        "ko_rate": ko_wins / wins if wins > 0 else 0,
        "sub_rate": sub_wins / wins if wins > 0 else 0,
        "dec_rate": dec_wins / wins if wins > 0 else 0,
        "ko_wins": ko_wins,
        "sub_wins": sub_wins,
        "dec_wins": dec_wins,
        "ko_losses": ko_losses,
        "sub_losses": sub_losses,
        "dec_losses": dec_losses,
        "avg_sig_str_landed": avg("sig_str_landed"),
        "avg_sig_str_received": avg("sig_str_received"),
        "avg_td_landed": avg("td_landed"),
        "avg_td_received": avg("td_received"),
        "recent_win_rate": recent_win_rate,
        "win_streak": win_streak,
        "lose_streak": lose_streak,
        "avg_head_landed": avg("head_landed"),
        "avg_body_landed": avg("body_landed"),
        "avg_leg_landed": avg("leg_landed"),
        "avg_distance_landed": avg("distance_landed"),
        "avg_clinch_landed": avg("clinch_landed"),
        "avg_ground_landed": avg("ground_landed"),
    }


# ---------------------------------------------------------------------------
# Physical attribute parsers
# ---------------------------------------------------------------------------


def parse_height_inches(h_str: str) -> float:
    """Parse height string (e.g. \"5' 11\") to inches."""
    if not h_str or h_str == "--":
        return np.nan
    try:
        parts = h_str.replace('"', "").replace("'", "").split()
        feet = int(parts[0])
        inches = int(parts[1]) if len(parts) > 1 else 0
        return feet * 12 + inches
    except Exception:
        return np.nan


def parse_reach_inches(r_str: str) -> float:
    """Parse reach string (e.g. '72\"') to inches."""
    if not r_str or r_str == "--":
        return np.nan
    try:
        return float(r_str.replace('"', "").strip())
    except Exception:
        return np.nan


def parse_dob(dob_str: str) -> datetime | None:
    """Parse date of birth string (e.g. 'Jan 01, 1990') to datetime."""
    if not dob_str or dob_str == "--":
        return None
    try:
        return datetime.strptime(dob_str, "%b %d, %Y")
    except Exception:
        return None


def american_to_decimal(odds: int | float | None) -> float:
    """Convert American odds to European decimal odds."""
    if odds is None or odds == 0:
        return np.nan
    if odds > 0:
        return 1 + odds / 100
    else:
        return 1 + 100 / abs(odds)
