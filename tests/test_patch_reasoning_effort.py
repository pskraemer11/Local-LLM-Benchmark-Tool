import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from tools.patch_reasoning_effort import (
    EFFORT_FIELD,
    PARSING_FIELD,
    find_configs,
    missing_fields,
    patch_config,
)


def _write_config(path, fields):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"operation": {"fields": fields}}, f)


class TestMissingFields:
    def test_empty_config_missing_both(self, tmp_path):
        path = os.path.join(str(tmp_path), "m.json")
        _write_config(path, [])
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        missing = missing_fields(data)
        assert len(missing) == 2
        assert {m["key"] for m in missing} == {EFFORT_FIELD["key"], PARSING_FIELD["key"]}

    def test_full_config_missing_none(self, tmp_path):
        path = os.path.join(str(tmp_path), "m.json")
        _write_config(path, [EFFORT_FIELD, PARSING_FIELD])
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert missing_fields(data) == []

    def test_only_effort_missing(self, tmp_path):
        path = os.path.join(str(tmp_path), "m.json")
        _write_config(path, [PARSING_FIELD])
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        missing = missing_fields(data)
        assert [m["key"] for m in missing] == [EFFORT_FIELD["key"]]


class TestPatchConfig:
    def test_patch_adds_fields_and_backup(self, tmp_path):
        path = os.path.join(str(tmp_path), "m.json")
        _write_config(path, [])
        changed, added, backup = patch_config(path)
        assert changed is True
        assert len(added) == 2
        assert backup is not None
        assert os.path.exists(backup)
        with open(path, "r", encoding="utf-8") as f:
            keys = {f["key"] for f in json.load(f)["operation"]["fields"]}
        assert keys == {EFFORT_FIELD["key"], PARSING_FIELD["key"]}
        with open(backup, "r", encoding="utf-8") as f:
            assert json.load(f)["operation"]["fields"] == []

    def test_patch_idempotent(self, tmp_path):
        path = os.path.join(str(tmp_path), "m.json")
        _write_config(path, [])
        patch_config(path)
        changed, added, backup = patch_config(path)
        assert changed is False
        assert added == []
        assert backup is None

    def test_dry_run_does_not_change(self, tmp_path):
        path = os.path.join(str(tmp_path), "m.json")
        _write_config(path, [])
        changed, added, backup = patch_config(path, dry_run=True)
        assert changed is True
        assert backup is None
        with open(path, "r", encoding="utf-8") as f:
            assert json.load(f)["operation"]["fields"] == []


class TestFindConfigs:
    def test_finds_only_valid_gptoss_configs(self, tmp_path, monkeypatch):
        monkeypatch.setattr("tools.patch_reasoning_effort.CONFIG_DIR", str(tmp_path))
        sub = os.path.join(str(tmp_path), "Intel", "x")
        os.makedirs(sub, exist_ok=True)
        gptoss = os.path.join(sub, "gpt-oss-20b-32x2.4B-Q4_K_S.gguf.json")
        other = os.path.join(sub, "other-model.json")
        broken = os.path.join(sub, "gpt-oss-broken.json")
        _write_config(gptoss, [])
        _write_config(other, [])
        with open(broken, "w", encoding="utf-8") as f:
            f.write("not-json")
        configs = find_configs()
        assert configs == [gptoss]
