"""Explain project/feature paste prompts."""

from __future__ import annotations

from typing import Any

from pulse_lib.prompt_common import (
    _card_path,
    _list_preview,
    _speckit_feature_block,
    _speckit_rules_block,
    feature_spec_insights,
    findings_for_feature,
    health_summary,
    load_mismatch_summary,
)
from pulse_lib.prompts_next import _backlog_card_block, _find_backlog_card
from pulse_lib.tag_audit import project_label


def build_explain_project_prompt(data: dict[str, Any], mismatch: dict[str, Any] | None = None) -> str:
    mismatch = mismatch if mismatch is not None else load_mismatch_summary()
    health = health_summary(data, mismatch)
    non_done = [
        f
        for f in (data.get("features") or [])
        if isinstance(f, dict) and f.get("status") != "done"
    ]
    non_done.sort(key=lambda f: (int(f.get("priority") or 99), -int(f.get("roi") or 0)))
    lines = [
        f"Explain the status of project {project_label()} (bullets OK).",
        "Call out easy-to-misread status, risks of claiming done early, and important detect findings.",
        "BOARD/`.pulse/features/` = progress; editing docs does not update the board — write a card + `generate`.",
        "",
        *_speckit_rules_block(),
        "",
        f"updated={health.get('updated')} counts={health['counts']}",
        f"detect: critical={mismatch.get('critical')} warning={mismatch.get('warning')} "
        f"info={mismatch.get('info')}",
        f"open_work={health.get('open_work')} drift={health.get('drift')}",
        "Details: `.pulse/features/`, `.pulse/DRIFT.md` (summary — no need for full JSON).",
        "",
        "Top incomplete:",
    ]
    for f in non_done[:5]:
        rem = _list_preview(f.get("remaining") or [], limit=2)
        lines.append(
            f"- `{f.get('id')}` {f.get('name')} — {f.get('status')} {f.get('percent')}% "
            f"P{f.get('priority')} remaining={rem} → {_card_path(str(f.get('id')))}"
        )
        for sp in feature_spec_insights(f):
            if sp["exists"]:
                lines.append(
                    f"  slice `{sp['path']}`: open_tasks={sp['open_tasks']} "
                    f"done_tasks={sp['done_tasks']}"
                )
    crit = [
        x
        for x in (mismatch.get("findings") or [])
        if isinstance(x, dict) and x.get("severity") in {"critical", "warning"}
    ][:5]
    if crit:
        lines.append("")
        lines.append("Detect (critical/warning top):")
        for x in crit:
            lines.append(
                f"- [{x.get('severity')}] {x.get('feature_id') or '-'}: "
                f"{x.get('code')} — {x.get('message')}"
            )
    lines.append("")
    lines.append("Reply in English unless the user is chatting in another language.")
    return "\n".join(lines)


def build_explain_feature_prompt(
    data: dict[str, Any],
    feature_id: str,
    mismatch: dict[str, Any] | None = None,
) -> str:
    backlog_card = _find_backlog_card(data, feature_id)
    if backlog_card is not None:
        ctype = str(backlog_card.get("type") or "tech-debt")
        return "\n".join(
            [
                f"Explain backlog item `{feature_id}` ({ctype}) in project {project_label()}.",
                "Cover severity/priority/roi meaning, cost of delaying, risks when fixing, "
                "and dependency order if any.",
                "",
                *_backlog_card_block(backlog_card),
                "",
                "Be clear; bullets OK. Reply in English unless the user is chatting in another language.",
            ]
        )
    mismatch = mismatch if mismatch is not None else load_mismatch_summary()
    feat = next(
        (f for f in (data.get("features") or []) if isinstance(f, dict) and f.get("id") == feature_id),
        None,
    )
    if not feat:
        return f"Feature id `{feature_id}` not found in .pulse/features/."
    findings = findings_for_feature(mismatch, feature_id)
    lines = [
        f"Explain feature `{feature_id}` (`{feat.get('name')}`) — {project_label()}.",
        "percent/status, remaining/mocks, risks of claiming done early.",
        f"Card: `{_card_path(feature_id)}` (read the file for detail — do not invent from memory).",
        "",
        *_speckit_rules_block(),
        "",
        f"status={feat.get('status')} percent={feat.get('percent')} "
        f"priority={feat.get('priority')} roi={feat.get('roi')} mvp={feat.get('mvp')}",
        f"docs={feat.get('docs')}",
        f"specs={feat.get('specs')}",
        f"remaining(top)={_list_preview(feat.get('remaining'), limit=5)}",
        f"mocks(top)={_list_preview(feat.get('mocks'), limit=5)}",
        f"evidence.paths_any={((feat.get('evidence') or {}).get('paths_any') if isinstance(feat.get('evidence'), dict) else None)}",
        *_speckit_feature_block(feat),
    ]
    if findings:
        lines.append("")
        lines.append("Detect findings for this feature (top):")
        for x in findings[:5]:
            lines.append(f"- [{x.get('severity')}] {x.get('code')}: {x.get('message')}")
    lines.append("")
    lines.append("Reply in English unless the user is chatting in another language.")
    return "\n".join(lines)
