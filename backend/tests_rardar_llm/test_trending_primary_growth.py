import json
from copy import deepcopy
from pathlib import Path

from app.integrations.rardar.trending_metrics import apply_history_context, order_today, select_growth


def appearance(source, value, date="2026-09-11", rank=1):
    return {
        "source": source,
        "reportedDelta" if source == "github" else "trendshiftStarsGained": value,
        "sourceDate": date,
        "captureDate": "2026-09-12",
        "fetchedAt": "2026-09-12T01:00:00+00:00",
        "rank": rank,
    }


def test_primary_is_source_priority_not_maximum_or_array_order():
    rows = [appearance("trendshift", 900), appearance("github", 0)]
    assert select_growth(rows)["value"] == 0
    assert select_growth(rows[::-1]) == select_growth(rows)
    rows[1]["reportedDelta"] = None
    assert select_growth(rows)["source"] == "trendshift"
    rows[0]["trendshiftStarsGained"] = None
    assert select_growth(rows) is None


def test_full_sort_before_pagination_does_not_change_facts():
    projects = [
        {"repository": f"owner/repo-{n:02}", "totalStars": n, "appearances": [appearance("trendshift", n)]}
        for n in range(36)
    ]
    facts = deepcopy({p["repository"]: p["appearances"] for p in projects})
    order_today(projects)
    assert [p["primaryGrowth"]["value"] for p in projects[:20]] == list(range(35, 15, -1))
    assert [p["displayRank"] for p in projects] == list(range(1, 37))
    assert {p["repository"]: p["appearances"] for p in projects} == facts


def test_ties_and_unknowns():
    projects = [
        {"repository": name, "totalStars": stars, "appearances": [appearance("github", growth)]}
        for name, stars, growth in [
            ("x/z", None, 2),
            ("x/b", 9, 2),
            ("x/a", 9, 2),
            ("x/n", 999, None),
            ("x/zero", 0, 0),
        ]
    ]
    order_today(projects)
    assert [p["repository"] for p in projects] == ["x/a", "x/b", "x/z", "x/zero", "x/n"]


def test_history_selects_period_before_source():
    project = {"appearances": [appearance("github", 999, "2026-09-10"), appearance("trendshift", 3, "2026-09-11", 7)]}
    apply_history_context(project)
    assert project["primaryGrowth"]["value"] == 3
    assert project["historicalContext"]["rank"] == 7
    project["appearances"].append(appearance("github", 0, "2026-09-11", 8))
    apply_history_context(project)
    assert project["primaryGrowth"]["value"] == 0
    assert project["historicalContext"]["rank"] == 8


def test_history_dated_window_precedes_undated_capture_and_count():
    project = {
        "appearances": [appearance("github", 700, None)],
        "historicalRardarEvidence": [
            {
                "windowStartedAt": "2026-09-09T00:00:00+00:00",
                "windowEndedAt": "2026-09-10T00:00:00+00:00",
                "rank": 7,
                "observedStarDelta": 666,
            }
        ],
    }
    apply_history_context(project)
    assert project["primaryGrowth"]["value"] == 666
    assert project["historicalContext"]["rank"] == 7
    project.pop("historicalRardarEvidence")
    apply_history_context(project)
    assert project["historicalContext"]["dateKind"] == "capture"
    project["appearances"] = []
    project["historicalEvidence"] = [
        {"source": "github", "reportedAppearanceCount": 89, "fetchedAt": "2026-09-11T00:00:00Z"}
    ]
    apply_history_context(project)
    assert project["primaryGrowth"] is None
    assert project["historicalContext"]["kind"] == "reported_count"


def test_mixed_timezone_instants_do_not_choose_older_history():
    rows = [appearance("github", 1), appearance("github", 2)]
    rows[0]["fetchedAt"] = "2026-09-12T00:30:00+08:00"
    rows[1]["fetchedAt"] = "2026-09-11T18:00:00Z"
    assert select_growth(rows)["value"] == 2
    project = {
        "appearances": [],
        "historicalRardarEvidence": [
            {"windowEndedAt": row["fetchedAt"], "rank": row["reportedDelta"], "observedStarDelta": row["reportedDelta"]}
            for row in rows
        ],
    }
    apply_history_context(project)
    assert project["primaryGrowth"]["value"] == 2


def test_complete_user_saved_snapshot_regression():
    projects = json.loads(
        (Path(__file__).parent / "fixtures/saved_today_growth_20260911.json").read_text(encoding="utf-8")
    )["projects"]
    original = {p["repository"]: deepcopy(p["appearances"]) for p in projects}
    assert len(projects) == 36
    order_today(projects)
    positions = {p["repository"]: p["displayRank"] for p in projects}
    assert {
        name: positions[name]
        for name in (
            "bilawalsidhu/gods-eye-view",
            "ayghri/i-have-adhd",
            "github/spec-kit",
            "obra/superpowers",
            "stablyai/orca",
            "nab138/iloader",
        )
    } == {
        "bilawalsidhu/gods-eye-view": 1,
        "ayghri/i-have-adhd": 2,
        "github/spec-kit": 5,
        "obra/superpowers": 6,
        "stablyai/orca": 13,
        "nab138/iloader": 36,
    }
    assert {p["repository"]: p["appearances"] for p in projects} == original
    assert len(projects[:20]) == 20 and len(projects[20:]) == 16
