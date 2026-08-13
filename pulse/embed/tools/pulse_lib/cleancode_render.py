#!/usr/bin/env python3
"""Clean-code board / clean-code.md rendering."""

from __future__ import annotations

from typing import Any

from pulse_lib.cleancode_metrics import (
    finding_index,
    module_metrics,
    score_band,
    stale_module_ids,
)

def _averages(mods: list[dict[str, Any]]) -> tuple[int, int, float | None]:
    scored = [m for m in mods if isinstance(m.get("score"), int)]
    avg = round(sum(m["score"] for m in scored) / len(scored), 1) if scored else None
    return (len(scored), len(mods), avg)


def _metrics_map(
    mods: list[dict[str, Any]], findings_index: dict[str, dict[str, Any]] | None = None
) -> dict[str, dict[str, Any]]:
    idx = finding_index() if findings_index is None else findings_index
    return {str(m.get("id")): module_metrics(m, idx) for m in mods}


def _structure_average(metrics: dict[str, dict[str, Any]]) -> float | None:
    if not metrics:
        return None
    return round(sum(v["structure_score"] for v in metrics.values()) / len(metrics), 1)


def _ordered_modules(
    mods: list[dict[str, Any]],
    *,
    stale_ids: set[str],
    metrics: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Stale / dirty structure / open findings first."""

    def key(m: dict[str, Any]) -> tuple[Any, ...]:
        mid = str(m.get("id") or "")
        met = metrics.get(mid) or {}
        return (
            0 if mid in stale_ids else 1,
            int(met.get("structure_score") if met.get("structure_score") is not None else 999),
            -int(met.get("open_findings") or 0),
            str(m.get("area") or ""),
            mid,
        )

    return sorted(mods, key=key)


def render_cleancode_board_section(
    mods: list[dict[str, Any]], stale_ids: set[str] | None = None
) -> str:
    if not mods:
        return ""
    if stale_ids is None:
        stale_ids = stale_module_ids(mods)
    metrics = _metrics_map(mods)
    scanned, total, ai_avg = _averages(mods)
    struct_avg = _structure_average(metrics)
    open_total = sum(v["open_findings"] for v in metrics.values())
    lines = [
        "## Clean Code",
        "",
        "_Structure & Findings auto-update on every `generate` (deterministic, like the backlog); "
        "AI score /100 from the `quality-raise` rubric needs a manual rescan. "
        + f"Struct avg {struct_avg} · {open_total} open findings · AI scanned {scanned}/{total}"
        + (f" (avg {ai_avg})" if ai_avg is not None else "")
        + (f" · {len(stale_ids)} need rescan ⚠️" if stale_ids else "")
        + ". Use Scan/Fix buttons in the extension panel._",
        "",
        "| Module | Area | AI | Struct | Findings | Scanned |",
        "|---|:---:|:---:|:---:|:---:|:---:|",
    ]
    for m in _ordered_modules(mods, stale_ids=stale_ids, metrics=metrics):
        mid = str(m.get("id"))
        met = metrics[mid]
        ai_emoji, _ = score_band(m.get("score"))
        score = m.get("score")
        ai_cell = f"{ai_emoji} {score}" if isinstance(score, int) else f"{ai_emoji} —"
        s_emoji, _ = score_band(met["structure_score"])
        struct_cell = f"{s_emoji} {met['structure_score']}"
        fnd = f"{met['open_findings']}/{met['total_findings']}"
        if met["open_findings"]:
            fnd += " ⚠️"
        scanned_cell = str(m.get("scanned_at") or "—")
        if mid in stale_ids:
            scanned_cell += " ⚠️"
        lines.append(
            f"| `{mid}` | {m.get('area', '')} | {ai_cell} | {struct_cell} | {fnd} | {scanned_cell} |"
        )
    return "\n".join(lines)


def render_cleancode_view(
    mods: list[dict[str, Any]], stale_ids: set[str] | None = None
) -> str:
    if stale_ids is None:
        stale_ids = stale_module_ids(mods)
    metrics = _metrics_map(mods)
    scanned, total, avg = _averages(mods)
    struct_avg = _structure_average(metrics)
    open_total = sum(v["open_findings"] for v in metrics.values())
    lines: list[str] = [
        "---",
        "doc_id: CLEAN-CODE",
        "type: technical",
        "generated: true",
        "---",
        "",
        "# Clean-Code Scoreboard",
        "",
        "**Generated view** from `.pulse/cleancode/`. Do not edit by hand.",
        "",
        "Two score layers:",
        "",
        "- **Struct** (deterministic, auto-updates each `generate` like the backlog): penalizes files "
        "over the LOC budget (>300 py / >400 swift) and **open findings** (linked tech-debt cards not `done`). "
        "Closing a card or splitting a file raises the score automatically.",
        "- **AI** (/100 from the `quality-raise` rubric): set via "
        "`.pulse/bin/pulse cleancode set --module <id> --score N`; code changes flag ⚠️ rescan needed.",
        "",
        f"Struct average **{struct_avg}**/100 · **{open_total}** open findings · "
        f"AI scanned **{scanned}/{total}**"
        + (f" (avg **{avg}**/100)" if avg is not None else "")
        + (f" · **{len(stale_ids)}** need rescan ⚠️." if stale_ids else "."),
        "",
        "Scale: 🟢 clean (>=85) · 🟡 warn (60-84) · 🔴 dirty (<60) · ⚪ unscanned · ⚠️ needs rescan.",
        "",
        "| Module | Area | AI | Struct | Findings (open/total) | Scanned | Summary |",
        "|---|:---:|:---:|:---:|:---:|:---:|---|",
    ]
    for m in _ordered_modules(mods, stale_ids=stale_ids, metrics=metrics):
        mid = str(m.get("id"))
        met = metrics[mid]
        emoji, _label = score_band(m.get("score"))
        score = m.get("score")
        ai_cell = f"{emoji} {score}" if isinstance(score, int) else f"{emoji} —"
        if mid in stale_ids:
            ai_cell += " ⚠️"
        s_emoji, _s = score_band(met["structure_score"])
        struct_cell = f"{s_emoji} {met['structure_score']}"
        fnd = f"{met['open_findings']}/{met['total_findings']}"
        lines.append(
            "| `{id}` | {area} | {ai} | {struct} | {fnd} | {scanned} | {summary} |".format(
                id=mid,
                area=m.get("area", ""),
                ai=ai_cell,
                struct=struct_cell,
                fnd=fnd,
                scanned=m.get("scanned_at") or "—",
                summary=str(m.get("summary", "")).replace("|", "/"),
            )
        )
    lines.append("")
    return "\n".join(lines)
