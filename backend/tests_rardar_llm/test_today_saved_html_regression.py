"""Regression from user-saved HTML RSC facts, not a synthetic source fetch."""

import copy
import json
from pathlib import Path

from app.integrations.rardar.trending_metrics import qualifying_today, select_growth


def test_september_13_saved_union_preserves_eight_qualifiers_and_stale_source():
    snapshot = json.loads((Path(__file__).parent / "fixtures" / "today-source-20260913.json").read_text(encoding="utf-8"))
    original = copy.deepcopy(snapshot)
    assert len(snapshot["projects"]) == 37
    for project in snapshot["projects"]:
        selected = select_growth(project["appearances"])
        assert ({"source": selected["source"], "value": selected["value"]} if selected else None) == project["expectedPrimary"]

    result = qualifying_today(snapshot, minimum=200)
    assert result["rawProjectCount"] == 37
    assert result["eligibleProjectCount"] == 8
    assert result["unknownGrowthCount"] == 0
    assert [project["repository"] for project in result["projects"]] == [
        "bilawalsidhu/gods-eye-view", "ayghri/i-have-adhd", "github/spec-kit", "obra/superpowers",
        "nashsu/llm_wiki", "alsk1992/cloddsbot", "vastsa/pi-desktop", "armory3d/armorpaint",
    ]
    assert [project["primaryGrowth"]["value"] for project in result["projects"]] == [3680, 3463, 1015, 729, 647, 626, 552, 350]
    github, trendshift = result["sources"]
    assert github["status"] == "stale"
    assert github["fetchedAt"] == "2026-09-12T06:31:05.538900+00:00"
    assert github["checkedAt"] == "2026-09-13T01:00:30.375698+00:00"
    assert trendshift["sourceDate"] == "2026-09-12"
    assert result["publishedAt"] == "2026-09-13T01:00:32.730177+00:00"
    assert snapshot == original  # Filtering does not rewrite source facts or freshness.
