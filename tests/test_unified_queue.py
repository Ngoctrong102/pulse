"""Unified queue merges ship/fix/debt/hygiene on one severity scale."""

from __future__ import annotations

from pulse_lib.next_ranking import rank_queue


def _data():
    return {
        "focus_id": None,
        "features": [
            {
                "id": "feat-a",
                "name": "Feature A",
                "type": "feature",
                "status": "partial",
                "percent": 40,
                "priority": 5,
                "roi": 3,
                "mvp": False,
                "remaining": ["ship it"],
                "mocks": [],
            },
            {
                "id": "feat-mvp",
                "name": "MVP Feature",
                "type": "feature",
                "status": "todo",
                "percent": 0,
                "priority": 2,
                "roi": 8,
                "mvp": True,
                "remaining": ["start"],
                "mocks": [],
            },
        ],
        "backlog": [
            {
                "id": "BUG-1",
                "name": "Critical bug",
                "type": "bug",
                "status": "todo",
                "percent": 0,
                "priority": 1,
                "severity": "blocker",
            },
            {
                "id": "TECH-DEBT-1",
                "name": "Low debt",
                "type": "tech-debt",
                "status": "todo",
                "percent": 0,
                "priority": 9,
                "severity": "low",
            },
        ],
    }


def test_unified_queue_orders_by_severity_then_priority():
    mismatch = {"findings": []}
    q = rank_queue(_data(), lane="all", limit=10, mismatch=mismatch)
    ids = [x["id"] for x in q]
    # blocker bug (sev 0) before mvp ship (sev 1) before medium ship (sev 2) before low debt (sev 3)
    assert ids[0] == "BUG-1"
    assert "feat-mvp" in ids
    assert ids.index("feat-mvp") < ids.index("feat-a")
    assert ids.index("feat-a") < ids.index("TECH-DEBT-1")
    lanes = {x["id"]: x["lane"] for x in q}
    assert lanes["BUG-1"] == "fix"
    assert lanes["feat-mvp"] == "ship"
    assert lanes["TECH-DEBT-1"] == "debt"


def test_hygiene_boosts_existing_card():
    data = _data()
    mismatch = {
        "findings": [
            {
                "feature_id": "feat-a",
                "severity": "critical",
                "code": "X1",
                "message": "broken evidence",
            }
        ]
    }
    q = rank_queue(data, lane="all", limit=10, mismatch=mismatch)
    # feat-a should rise via detect critical boost (rank 0), ahead of mvp (rank 1)
    # BUG-1 also rank 0; tie-break by priority then roi then id
    ids = [x["id"] for x in q]
    assert "feat-a" in ids
    feat = next(x for x in q if x["id"] == "feat-a")
    assert "detect critical boost" in str(feat.get("why") or "")


def test_per_lane_filter_still_works():
    q = rank_queue(_data(), lane="fix", limit=10, mismatch={"findings": []})
    assert all(x["lane"] == "fix" for x in q)
    assert [x["id"] for x in q] == ["BUG-1"]
