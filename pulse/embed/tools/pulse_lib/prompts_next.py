"""Next-action ranking and next/backlog paste prompts."""

from __future__ import annotations

from typing import Any

from pulse_lib.prompt_common import (
    SPECKIT_LOOP,
    _card_path,
    _list_preview,
    _quality_raise_block,
    _speckit_enabled,
    _speckit_feature_block,
    _speckit_next_playbook,
    _speckit_rules_block,
    feature_spec_insights,
    findings_for_feature,
    inspect_spec_slice,
    load_mismatch_summary,
)
from pulse_lib.tag_audit import project_label

def list_sub_actions(
    feat: dict[str, Any],
    feat_findings: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Coarse next-action chunks for one feature.

    Returns [] or a single conceptual action path when the feature fits one prompt.
    Returns 2+ items when the board should show **Next actions** + a sub-table.
    Does not explode Spec Kit checkboxes — prefer remaining bullets / one Spec Kit gate.
    """
    remaining = [str(x) for x in (feat.get("remaining") or []) if str(x).strip()]
    mocks = [str(x) for x in (feat.get("mocks") or []) if str(x).strip()]
    specs = feature_spec_insights(feat)
    findings = feat_findings or []
    # Opt-in: board Next-actions table = one chunk per remaining (surgical UX), skip Spec Kit collapse.
    expand_remaining = str(feat.get("next_chunks") or "").strip().lower() in {
        "remaining",
        "per_remaining",
        "chunks",
    }

    # Critical detect only: keep a single investigate prompt when there is no other work list
    critical = [f for f in findings if str(f.get("severity") or "") == "critical"]
    if critical and not remaining and not mocks:
        return []

    # No slice yet + several remainings → one Spec Kit gate (single Next action, not a table)
    # unless next_chunks: remaining (curated per-item UX workstreams).
    if not specs and len(remaining) >= 2 and not expand_remaining:
        return []

    subs: list[dict[str, Any]] = []

    open_impl = next(
        (
            sp
            for sp in specs
            if sp.get("exists")
            and sp.get("has_tasks")
            and int(sp.get("open_tasks") or 0) > 0
        ),
        None,
    )
    need_plan = next(
        (
            sp
            for sp in specs
            if sp.get("exists") and sp.get("has_spec") and not sp.get("has_tasks")
        ),
        None,
    )

    if need_plan and len(remaining) >= 2:
        subs.append(
            {
                "key": "speckit-plan-tasks",
                "title": f"Finish Spec Kit plan→tasks on `{need_plan['path']}`",
                "kind": "speckit",
            }
        )
    elif open_impl and not remaining:
        # One implement prompt — not multi
        return []

    # Remaining bullets are the natural coarse chunks (already curated in YAML)
    if len(remaining) >= 2:
        for i, rem in enumerate(remaining):
            title = rem
            if open_impl:
                title = f"Implement via `{open_impl['path']}`: {rem}"
            subs.append({"key": f"rem-{i}", "title": title, "kind": "remaining"})
    elif len(remaining) == 1 and need_plan:
        # plan missing + one remaining → still two steps
        subs.append(
            {
                "key": "speckit-plan-tasks",
                "title": f"Finish Spec Kit plan→tasks on `{need_plan['path']}`",
                "kind": "speckit",
            }
        )
        subs.append({"key": "rem-0", "title": remaining[0], "kind": "remaining"})

    # Mocks as separate chunk only when we already have multi work
    if mocks and len(subs) >= 2:
        if len(mocks) == 1:
            subs.append(
                {
                    "key": "mock-0",
                    "title": f"Close or remove mock: {mocks[0]}",
                    "kind": "mock",
                }
            )
        else:
            subs.append(
                {
                    "key": "mocks",
                    "title": f"Close or remove {len(mocks)} mocks",
                    "kind": "mock",
                }
            )

    return subs if len(subs) >= 2 else []


def _recommended_action(feat: dict[str, Any], feat_findings: list[dict[str, Any]]) -> tuple[str, str]:
    """Return (action, why)."""
    remaining = [str(x) for x in (feat.get("remaining") or []) if x]
    mocks = [str(x) for x in (feat.get("mocks") or []) if x]
    specs = feature_spec_insights(feat)
    expand_remaining = str(feat.get("next_chunks") or "").strip().lower() in {
        "remaining",
        "per_remaining",
        "chunks",
    }

    # Detect override: always for critical/warning; info only when not using curated next_chunks.
    blocking = [
        f
        for f in feat_findings
        if str(f.get("severity") or "") in {"critical", "warning"}
        or not expand_remaining
    ]
    if blocking:
        top = blocking[0]
        msg = str(top.get("message") or top.get("code") or "mismatch finding")
        return (
            f"Investigate detect finding ({top.get('severity', 'info')}): {msg}",
            f"Detect flagged this feature: {msg}",
        )

    for sp in specs:
        if not _speckit_enabled():
            break
        if sp.get("exists") and sp.get("has_tasks") and int(sp.get("open_tasks") or 0) > 0:
            return (
                f"Continue Spec Kit implement on `{sp['path']}` "
                f"({sp['open_tasks']} open tasks in tasks.md)",
                "Feature already has a Spec Kit slice with unchecked tasks — prefer speckit-implement",
            )
        if sp.get("exists") and sp.get("has_spec") and not sp.get("has_tasks"):
            return (
                f"Finish Spec Kit loop on `{sp['path']}` (plan/tasks missing)",
                "spec.md exists but tasks.md incomplete — run plan→tasks before implement",
            )

    if remaining:
        if (
            _speckit_enabled()
            and not specs
            and len(remaining) >= 2
            and not expand_remaining
        ):
            return (
                f"Start Spec Kit slice for remaining work (first: {remaining[0]})",
                "No specs[] linked and multiple remaining items — brownfield specify→… before large coding",
            )
        why = f"Top remaining item for {feat.get('id')}"
        if expand_remaining:
            why = (
                f"Per-card / curated chunk for {feat.get('id')} "
                "(next_chunks: remaining — surgical unless chunk says Spec Kit)"
            )
        return (remaining[0], why)
    if mocks:
        return (
            f"Close or document mock: {mocks[0]}",
            "Mocks still listed — clarify if production-ready",
        )
    return (
        "Re-run .pulse/bin/pulse mismatch detect then refresh .pulse/features/ if needed",
        "No remaining bullets; verify evidence matches status",
    )


def rank_next_actions(
    data: dict[str, Any],
    *,
    limit: int = 3,
    mismatch: dict[str, Any] | None = None,
    mvp_only: bool = False,
    boost_findings: bool = False,
) -> list[dict[str, Any]]:
    """Deterministic next-up list for incomplete features.

    ``boost_findings`` default False (specs/016): detect info must not steal Ship #1.
    Pass True only for legacy/debug.
    """
    mismatch = mismatch if mismatch is not None else load_mismatch_summary()
    features = list(data.get("features") or [])
    scored: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    for feat in features:
        if not isinstance(feat, dict):
            continue
        status = feat.get("status")
        if status == "done":
            continue
        if mvp_only and not feat.get("mvp"):
            continue
        fid = str(feat.get("id") or "")
        feat_findings = findings_for_feature(mismatch, fid)
        # For action text, only surface critical/warning unless boosting all findings.
        action_findings = (
            feat_findings
            if boost_findings
            else [
                f
                for f in feat_findings
                if str(f.get("severity") or "") in {"critical", "warning"}
            ]
        )
        action, why = _recommended_action(feat, action_findings)
        subs = list_sub_actions(feat, action_findings)
        mvp_rank = 0 if feat.get("mvp") else 1
        priority = int(feat.get("priority") or 99)
        roi = -int(feat.get("roi") or 0)
        if boost_findings:
            finding_boost = 0 if feat_findings else 1
            key = (mvp_rank, finding_boost, priority, roi, fid)
        else:
            # specs/016 Ship: mvp → priority → roi only (info never boosts; critical also
            # does not jump the P/ROI order — surface via Hygiene / badges instead).
            key = (mvp_rank, priority, roi, fid)
        scored.append(
            (
                key,
                {
                    "id": fid,
                    "name": feat.get("name"),
                    "phase": feat.get("phase"),
                    "status": status,
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
                    "finding_count": len(feat_findings),
                    "spec_insights": feature_spec_insights(feat),
                    "sub_actions": subs,
                    "multi": len(subs) >= 2,
                },
            )
        )
    scored.sort(key=lambda x: x[0])
    return [item for _, item in scored[:limit]]


def _find_backlog_card(data: dict[str, Any], card_id: str) -> dict[str, Any] | None:
    return next(
        (
            c
            for c in (data.get("backlog") or [])
            if isinstance(c, dict) and c.get("id") == card_id
        ),
        None,
    )


def _backlog_card_block(card: dict[str, Any]) -> list[str]:
    return [
        "## Card",
        f"name: {card.get('name')}",
        f"severity: {card.get('severity')} · priority: {card.get('priority')} · "
        f"roi: {card.get('roi')} · status: {card.get('status')}",
        f"where: {card.get('where')}",
        f"why: {card.get('why')}",
        f"proposed_fix: {card.get('proposed_fix')}",
        f"refs: {card.get('refs')}",
    ]


def build_backlog_action_prompt(card: dict[str, Any]) -> str:
    ctype = str(card.get("type") or "tech-debt")
    lines = [
        f"Handle backlog item `{card.get('id')}` ({ctype}) in repo {project_label()}.",
        "",
        "## Principles",
        "- Start with a plan for this card only (read large files before splitting/editing).",
        "- Do only this card; minimal scope; no drive-by refactors.",
        "- Keep gates green: pytest + ruff + black --check + mypy (as relevant to the stack).",
        "",
        *_backlog_card_block(card),
        "",
        *_backlog_speckit_block(card),
        "",
        "## Close the status loop",
        f"When finished: `.pulse/bin/pulse set --feature {card.get('id')} --status done` then `generate`.",
        "If not fully done: update the description / remove finished parts; keep status accurate.",
        "Reply in English unless the user is chatting in another language.",
    ]
    return "\n".join(lines)


def _backlog_speckit_block(card: dict[str, Any]) -> list[str]:
    """Guide the agent to reach for Spec Kit when a backlog card is large/complex."""
    ref = ""
    refs = card.get("refs")
    if isinstance(refs, list) and refs:
        ref = str(refs[0])
    elif isinstance(refs, str) and refs.strip():
        ref = refs.strip()
    slice_hint = (
        f"attach the slice path to the card `specs:` (and `--ref {ref}` if `speckit-specify` creates a new card)"
        if ref
        else "attach the slice path to the card `specs:`"
    )
    return [
        "## Spec Kit — use when the card is large/complex",
        "**Before coding, classify this card:**",
        "- **Small / surgical** (1–2 files, clear fix, no new acceptance): edit directly, "
        "**do not** open a Spec Kit slice. Still read related `docs/` first.",
        "- **Large / complex** (many files/modules, broad refactor, architecture change, "
        "new behavior/acceptance, or high regression risk): **use the Spec Kit brownfield loop** — "
        f"{SPECKIT_LOOP}.",
        f"  - After `speckit-specify`: {slice_hint}.",
        "  - Treat `docs/` as product SoT; the slice only implements locked scope — do not invent behavior.",
        "  - Implement via `tasks.md` (skill `speckit-implement`); before claiming done run detect; optional `speckit-converge`.",
        "- Unsure about scope? Read the main file in `where` first, then decide — if it grows past 1–2 files / many new acceptance criteria, escalate to Spec Kit.",
        *_speckit_rules_block(),
    ]


def build_next_action_prompt(
    data: dict[str, Any],
    *,
    feature_id: str | None = None,
    mismatch: dict[str, Any] | None = None,
    sub_index: int | None = None,
    lane: str = "all",
) -> str:
    if feature_id:
        backlog_card = _find_backlog_card(data, feature_id)
        if backlog_card is not None:
            return build_backlog_action_prompt(backlog_card)
    mismatch = mismatch if mismatch is not None else load_mismatch_summary()

    # No --feature: follow Continue target (focus_step | unblock | promote_queue).
    if not feature_id:
        from pulse_lib.next_ranking import resolve_continue

        cont = resolve_continue(data, mismatch=mismatch, lane=lane)
        cid = cont.get("id")
        if not cid:
            return "No next action left (all features done or registry empty)."
        if cont.get("kind") == "unblock":
            backlog_card = _find_backlog_card(data, str(cid))
            if backlog_card is not None:
                return build_backlog_action_prompt(backlog_card)
        feature_id = str(cid)

    items = rank_next_actions(data, limit=50, mismatch=mismatch, boost_findings=False)
    item = None
    feat: dict[str, Any] | None = None
    if feature_id:
        item = next((x for x in items if x["id"] == feature_id), None)
        feat = next(
            (
                f
                for f in (data.get("features") or [])
                if isinstance(f, dict) and f.get("id") == feature_id
            ),
            None,
        )
        if item is None and feat:
            findings = findings_for_feature(mismatch, feature_id)
            blocking = [
                f
                for f in findings
                if str(f.get("severity") or "") in {"critical", "warning"}
            ]
            action, why = _recommended_action(feat, blocking)
            subs = list_sub_actions(feat, blocking)
            item = {
                "id": feature_id,
                "name": feat.get("name"),
                "action": action,
                "why": why,
                "docs": feat.get("docs") or {},
                "specs": list(feat.get("specs") or []),
                "remaining": list(feat.get("remaining") or []),
                "mocks": list(feat.get("mocks") or []),
                "sub_actions": subs,
                "multi": len(subs) >= 2,
            }
        if item is None:
            backlog_card = _find_backlog_card(data, feature_id)
            if backlog_card is not None:
                return build_backlog_action_prompt(backlog_card)
    else:
        item = items[0] if items else None
        if item:
            feat = next(
                (
                    f
                    for f in (data.get("features") or [])
                    if isinstance(f, dict) and f.get("id") == item["id"]
                ),
                None,
            )
    if not item:
        return "No next action left (all features done or registry empty)."

    subs = list(item.get("sub_actions") or [])
    focus_title = None
    if sub_index is not None and 0 <= sub_index < len(subs):
        focus_title = str(subs[sub_index].get("title") or "")
        item = {**item, "action": focus_title, "why": f"Sub-action {sub_index + 1}/{len(subs)} for {item['id']}"}

    lines = [
        (
            f"Perform the next action on {project_label()} (Spec Kit-aware)."
            if _speckit_enabled()
            else f"Perform the next action on {project_label()} "
            "(surgical; update the board afterward)."
        ),
        "",
        *_speckit_rules_block(),
        "",
        f"Feature: `{item['id']}` — {item.get('name')}",
        f"Card: `{_card_path(str(item['id']))}`",
        f"Action: {item.get('action')}",
        f"Why: {item.get('why')}",
        f"docs={item.get('docs')} specs={item.get('specs')}",
        f"remaining(top)={_list_preview(item.get('remaining'), limit=5)}",
        f"mocks(top)={_list_preview(item.get('mocks'), limit=5)}",
    ]
    if focus_title and len(subs) >= 2:
        lines.extend(
            [
                "",
                f"## Focus sub-action ({sub_index + 1}/{len(subs)})",
                f"- **Do only** this chunk in this prompt: {focus_title}",
                "- Other chunks (do not finish them here):",
            ]
        )
        for i, s in enumerate(subs):
            mark = "→" if i == sub_index else "·"
            lines.append(f"  {mark} [{i + 1}] {s.get('title')}")
    elif item.get("multi") and subs:
        lines.extend(["", "## Sub-actions (large feature — one chunk at a time)", ""])
        for i, s in enumerate(subs):
            lines.append(f"- [{i + 1}] {s.get('title')}")
        lines.append(
            "If this prompt does not specify a sub-index, do chunk #1 then stop; sync YAML before the next chunk."
        )
    if feat:
        lines.extend(_speckit_feature_block(feat))
    lines.extend(_speckit_next_playbook(item, feat))
    lines.extend(
        [
            "",
            "## Close the status loop",
            "When finished: update `.pulse/features/` (done/remaining/mocks/percent/status), "
            "run `.pulse/bin/pulse generate`.",
            "Before claiming done: `.pulse/bin/pulse mismatch detect`. "
            "Do not run mismatch-heal unless I explicitly ask.",
            "Do not set `status: done` while `mocks` or `remaining` is non-empty.",
        ]
    )
    return "\n".join(lines)

