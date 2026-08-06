"""Tests for registry_tool.py patch-reasoning-effort (port of tools/patch_reasoning_effort.py)."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from registry_tool import (
    _PRE_BUDGET_FIELD,
    _PRE_EFFORT_FIELD,
    _PRE_PARSING_FIELD,
    find_gptoss_configs,
    gptoss_missing_fields,
    gptoss_patch_config,
)


def _write_config(path, fields):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"operation": {"fields": fields}}, f)


class TestMissingFields:
    def test_empty_config_missing_all(self, tmp_path):
        path = os.path.join(str(tmp_path), "m.json")
        _write_config(path, [])
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        missing = gptoss_missing_fields(data)
        assert len(missing) == 3
        assert {m["key"] for m in missing} == {_PRE_EFFORT_FIELD["key"], _PRE_PARSING_FIELD["key"], _PRE_BUDGET_FIELD["key"]}

    def test_full_config_missing_none(self, tmp_path):
        path = os.path.join(str(tmp_path), "m.json")
        _write_config(path, [_PRE_EFFORT_FIELD, _PRE_PARSING_FIELD, _PRE_BUDGET_FIELD])
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert gptoss_missing_fields(data) == []

    def test_only_effort_missing(self, tmp_path):
        path = os.path.join(str(tmp_path), "m.json")
        _write_config(path, [_PRE_PARSING_FIELD, _PRE_BUDGET_FIELD])
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        missing = gptoss_missing_fields(data)
        assert [m["key"] for m in missing] == [_PRE_EFFORT_FIELD["key"]]

    def test_budget_missing_when_only_legacy_fields(self, tmp_path):
        # Alte Configs mit effort+parsing, aber ohne Budget -> Budget fehlt.
        path = os.path.join(str(tmp_path), "m.json")
        _write_config(path, [_PRE_EFFORT_FIELD, _PRE_PARSING_FIELD])
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        missing = gptoss_missing_fields(data)
        assert [m["key"] for m in missing] == [_PRE_BUDGET_FIELD["key"]]


class TestPatchConfig:
    def test_patch_adds_fields_and_backup(self, tmp_path):
        path = os.path.join(str(tmp_path), "m.json")
        _write_config(path, [])
        changed, added, updated, backup = gptoss_patch_config(path)
        assert changed is True
        assert len(added) == 3
        assert updated == []
        assert backup is not None
        assert os.path.exists(backup)
        with open(path, "r", encoding="utf-8") as f:
            keys = {f["key"] for f in json.load(f)["operation"]["fields"]}
        assert keys == {_PRE_EFFORT_FIELD["key"], _PRE_PARSING_FIELD["key"], _PRE_BUDGET_FIELD["key"]}
        with open(backup, "r", encoding="utf-8") as f:
            assert json.load(f)["operation"]["fields"] == []

    def test_patch_idempotent(self, tmp_path):
        path = os.path.join(str(tmp_path), "m.json")
        _write_config(path, [])
        gptoss_patch_config(path)
        changed, added, updated, backup = gptoss_patch_config(path)
        assert changed is False
        assert added == []
        assert updated == []
        assert backup is None

    def test_dry_run_does_not_change(self, tmp_path):
        path = os.path.join(str(tmp_path), "m.json")
        _write_config(path, [])
        changed, added, updated, backup = gptoss_patch_config(path, dry_run=True)
        assert changed is True
        assert backup is None
        with open(path, "r", encoding="utf-8") as f:
            assert json.load(f)["operation"]["fields"] == []

    def test_patch_overwrites_stale_effort_value(self, tmp_path):
        # Alte Config mit effort="low": Zielwert (medium) wird ueberschrieben.
        legacy_effort = dict(_PRE_EFFORT_FIELD)
        legacy_effort["value"] = "low"
        path = os.path.join(str(tmp_path), "m.json")
        _write_config(path, [legacy_effort, _PRE_PARSING_FIELD, dict(_PRE_BUDGET_FIELD, **{"value": {"checked": True, "value": 1024}})])
        changed, added, updated, backup = gptoss_patch_config(path)
        assert changed is True
        assert added == []
        assert len(updated) == 2  # effort + budget nachgezogen
        with open(path, "r", encoding="utf-8") as f:
            values = {f["key"]: f["value"] for f in json.load(f)["operation"]["fields"]}
        assert values[_PRE_EFFORT_FIELD["key"]] == _PRE_EFFORT_FIELD["value"]
        assert values[_PRE_BUDGET_FIELD["key"]]["value"] == _PRE_BUDGET_FIELD["value"]["value"]


class TestFindConfigs:
    def test_finds_only_valid_gptoss_configs(self, tmp_path, monkeypatch):
        monkeypatch.setattr("registry_tool.CONFIG_ROOT", tmp_path)
        sub = os.path.join(str(tmp_path), "Intel", "x")
        os.makedirs(sub, exist_ok=True)
        gptoss = os.path.join(sub, "gpt-oss-20b-32x2.4B-Q4_K_S.gguf.json")
        other = os.path.join(sub, "other-model.json")
        broken = os.path.join(sub, "gpt-oss-broken.json")
        _write_config(gptoss, [])
        _write_config(other, [])
        with open(broken, "w", encoding="utf-8") as f:
            f.write("not-json")
        configs = find_gptoss_configs()
        assert configs == [gptoss]
