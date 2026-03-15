"""Tests for unmatched logger + retry queue."""

import json

from ufc_core.tapology.unmatched import RetryQueue, UnmatchedLogger


def _logger(tmp_path):
    return UnmatchedLogger(
        fighters_path=tmp_path / "uf.json",
        events_path=tmp_path / "ue.json",
        fights_path=tmp_path / "ufi.json",
    )


def test_unmatched_fighter_logged_with_context(tmp_path):
    log = _logger(tmp_path)
    log.add_fighter(
        "Jiří Procházka",
        context={"event_url": "https://t.com/e/1", "opponent_name": "X"},
    )
    log.add_fighter(
        "Jiří Procházka",
        context={"event_url": "https://t.com/e/2", "opponent_name": "Y"},
    )
    log.flush()

    data = json.loads((tmp_path / "uf.json").read_text(encoding="utf-8"))
    assert "Jiří Procházka" in data
    assert data["Jiří Procházka"]["occurrences"] == 2
    assert len(data["Jiří Procházka"]["sample_context"]) == 2


def test_unmatched_event_and_fight(tmp_path):
    log = _logger(tmp_path)
    log.add_event("UFC X", date="2026-01-01", url="https://t.com/e/x")
    log.add_fight(
        event_url="https://t.com/e/x",
        fighter_a="A",
        fighter_b="B",
        reason="fight_not_in_db",
    )
    log.flush()

    ev_data = json.loads((tmp_path / "ue.json").read_text(encoding="utf-8"))
    fi_data = json.loads((tmp_path / "ufi.json").read_text(encoding="utf-8"))
    assert ev_data[0]["url"] == "https://t.com/e/x"
    assert fi_data[0]["reason"] == "fight_not_in_db"


def test_unmatched_event_dedupes_across_runs(tmp_path):
    """Same (name, date) on multiple runs must not duplicate entries."""
    log = _logger(tmp_path)
    log.add_event("UFC X", date="2026-01-01", url="u1")
    log.add_event("UFC X", date="2026-01-01", url="u1")
    log.add_event("UFC X", date="2026-01-01", url="u1")
    log.add_event("UFC Y", date="2026-02-02", url="u2")
    log.flush()

    data = json.loads((tmp_path / "ue.json").read_text(encoding="utf-8"))
    assert len(data) == 2
    ufc_x = next(e for e in data if e["name"] == "UFC X")
    assert ufc_x["occurrences"] == 3


def test_unmatched_fight_dedupes(tmp_path):
    log = _logger(tmp_path)
    log.add_fight("u1", "A", "B", "fight_not_in_db")
    log.add_fight("u1", "A", "B", "fight_not_in_db")
    log.flush()

    data = json.loads((tmp_path / "ufi.json").read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["occurrences"] == 2


def test_logger_persists_across_instances(tmp_path):
    """Existing entries are preserved when reopening the logger."""
    log = _logger(tmp_path)
    log.add_fighter("X", {"event_url": "u1"})
    log.flush()

    log2 = _logger(tmp_path)
    log2.add_fighter("X", {"event_url": "u2"})
    log2.flush()

    data = json.loads((tmp_path / "uf.json").read_text(encoding="utf-8"))
    assert data["X"]["occurrences"] == 2


def test_sample_context_capped(tmp_path):
    log = _logger(tmp_path)
    for i in range(20):
        log.add_fighter("X", {"event_url": f"u{i}"})
    log.flush()
    data = json.loads((tmp_path / "uf.json").read_text(encoding="utf-8"))
    assert data["X"]["occurrences"] == 20
    assert len(data["X"]["sample_context"]) == 10  # cap


def test_retry_queue_add_and_remove(tmp_path):
    q = RetryQueue(tmp_path / "rq.json")
    q.add(matchup_url="https://t.com/m/1", reason="unmatched_fighter", context={"name": "X"})
    q.add(matchup_url="https://t.com/m/2", reason="unmatched_event")
    q.save()

    reloaded = RetryQueue(tmp_path / "rq.json")
    assert len(reloaded.entries()) == 2
    reloaded.remove("https://t.com/m/1")
    reloaded.save()

    final = RetryQueue(tmp_path / "rq.json")
    urls = [e["matchup_url"] for e in final.entries()]
    assert urls == ["https://t.com/m/2"]


def test_retry_queue_remove_nonexistent_no_error(tmp_path):
    q = RetryQueue(tmp_path / "rq.json")
    q.remove("https://t.com/missing")  # Should not raise
    assert q.entries() == []
