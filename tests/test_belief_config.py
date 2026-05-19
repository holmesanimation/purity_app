"""
Phase 0 characterization tests: belief config normalization and JSON serialization.
Tests pure functions in reminder_dialog without touching GUI or file system.
"""
import sys
import types
import importlib
import json
import pytest

# ---------------------------------------------------------------------------
# Import reminder_dialog without triggering the module-level config file read
# or breaking if optional deps are missing.
# ---------------------------------------------------------------------------
import reminder_dialog as rd


# ---------------------------------------------------------------------------
# normalize_belief_config
# ---------------------------------------------------------------------------

class TestNormalizeBeliefConfig:
    def test_non_list_returns_default(self):
        result = rd.normalize_belief_config("not a list")
        assert result == rd.default_belief_scripture_map()

    def test_non_list_dict_returns_default(self):
        result = rd.normalize_belief_config({"name": "x"})
        assert result == rd.default_belief_scripture_map()

    def test_empty_list_returns_default(self):
        result = rd.normalize_belief_config([])
        assert result == rd.default_belief_scripture_map()

    def test_valid_dict_scriptures_normalized(self):
        raw = [
            {
                "name": "shame",
                "keywords": ["dirty", "ashamed"],
                "scriptures": [
                    {"ref": "Romans 8:1", "text": "No condemnation."},
                ],
            }
        ]
        result = rd.normalize_belief_config(raw)
        assert len(result) == 1
        assert result[0]["name"] == "shame"
        assert result[0]["keywords"] == ["dirty", "ashamed"]
        assert result[0]["scriptures"] == [("Romans 8:1", "No condemnation.")]

    def test_tuple_scriptures_normalized(self):
        raw = [
            {
                "name": "weak",
                "keywords": ["tired"],
                "scriptures": [("Phil 4:13", "I can do all things.")],
            }
        ]
        result = rd.normalize_belief_config(raw)
        assert result[0]["scriptures"] == [("Phil 4:13", "I can do all things.")]

    def test_list_scriptures_normalized(self):
        raw = [
            {
                "name": "weak",
                "keywords": ["tired"],
                "scriptures": [["Phil 4:13", "I can do all things."]],
            }
        ]
        result = rd.normalize_belief_config(raw)
        assert result[0]["scriptures"] == [("Phil 4:13", "I can do all things.")]

    def test_string_keywords_split_by_comma(self):
        raw = [
            {
                "name": "escape",
                "keywords": "deserve, escape, reward",
                "scriptures": [("Rom 1:1", "Text.")],
            }
        ]
        result = rd.normalize_belief_config(raw)
        assert result[0]["keywords"] == ["deserve", "escape", "reward"]

    def test_keywords_lowercased_and_stripped(self):
        raw = [
            {
                "name": "test",
                "keywords": ["  DIRTY  ", "Ashamed"],
                "scriptures": [("Rom 1:1", "Text.")],
            }
        ]
        result = rd.normalize_belief_config(raw)
        assert result[0]["keywords"] == ["dirty", "ashamed"]

    def test_category_missing_keywords_skipped(self):
        raw = [
            {"name": "no_keywords", "keywords": [], "scriptures": [("Rom 1:1", "Text.")]},
        ]
        result = rd.normalize_belief_config(raw)
        # no valid categories → falls back to default
        assert result == rd.default_belief_scripture_map()

    def test_category_missing_scriptures_skipped(self):
        raw = [
            {"name": "no_scripts", "keywords": ["x"], "scriptures": []},
        ]
        result = rd.normalize_belief_config(raw)
        assert result == rd.default_belief_scripture_map()

    def test_non_dict_category_items_skipped(self):
        raw = ["not_a_dict", None, 42]
        result = rd.normalize_belief_config(raw)
        assert result == rd.default_belief_scripture_map()

    def test_invalid_config_mixed_with_valid(self):
        raw = [
            "bad",
            {
                "name": "good",
                "keywords": ["weak"],
                "scriptures": [("Phil 4:13", "Strength.")],
            },
        ]
        result = rd.normalize_belief_config(raw)
        assert len(result) == 1
        assert result[0]["name"] == "good"

    def test_name_defaulted_when_blank(self):
        raw = [
            {
                "name": "   ",
                "keywords": ["x"],
                "scriptures": [("Rom 1:1", "Text.")],
            }
        ]
        result = rd.normalize_belief_config(raw)
        assert result[0]["name"] == "belief_1"

    def test_name_defaulted_when_missing(self):
        raw = [
            {
                "keywords": ["x"],
                "scriptures": [("Rom 1:1", "Text.")],
            }
        ]
        result = rd.normalize_belief_config(raw)
        assert result[0]["name"] == "belief_1"


# ---------------------------------------------------------------------------
# config_to_json_ready
# ---------------------------------------------------------------------------

class TestConfigToJsonReady:
    def test_round_trip_shape(self):
        config = rd.default_belief_scripture_map()
        result = rd.config_to_json_ready(config)

        assert isinstance(result, list)
        for item in result:
            assert "name" in item
            assert "keywords" in item
            assert "scriptures" in item
            for s in item["scriptures"]:
                assert "ref" in s
                assert "text" in s

    def test_scriptures_are_dicts_not_tuples(self):
        config = [
            {
                "name": "shame",
                "keywords": ["dirty"],
                "scriptures": [("Romans 8:1", "No condemnation.")],
            }
        ]
        result = rd.config_to_json_ready(config)
        assert result[0]["scriptures"][0] == {"ref": "Romans 8:1", "text": "No condemnation."}

    def test_result_is_json_serializable(self):
        config = rd.default_belief_scripture_map()
        result = rd.config_to_json_ready(config)
        json_str = json.dumps(result)  # must not raise
        assert json_str

    def test_keywords_are_list(self):
        config = [
            {
                "name": "shame",
                "keywords": ["dirty", "ashamed"],
                "scriptures": [("Romans 8:1", "No condemnation.")],
            }
        ]
        result = rd.config_to_json_ready(config)
        assert isinstance(result[0]["keywords"], list)

    def test_roundtrip_normalize_then_json_ready(self):
        raw = [
            {
                "name": "shame",
                "keywords": ["dirty"],
                "scriptures": [{"ref": "Romans 8:1", "text": "No condemnation."}],
            }
        ]
        normalized = rd.normalize_belief_config(raw)
        json_ready = rd.config_to_json_ready(normalized)
        # re-normalizing from json_ready should produce same structure
        renormalized = rd.normalize_belief_config(json_ready)
        assert renormalized == normalized
