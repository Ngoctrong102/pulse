#!/usr/bin/env python3
"""Board / backlog / tech-debt / phases / id-index views."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from pulse_lib.paths import (
    BOARD_PATH,
    ID_INDEX_PATH,
    PHASES_PATH,
    REPO_ROOT,
    TECHDEBT_PATH,
)

# Imported lazily-friendly constants from pulse_lib to avoid circular import at module load:
STATUS_BEGIN = "<!-- STATUS:BEGIN -->"
STATUS_END = "<!-- STATUS:END -->"

STATUSES = frozenset({"done", "partial", "todo", "blocked"})

STATUS_EMOJI = {
    "done": "✅",
    "partial": "🟡",
    "todo": "⬜",
    "blocked": "🚫",
}

BACKLOG_STATUS_LABEL = {
    "todo": "deferred",
    "partial": "in-progress",
    "done": "done",
    "blocked": "blocked",
}


def _sort_features(features: list[dict[str, Any]], sort_key: str = "priority") -> list[dict[str, Any]]:
    from pulse_lib import sort_features
    return sort_features(features, sort_key)


def _load_registry(data: dict[str, Any] | None = None) -> dict[str, Any]:
    from pulse_lib import load_registry
    return data or load_registry()


def _validate_registry(registry: dict[str, Any]) -> list[str]:
    from pulse_lib import validate_registry
    return validate_registry(registry)


def _status_error(msg: str):
    from pulse_lib import StatusError
    raise StatusError(msg)

# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def render_board(data: dict[str, Any]) -> str:
    features = _sort_features(list(data.get("features") or []), "priority")
    lines = [
        "# {0} Status Board".format(data.get("project") or "Project"),
        "",
        f"_Generated from `.pulse/features/` — {data.get('updated', date.today().isoformat())}. Do not edit by hand; run `.pulse/bin/pulse generate`._",
        "",
        "Also see [DRIFT.md](./DRIFT.md) (docs/spec ↔ board leftover remaining/mocks/unmapped IDs).",
        "",
        "| ID | Phase | Status | % | Pri | ROI | MVP | Remaining (short) | Mocks (short) |",
        "|---|:---:|:---:|:---:|:---:|:---:|:---:|---|---|",
    ]
    for f in features:
        rem = "; ".join((f.get("remaining") or [])[:2])
        mocks = "; ".join((f.get("mocks") or [])[:2])
        lines.append(
            "| `{id}` | {phase} | {emoji} {status} | {percent} | {priority} | {roi} | {mvp} | {rem} | {mocks} |".format(
                id=f.get("id"),
                phase=f.get("phase", ""),
                emoji=STATUS_EMOJI.get(str(f.get("status")), ""),
                status=f.get("status"),
                percent=f.get("percent"),
                priority=f.get("priority"),
                roi=f.get("roi"),
                mvp="yes" if f.get("mvp") else "",
                rem=rem.replace("|", "/"),
                mocks=mocks.replace("|", "/"),
            )
        )
    lines.extend(["", "## Filter hints", "", "- MVP only: entries with MVP=yes", "- Partial: status `partial`", "- Sort in CLI: `--sort roi|priority|percent|phase`", ""])
    backlog = render_backlog_section(data)
    if backlog:
        lines.extend([backlog, ""])
    return "\n".join(lines)


def render_backlog_section(data: dict[str, Any]) -> str:
    backlog = list(data.get("backlog") or [])
    if not backlog:
        return ""
    order = {"blocker": 0, "high": 1, "medium": 2, "low": 3}
    backlog = sorted(
        backlog,
        key=lambda c: (c.get("status") == "done", order.get(str(c.get("severity")), 9), c.get("id") or ""),
    )
    lines = [
        "## Backlog & Bugs",
        "",
        "_Cards `type: bug | tech-debt`. Log via `.pulse/bin/pulse new --type ...`._",
        "",
        "| ID | Type | Sev | Status | Where | Title |",
        "|---|:---:|:---:|:---:|---|---|",
    ]
    for c in backlog:
        status = str(c.get("status"))
        lines.append(
            "| `{id}` | {type} | {sev} | {emoji} {status} | {where} | {name} |".format(
                id=c.get("id"),
                type=c.get("type"),
                sev=c.get("severity", ""),
                emoji=STATUS_EMOJI.get(status, ""),
                status=BACKLOG_STATUS_LABEL.get(status, status),
                where=str(c.get("where", "")).replace("|", "/"),
                name=str(c.get("name", "")).replace("|", "/"),
            )
        )
    return "\n".join(lines)


def render_status_table(data: dict[str, Any]) -> str:
    features = _sort_features(list(data.get("features") or []), "phase")
    # Collapse to one row per phase number for 3.16 quick table (first feature per phase wins display)
    by_phase: dict[int, dict[str, Any]] = {}
    for f in features:
        phase = f.get("phase")
        if isinstance(phase, int) and phase not in by_phase:
            by_phase[phase] = f
    lines = [
        STATUS_BEGIN,
        "",
        f"**Quick status** (generated from `.pulse/features/` — {data.get('updated', '')}). Edit cards then `.pulse/bin/pulse generate`.",
        "",
        "| Phase | Name | Done? | % | Notes |",
        "|:---:|---|:---:|:---:|---|",
    ]
    for phase in sorted(by_phase):
        f = by_phase[phase]
        note_parts = []
        if f.get("mocks"):
            note_parts.append("mock: " + f["mocks"][0])
        if f.get("remaining"):
            note_parts.append(f["remaining"][0])
        note = "; ".join(note_parts)[:80]
        lines.append(
            f"| **{phase}** | {f.get('name')} | {STATUS_EMOJI.get(str(f.get('status')), '')} | {f.get('percent')} | {note} |"
        )
    counts = {s: 0 for s in STATUSES}
    for f in features:
        st = f.get("status")
        if st in counts:
            counts[st] += 1
    lines.extend(
        [
            "",
            f"**Registry summary:** {counts['done']} done · {counts['partial']} partial · {counts['todo']} todo · {counts['blocked']} blocked.",
            "",
            STATUS_END,
        ]
    )
    return "\n".join(lines)


def patch_phases_file(data: dict[str, Any], phases_path: Path = PHASES_PATH) -> None:
    block = render_status_table(data)
    text = phases_path.read_text(encoding="utf-8")
    if STATUS_BEGIN in text and STATUS_END in text:
        pattern = re.compile(
            re.escape(STATUS_BEGIN) + r".*?" + re.escape(STATUS_END),
            re.DOTALL,
        )
        text = pattern.sub(block, text)
    else:
        anchor = "## Quick status"
        if anchor in text or "## Trạng thái nhanh" in text:
            text = text.replace(
                "## Trạng thái nhanh (cập nhật 2026-08-08)",
                block + "\n\n## Quick status (legacy checklist below)",
                1,
            )
            text = text.replace(
                "## Trạng thái nhanh",
                "## Quick status",
            )
        else:
            text = block + "\n\n" + text
    phases_path.write_text(text, encoding="utf-8")


def render_tech_debt_doc(data: dict[str, Any]) -> str:
    cards = [c for c in (data.get("backlog") or []) if _card_type(c) == "tech-debt"]
    order = {"blocker": 0, "high": 1, "medium": 2, "low": 3}
    cards = sorted(
        cards,
        key=lambda c: (
            str(c.get("status")) == "done",
            order.get(str(c.get("severity")), 9),
            c.get("id") or "",
        ),
    )
    open_cards = [c for c in cards if str(c.get("status")) != "done"]
    done_cards = [c for c in cards if str(c.get("status")) == "done"]
    ids = [c["id"] for c in cards if c.get("id")]
    refs = sorted({r for c in cards for r in (c.get("refs") or [])})
    lines: list[str] = ["---", "doc_id: TECH-DEBT", "type: technical", "generated: true"]
    if ids:
        lines.append("ids:")
        lines.extend(f"  - {i}" for i in ids)
    if refs:
        lines.append("status_refs:")
        lines.extend(f"  - {r}" for r in refs)
    lines.extend(
        [
            "---",
            "",
            "# Tech Debt / Refactor Backlog (TECH-DEBT)",
            "",
            "**Generated view** from `type: tech-debt` cards in `.pulse/features/`. "
            "Do not edit by hand — add/change with `.pulse/bin/pulse new --type tech-debt ...` "
            "or `set --feature TECH-DEBT-NNN ...`, then `generate`.",
            "",
            "Status convention: `todo` = deferred · `partial` = in-progress · `done`.",
            f"Open: **{len(open_cards)}** · done (collapsed): **{len(done_cards)}**.",
            "",
        ]
    )
    if not cards:
        lines.append("_No tech-debt cards yet._")
        return "\n".join(lines) + "\n"
    for c in open_cards:
        status = str(c.get("status"))
        label = BACKLOG_STATUS_LABEL.get(status, status)
        lines.append(f"## {c.get('id')} — {c.get('name', '')}")
        lines.append("")
        if c.get("where"):
            lines.append(f"- **Where:** {c['where']}")
        if c.get("why"):
            lines.append(f"- **Smell / why it hurts:** {c['why']}")
        if c.get("proposed_fix"):
            lines.append(f"- **Proposed fix:** {c['proposed_fix']}")
        if c.get("refs"):
            lines.append(f"- **Refs:** {', '.join(c['refs'])}")
        lines.append(
            f"- **Severity:** {c.get('severity', '')} · **Status:** {status} ({label})"
        )
        lines.append("")
    if done_cards:
        lines.append("## Done (collapsed)")
        lines.append("")
        for c in done_cards:
            lines.append(f"- `{c.get('id')}` — {c.get('name', '')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _card_type(card: dict[str, Any]) -> str:
    return str(card.get("type") or "feature")


def parse_frontmatter(path: Path) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    raw = text[3:end].strip()
    data = yaml.safe_load(raw)
    return data if isinstance(data, dict) else None


def build_id_catalog(docs_root: Path | None = None) -> tuple[dict[str, str], list[str]]:
    """Return id -> relative path, and warnings."""
    root = docs_root or (REPO_ROOT / "docs")
    catalog: dict[str, str] = {}
    warnings: list[str] = []
    for path in sorted(root.rglob("*.md")):
        rel = str(path.relative_to(REPO_ROOT))
        fm = parse_frontmatter(path)
        if fm and isinstance(fm.get("ids"), list):
            for req_id in fm["ids"]:
                if not isinstance(req_id, str):
                    continue
                if req_id in catalog and catalog[req_id] != rel:
                    warnings.append(f"duplicate id {req_id}: {catalog[req_id]} vs {rel}")
                catalog[req_id] = rel
            continue
        for match in re.finditer(r"^##\s+((?:FR|NFR|TECH|UF|DEC)[-A-Z0-9.]+)\b", path.read_text(encoding="utf-8"), re.M):
            req_id = match.group(1)
            if req_id not in catalog:
                catalog[req_id] = rel
                warnings.append(f"missing frontmatter; inferred {req_id} from headings in {rel}")
    return catalog, warnings


def render_id_index(catalog: dict[str, str]) -> str:
    lines = [
        "# Requirement ID index",
        "",
        "_Generated — run `.pulse/bin/pulse generate`._",
        "",
        "| ID | Doc |",
        "|---|---|",
    ]
    for req_id in sorted(catalog):
        lines.append(f"| `{req_id}` | [{catalog[req_id]}](../../{catalog[req_id]}) |")
    lines.append("")
    return "\n".join(lines)


def generate_views(data: dict[str, Any] | None = None) -> None:
    """Core generate only (board / id-index / tech-debt / phases).

    Optional views (DRIFT, cleancode scoreboard, …) are registered by plugins
    via ``PulseApp.on_generate`` and run from the CLI after this function.
    """
    registry = _load_registry(data)
    errors = _validate_registry(registry)
    if errors:
        _status_error("validate failed:\n- " + "\n- ".join(errors))
    BOARD_PATH.write_text(render_board(registry), encoding="utf-8")
    catalog, _warnings = build_id_catalog()
    ID_INDEX_PATH.write_text(render_id_index(catalog), encoding="utf-8")
    if TECHDEBT_PATH.parent.is_dir():
        TECHDEBT_PATH.write_text(render_tech_debt_doc(registry), encoding="utf-8")
    if PHASES_PATH.is_file():
        phases = PHASES_PATH.read_text(encoding="utf-8")
        if STATUS_BEGIN not in phases:
            PHASES_PATH.write_text(f"{STATUS_BEGIN}\n{STATUS_END}\n\n" + phases, encoding="utf-8")
        patch_phases_file(registry)
    elif PHASES_PATH.parent.is_dir():
        PHASES_PATH.write_text(
            f"# Implementation phases\n\n{STATUS_BEGIN}\n{STATUS_END}\n",
            encoding="utf-8",
        )
        patch_phases_file(registry)


