#!/usr/bin/env python3
"""Focus / Continue / unified Queue ranking for pulse.

``refs`` = ownership only. Continue interrupt requires ``focus_id in card.blocks``.
Default queue merges ship/fix/debt/hygiene on one scale: severity → priority → roi → id.
Per-lane filters remain via ``--lane ship|fix|debt|hygiene``.
"""

from __future__ import annotations

from typing import Any

from pulse_lib.next_actions import (
    _recommended_action,
    findings_for_feature,
    list_sub_actions,
    load_mismatch_summary,
    rank_next_actions,
)

LANES = frozenset({"all", "ship", "fix", "debt", "hygiene"})
OPEN_STATUSES = frozenset({"todo", "partial", "blocked"})
DONE_STATUSES = frozenset({"done", "cancelled", "wontfix"})
SEVERITY_ORDER = {"blocker": 0, "high": 1, "medium": 2, "low": 3}
# Detect severities map onto the same 0..3 scale as card severities.
DETECT_SEVERITY_RANK = {"critical": 0, "warning": 2}


def _all_cards(data: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for bucket in ("features", "backlog"):
        for card in data.get(bucket) or []:
            if isinstance(card, dict):
                out.append(card)
    return out


def _card_by_id(data: dict[str, Any], cid: str) -> dict[str, Any] | None:
    for card in _all_cards(data):
        if card.get("id") == cid:
            return card
    return None


def _blocks_list(card: dict[str, Any]) -> list[str]:
    raw = card.get("blocks")
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw if str(x).strip()]


def _is_open(card: dict[str, Any]) -> bool:
    return str(card.get("status") or "") in OPEN_STATUSES


def focus_snapshot(data: dict[str, Any]) -> dict[str, Any] | None:
    """Runtime focus view. Missing/done focus → null (caller may still keep focus_id on disk)."""
    fid = data.get("focus_id")
    if fid is None or str(fid).strip() == "":
        return None
    fid = str(fid).strip()
    card = _card_by_id(data, fid)
    if card is None:
        return {"id": fid, "name": None, "status": None, "percent": None, "valid": False}
    st = str(card.get("status") or "")
    valid = st not in DONE_STATUSES
    return {
        "id": fid,
        "name": card.get("name"),
        "status": st,
        "percent": card.get("percent"),
        "valid": valid,
        "type": card.get("type") or "feature",
    }


def open_blockers_for_focus(data: dict[str, Any], focus_id: str) -> list[dict[str, Any]]:
    """Open backlog/feature cards whose ``blocks`` contains focus_id.

    Sorted by severity → priority → id. ``refs`` alone never qualifies.
    """
    blockers: list[dict[str, Any]] = []
    for card in _all_cards(data):
        if not _is_open(card):
            continue
        if focus_id not in _blocks_list(card):
            continue
        blockers.append(card)
    blockers.sort(
        key=lambda c: (
            SEVERITY_ORDER.get(str(c.get("severity") or ""), 9),
            int(c.get("priority") or 99),
            str(c.get("id") or ""),
        )
    )
    return blockers


def _feature_step_item(
    feat: dict[str, Any],
    mismatch: dict[str, Any],
) -> dict[str, Any]:
    fid = str(feat.get("id") or "")
    findings = findings_for_feature(mismatch, fid)
    # Ship/focus step: do not let detect info steal the action text when we only need remaining.
    # Prefer remaining/spec path by filtering findings to critical/warning for recommendation.
    blocking = [
        f
        for f in findings
        if str(f.get("severity") or "") in {"critical", "warning"}
    ]
    action, why = _recommended_action(feat, blocking)
    subs = list_sub_actions(feat, blocking)
    return {
        "id": fid,
        "name": feat.get("name"),
        "status": feat.get("status"),
        "percent": feat.get("percent"),
        "priority": feat.get("priority"),
        "roi": feat.get("roi"),
        "mvp": bool(feat.get("mvp")),
        "action": action,
        "why": why,
        "remaining": list(feat.get("remaining") or []),
        "mocks": list(feat.get("mocks") or []),
        "docs": feat.get("docs") or {},
        "specs": list(feat.get("specs") or []),
        "sub_actions": subs,
        "multi": len(subs) >= 2,
        "finding_count": len(findings),
    }


def _sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        int(item.get("_severity_rank") if item.get("_severity_rank") is not None else 9),
        int(item.get("priority") if item.get("priority") is not None else 99),
        -int(item.get("roi") or 0),
        str(item.get("id") or ""),
    )


def _ship_candidates(
    data: dict[str, Any],
    *,
    mismatch: dict[str, Any],
    exclude: str | None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for feat in data.get("features") or []:
        if not isinstance(feat, dict) or not _is_open(feat):
            continue
        fid = str(feat.get("id") or "")
        if exclude and fid == exclude:
            continue
        step = _feature_step_item(feat, mismatch)
        # mvp → rank 1 (same band as high); else medium band
        sev_rank = 1 if feat.get("mvp") else 2
        items.append(
            {
                "id": fid,
                "name": feat.get("name"),
                "lane": "ship",
                "action": step.get("action"),
                "why": "Unified queue (severity → priority → roi)",
                "priority": feat.get("priority"),
                "roi": feat.get("roi"),
                "severity": None,
                "status": feat.get("status"),
                "percent": feat.get("percent"),
                "_severity_rank": sev_rank,
            }
        )
    return items


def _fix_candidates(
    data: dict[str, Any],
    *,
    exclude: str | None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for c in data.get("backlog") or []:
        if not isinstance(c, dict) or c.get("type") != "bug" or not _is_open(c):
            continue
        cid = str(c.get("id") or "")
        if exclude and cid == exclude:
            continue
        sev = str(c.get("severity") or "")
        items.append(
            {
                "id": cid,
                "name": c.get("name"),
                "lane": "fix",
                "action": f"Fix bug: {c.get('name')}",
                "why": f"severity={c.get('severity')}",
                "priority": c.get("priority"),
                "roi": 0,
                "severity": c.get("severity"),
                "status": c.get("status"),
                "percent": c.get("percent"),
                "_severity_rank": SEVERITY_ORDER.get(sev, 9),
            }
        )
    return items


def _debt_candidates(
    data: dict[str, Any],
    *,
    exclude: str | None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for c in data.get("backlog") or []:
        if not isinstance(c, dict) or c.get("type") != "tech-debt" or not _is_open(c):
            continue
        cid = str(c.get("id") or "")
        if exclude and cid == exclude:
            continue
        sev = str(c.get("severity") or "")
        items.append(
            {
                "id": cid,
                "name": c.get("name"),
                "lane": "debt",
                "action": f"Pay debt: {c.get('name')}",
                "why": f"severity={c.get('severity')}",
                "priority": c.get("priority"),
                "roi": 0,
                "severity": c.get("severity"),
                "status": c.get("status"),
                "percent": c.get("percent"),
                "_severity_rank": SEVERITY_ORDER.get(sev, 9),
            }
        )
    return items


def _hygiene_candidates(
    mismatch: dict[str, Any],
    *,
    exclude: str | None,
    occupied_ids: set[str],
) -> list[dict[str, Any]]:
    """Detect critical/warning rows. Skip ids already represented by ship/fix/debt.

    If a finding is more urgent than an occupied card, raise that card's severity_rank
    (caller merges via occupied map — here we only emit orphan hygiene rows).
    """
    items: list[dict[str, Any]] = []
    findings = [
        f
        for f in (mismatch.get("findings") or [])
        if isinstance(f, dict)
        and str(f.get("severity") or "") in {"critical", "warning"}
    ]
    for f in findings:
        fid = str(f.get("feature_id") or "").strip()
        row_id = fid or str(f.get("code") or "")
        if not row_id:
            continue
        if exclude and row_id == exclude:
            continue
        if fid and fid in occupied_ids:
            continue  # dedup — occupied card keeps the row
        if row_id in occupied_ids:
            continue
        sev = str(f.get("severity") or "")
        items.append(
            {
                "id": row_id,
                "name": f.get("message") or f.get("code"),
                "lane": "hygiene",
                "action": (
                    f"Investigate detect ({f.get('severity')}): "
                    f"{f.get('message') or f.get('code')}"
                ),
                "why": "Hygiene — critical/warning only (info excluded)",
                "priority": 99,
                "roi": 0,
                "severity": sev,
                "status": None,
                "percent": None,
                "_severity_rank": DETECT_SEVERITY_RANK.get(sev, 9),
            }
        )
        occupied_ids.add(row_id)
    return items


def _apply_hygiene_urgency_boost(
    items: list[dict[str, Any]],
    mismatch: dict[str, Any],
) -> None:
    """If detect critical/warning targets an existing card id, raise severity_rank in place."""
    by_id = {str(i.get("id") or ""): i for i in items if i.get("id")}
    for f in mismatch.get("findings") or []:
        if not isinstance(f, dict):
            continue
        sev = str(f.get("severity") or "")
        if sev not in DETECT_SEVERITY_RANK:
            continue
        fid = str(f.get("feature_id") or "").strip()
        if not fid or fid not in by_id:
            continue
        rank = DETECT_SEVERITY_RANK[sev]
        cur = by_id[fid]
        if int(cur.get("_severity_rank") if cur.get("_severity_rank") is not None else 9) > rank:
            cur["_severity_rank"] = rank
            if sev == "critical":
                cur["why"] = f"{cur.get('why')} · detect critical boost"


def _strip_internal(item: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in item.items() if not k.startswith("_")}
    return out


def resolve_continue(
    data: dict[str, Any],
    *,
    mismatch: dict[str, Any] | None = None,
    lane: str = "all",
    queue_limit: int = 7,
) -> dict[str, Any]:
    """Return ContinueTarget dict (kind focus_step | unblock | promote_queue)."""
    mismatch = mismatch if mismatch is not None else load_mismatch_summary()
    focus = focus_snapshot(data)
    queue = rank_queue(data, lane=lane, limit=queue_limit, mismatch=mismatch)

    if focus and focus.get("valid"):
        fid = str(focus["id"])
        blockers = open_blockers_for_focus(data, fid)
        if blockers:
            top = blockers[0]
            tid = str(top.get("id") or "")
            return {
                "kind": "unblock",
                "id": tid,
                "focus_id": fid,
                "blocker_id": tid,
                "action": f"Unblock focus `{fid}`: resolve `{tid}` — {top.get('name')}",
                "why": (
                    f"Open card blocks focus (blocks contains {fid}); "
                    "refs alone would not interrupt"
                ),
                "sub_index": None,
                "name": top.get("name"),
                "severity": top.get("severity"),
            }
        feat = _card_by_id(data, fid)
        if feat is not None:
            step = _feature_step_item(feat, mismatch)
            return {
                "kind": "focus_step",
                "id": fid,
                "focus_id": fid,
                "blocker_id": None,
                "action": step.get("action"),
                "why": step.get("why"),
                "sub_index": 0 if step.get("multi") else None,
                "name": step.get("name"),
                "multi": step.get("multi"),
                "sub_actions": step.get("sub_actions") or [],
            }

    if queue:
        q0 = queue[0]
        return {
            "kind": "promote_queue",
            "id": q0.get("id"),
            "focus_id": None,
            "blocker_id": None,
            "action": f"Promote to focus then continue: {q0.get('action')}",
            "why": f"No active focus — queue #1 ({lane})",
            "sub_index": None,
            "name": q0.get("name"),
        }
    return {
        "kind": "promote_queue",
        "id": None,
        "focus_id": None,
        "blocker_id": None,
        "action": None,
        "why": "No focus and empty queue",
        "sub_index": None,
        "name": None,
    }


def rank_queue(
    data: dict[str, Any],
    *,
    lane: str = "all",
    limit: int = 7,
    mismatch: dict[str, Any] | None = None,
    exclude_id: str | None = None,
) -> list[dict[str, Any]]:
    lane = (lane or "all").strip().lower()
    if lane not in LANES:
        lane = "all"
    mismatch = mismatch if mismatch is not None else load_mismatch_summary()
    focus = focus_snapshot(data)
    focus_id = str(focus["id"]) if focus and focus.get("valid") else None
    exclude = exclude_id or focus_id

    if lane == "ship":
        scored = _ship_candidates(data, mismatch=mismatch, exclude=exclude)
        scored.sort(key=_sort_key)
        return [_strip_internal(x) for x in scored[:limit]]

    if lane == "fix":
        scored = _fix_candidates(data, exclude=exclude)
        scored.sort(key=_sort_key)
        return [_strip_internal(x) for x in scored[:limit]]

    if lane == "debt":
        scored = _debt_candidates(data, exclude=exclude)
        scored.sort(key=_sort_key)
        return [_strip_internal(x) for x in scored[:limit]]

    if lane == "hygiene":
        occupied: set[str] = set()
        scored = _hygiene_candidates(mismatch, exclude=exclude, occupied_ids=occupied)
        scored.sort(key=_sort_key)
        return [_strip_internal(x) for x in scored[:limit]]

    # lane == "all": merge on unified scale
    ship = _ship_candidates(data, mismatch=mismatch, exclude=exclude)
    fix = _fix_candidates(data, exclude=exclude)
    debt = _debt_candidates(data, exclude=exclude)
    merged = ship + fix + debt
    occupied_ids = {str(i.get("id") or "") for i in merged if i.get("id")}
    _apply_hygiene_urgency_boost(merged, mismatch)
    hygiene = _hygiene_candidates(
        mismatch, exclude=exclude, occupied_ids=occupied_ids
    )
    merged.extend(hygiene)
    merged.sort(key=_sort_key)
    return [_strip_internal(x) for x in merged[:limit]]


def soft_blocker_banner(data: dict[str, Any]) -> dict[str, Any] | None:
    """Open severity=blocker without blocks intersecting focus — soft hint only."""
    focus = focus_snapshot(data)
    focus_id = str(focus["id"]) if focus and focus.get("valid") else None
    for card in data.get("backlog") or []:
        if not isinstance(card, dict) or not _is_open(card):
            continue
        if str(card.get("severity") or "") != "blocker":
            continue
        blocks = _blocks_list(card)
        if focus_id and focus_id in blocks:
            continue  # already handled by Continue unblock
        if not blocks:
            return {
                "id": card.get("id"),
                "name": card.get("name"),
                "message": (
                    "Open blocker without blocks[] — appears in Queue by severity "
                    "(does not steal Continue)"
                ),
            }
    return None


def count_open_fix_urgent(data: dict[str, Any]) -> int:
    n = 0
    for card in data.get("backlog") or []:
        if not isinstance(card, dict) or card.get("type") != "bug" or not _is_open(card):
            continue
        if str(card.get("severity") or "") in {"blocker", "high"}:
            n += 1
    return n


def build_next_payload(
    data: dict[str, Any],
    *,
    mismatch: dict[str, Any] | None = None,
    lane: str = "all",
    limit: int = 7,
    mvp_only: bool = False,
) -> dict[str, Any]:
    from pulse_lib.next_actions import health_summary

    mismatch = mismatch if mismatch is not None else load_mismatch_summary()
    lane = (lane or "all").strip().lower()
    if lane not in LANES:
        lane = "all"
    focus = focus_snapshot(data)
    cont = resolve_continue(data, mismatch=mismatch, lane=lane, queue_limit=limit)
    queue = rank_queue(data, lane=lane, limit=limit, mismatch=mismatch)
    # Legacy ``next``: ship-ranked incomplete features (no info boost) for older clients.
    legacy = rank_next_actions(
        data, limit=limit, mismatch=mismatch, mvp_only=mvp_only, boost_findings=False
    )
    return {
        "health": health_summary(data, mismatch),
        "focus": focus,
        "continue": cont,
        "lane": lane,
        "queue": queue,
        "fix_urgent_count": count_open_fix_urgent(data),
        "blocker_banner": soft_blocker_banner(data),
        "next": legacy,
    }
