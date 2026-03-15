"""Tests for the manual fighter alias map."""

import json

from ufc_core.tapology.alias_map import AliasMap


def _write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_lookup_existing_alias(tmp_path):
    p = tmp_path / "aliases.json"
    _write(p, {"Jiří Procházka": "Jiri Prochazka"})
    am = AliasMap(p)
    assert am.resolve("Jiří Procházka") == "Jiri Prochazka"


def test_lookup_missing_returns_none(tmp_path):
    p = tmp_path / "aliases.json"
    _write(p, {"Jiří Procházka": "Jiri Prochazka"})
    am = AliasMap(p)
    assert am.resolve("Random Fighter") is None


def test_missing_file_returns_empty_map(tmp_path):
    am = AliasMap(tmp_path / "nonexistent.json")
    assert am.resolve("Anyone") is None


def test_corrupt_file_returns_empty_map(tmp_path):
    p = tmp_path / "broken.json"
    p.write_text("{not valid json", encoding="utf-8")
    am = AliasMap(p)
    assert am.resolve("Anyone") is None


def test_add_alias_persists(tmp_path):
    p = tmp_path / "aliases.json"
    am = AliasMap(p)
    am.add("Test Fighter", "Test Canonical")
    am.save()
    reloaded = AliasMap(p)
    assert reloaded.resolve("Test Fighter") == "Test Canonical"


def test_save_uses_unicode_for_diacritics(tmp_path):
    p = tmp_path / "aliases.json"
    am = AliasMap(p)
    am.add("Jiří Procházka", "Jiri Prochazka")
    am.save()
    raw = p.read_text(encoding="utf-8")
    assert "Jiří Procházka" in raw
