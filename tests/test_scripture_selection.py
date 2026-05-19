"""
Phase 0 characterization tests: scripture selection behavior.
"""
import pytest
import reminder_dialog as rd


# Use a fixed, known BELIEF_SCRIPTURE_MAP to make tests deterministic.
_FIXED_MAP = [
    {
        "name": "shame_identity",
        "keywords": ["dirty", "ashamed", "failure"],
        "scriptures": [("Romans 8:1", "No condemnation.")],
    },
    {
        "name": "too_weak",
        "keywords": ["weak", "powerless"],
        "scriptures": [("Phil 4:13", "I can do all things.")],
    },
]


@pytest.fixture(autouse=True)
def patch_belief_map(monkeypatch):
    monkeypatch.setattr(rd, "BELIEF_SCRIPTURE_MAP", _FIXED_MAP)
    monkeypatch.setattr(rd, "SCRIPTURES", [("Psalm 51:10", "Create in me a clean heart.")])


class TestSelectScriptureForBelief:
    def test_empty_belief_returns_default_match_type(self):
        result = rd.select_scripture_for_belief("")
        assert result["match_type"] == "default"
        assert result["category"] is None
        assert result["matched_keywords"] == []
        assert result["scripture_ref"] == "Psalm 51:10"

    def test_whitespace_only_belief_returns_default(self):
        result = rd.select_scripture_for_belief("   ")
        assert result["match_type"] == "default"

    def test_keyword_match_returns_belief_keyword_type(self):
        result = rd.select_scripture_for_belief("I feel dirty and ashamed")
        assert result["match_type"] == "belief_keyword"
        assert result["category"] == "shame_identity"
        assert "dirty" in result["matched_keywords"] or "ashamed" in result["matched_keywords"]
        assert result["scripture_ref"] == "Romans 8:1"

    def test_no_keyword_match_returns_fallback(self):
        result = rd.select_scripture_for_belief("just some random text with no matches here")
        assert result["match_type"] == "fallback"
        assert result["category"] is None
        assert result["matched_keywords"] == []

    def test_best_match_wins_by_keyword_count(self):
        # "dirty" matches shame_identity (1 kw); "weak" matches too_weak (1 kw)
        # "dirty ashamed" matches shame_identity (2 kw) > too_weak (0 kw)
        result = rd.select_scripture_for_belief("I feel dirty and ashamed")
        assert result["category"] == "shame_identity"

    def test_result_has_required_keys(self):
        result = rd.select_scripture_for_belief("anything")
        assert "match_type" in result
        assert "category" in result
        assert "matched_keywords" in result
        assert "scripture_ref" in result
        assert "scripture_text" in result

    def test_match_type_is_case_insensitive(self):
        # Keywords should match regardless of input case since belief text is .lower()ed
        result = rd.select_scripture_for_belief("I Feel DIRTY")
        assert result["match_type"] == "belief_keyword"
        assert result["category"] == "shame_identity"

    def test_multiple_keyword_matches_recorded(self):
        result = rd.select_scripture_for_belief("dirty failure ashamed")
        assert result["match_type"] == "belief_keyword"
        assert len(result["matched_keywords"]) >= 2
