"""next --json exposes a single ranking story (continue + queue)."""

from __future__ import annotations

from pulse_lib.next_ranking import build_next_payload


def test_payload_has_no_legacy_next_list():
    data = {
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
            }
        ],
        "backlog": [],
    }
    payload = build_next_payload(data, mismatch={"findings": []}, limit=5)
    assert "next" not in payload
    assert "queue" in payload
    assert "continue" in payload
    assert payload["queue"]
    assert payload["queue"][0]["lane"] == "ship"
