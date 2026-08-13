"""Shared helpers for pulse paste-ready prompts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pulse_lib.paths import BOARD_PATH, FEATURES_DIR as REGISTRY_PATH, MISMATCH_REPORT, PROJECT_ROOT, REPO_ROOT
from pulse_lib.tag_audit import code_roots, project_label, tag_marker

def _meta_flags() -> dict:
    """Lightweight meta read (avoid circular imports via tag_audit helpers)."""
    from pulse_lib.tag_audit import _load_meta

    return _load_meta()


def _speckit_enabled() -> bool:
    """Spec Kit guidance is optional: meta.speckit, else on if specs/ exists."""
    meta = _meta_flags()
    if "speckit" in meta:
        return bool(meta.get("speckit"))
    return (REPO_ROOT / "specs").is_dir()


# Brownfield Spec Kit loop (constitution)
SPECKIT_LOOP = "specify → clarify? → plan → tasks → implement → analyze → converge"

def load_mismatch_summary(path: Path | None = None) -> dict[str, Any]:
    report_path = path or MISMATCH_REPORT
    if not report_path.is_file():
        return {"exists": False, "critical": 0, "warning": 0, "info": 0, "findings": []}
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"exists": False, "critical": 0, "warning": 0, "info": 0, "findings": []}
    summary = data.get("summary") or {}
    findings = data.get("findings") or []
    return {
        "exists": True,
        "critical": int(summary.get("critical") or 0),
        "warning": int(summary.get("warning") or 0),
        "info": int(summary.get("info") or 0),
        "findings": findings if isinstance(findings, list) else [],
    }


def findings_for_feature(mismatch: dict[str, Any], feature_id: str) -> list[dict[str, Any]]:
    return [
        f
        for f in mismatch.get("findings") or []
        if isinstance(f, dict) and f.get("feature_id") == feature_id
    ]


def inspect_spec_slice(spec_rel: str) -> dict[str, Any]:
    """Summarize a specs/NNN-* directory for prompts."""
    root = REPO_ROOT / spec_rel
    info: dict[str, Any] = {
        "path": spec_rel,
        "exists": root.is_dir(),
        "has_spec": False,
        "has_plan": False,
        "has_tasks": False,
        "open_tasks": 0,
        "done_tasks": 0,
    }
    if not root.is_dir():
        return info
    info["has_spec"] = (root / "spec.md").is_file()
    info["has_plan"] = (root / "plan.md").is_file()
    tasks = root / "tasks.md"
    info["has_tasks"] = tasks.is_file()
    if tasks.is_file():
        text = tasks.read_text(encoding="utf-8")
        info["open_tasks"] = len(re.findall(r"^\s*-\s+\[\s\]\s+", text, re.M))
        info["done_tasks"] = len(re.findall(r"^\s*-\s+\[[xX]\]\s+", text, re.M))
    return info


def feature_spec_insights(feat: dict[str, Any]) -> list[dict[str, Any]]:
    return [inspect_spec_slice(str(p)) for p in (feat.get("specs") or []) if p]


def _speckit_rules_block() -> list[str]:
    if not _speckit_enabled():
        return [
            "## Implementation style",
            "This project has **Spec Kit disabled** (`speckit: false` or no `specs/`).",
            "Work surgically: update the card + minimal code; before claiming done run "
            "`.pulse/bin/pulse mismatch detect` and `generate`.",
            *_quality_raise_block(),
        ]
    return [
        "## Spec Kit (optional brownfield) — use only when appropriate",
        "Pros: slice with spec/plan/tasks keeps the agent on acceptance; loop "
        f"{SPECKIT_LOOP}; cite real product docs + modules.",
        "Cons / skip full Spec Kit for: small fixes, registry sync, narrow detect findings, "
        "single-file polish — stay surgical; do not open a new specify.",
        "Always: product docs are SoT; `specs/NNN-*` is only a feature slice — "
        "do not invent behavior outside the locked scope. BOARD `%` ≠ Spec Kit checklist.",
        "Skills: `speckit-specify`, `speckit-plan`, `speckit-tasks`, `speckit-implement`, "
        "`speckit-analyze`, `speckit-converge`, `speckit-clarify` (read SKILL.md when running).",
        "Disable Spec Kit prompts: set `speckit: false` in `_meta.yaml`.",
        *_quality_raise_block(),
    ]


def _quality_raise_block() -> list[str]:
    return [
        "",
        "## Quality raise",
        "Conflict / smell / oversized multi-duty file / SOLID break / security → "
        "log a tech-debt card (skill `quality-raise`); **get approval before** large refactors. "
        "No drive-by rewrites. Rule: `.cursor/rules/quality-raise.mdc`.",
    ]


def _list_preview(items: Any, *, limit: int = 5) -> list[Any]:
    if not isinstance(items, list):
        return []
    return items[:limit]


def _card_path(feature_id: str) -> str:
    return f".pulse/features/{feature_id}.yaml"


def _speckit_feature_block(feat: dict[str, Any]) -> list[str]:
    if not _speckit_enabled():
        return []
    lines = ["", "### Spec Kit linkage for this feature"]
    specs = feature_spec_insights(feat)
    if not specs:
        lines.append(
            "- `specs: []` — no slice attached. Large work / many remaining → "
            "`speckit-specify` (cite product docs / requirements); small work → code directly."
        )
        return lines
    for sp in specs:
        if not sp["exists"]:
            lines.append(f"- `{sp['path']}` — listed in registry but directory is missing")
            continue
        lines.append(
            f"- `{sp['path']}`: spec={'yes' if sp['has_spec'] else 'no'} "
            f"plan={'yes' if sp['has_plan'] else 'no'} "
            f"tasks={'yes' if sp['has_tasks'] else 'no'} "
            f"open_tasks={sp['open_tasks']} done_tasks={sp['done_tasks']}"
        )
        if sp["open_tasks"] > 0:
            lines.append(
                f"  → Recommend skill `speckit-implement` "
                f"(read `{sp['path']}/tasks.md` + plan.md)."
            )
        elif sp["has_tasks"] and sp["open_tasks"] == 0:
            lines.append(
                "  → tasks are all checked — if BOARD still has remaining, sync the registry "
                "or `speckit-converge` / a new slice for the leftover gap."
            )
        elif sp["has_spec"] and not sp["has_tasks"]:
            lines.append("  → Run plan → tasks before implement.")
    return lines


def _speckit_next_playbook(item: dict[str, Any], feat: dict[str, Any] | None) -> list[str]:
    if not _speckit_enabled():
        return [
            "",
            "## How to proceed",
            "1. Do the minimum work implied by remaining/mocks on the card.",
            "2. Update `.pulse/features/`, then `.pulse/bin/pulse generate`.",
            "3. Before claiming done: `.pulse/bin/pulse mismatch detect`.",
            *_quality_raise_block(),
        ]
    lines = ["", "## How to proceed (Spec Kit-aware)"]
    specs = feature_spec_insights(feat) if feat else []
    action = str(item.get("action") or "")

    open_slice = next(
        (sp for sp in specs if sp.get("exists") and int(sp.get("open_tasks") or 0) > 0),
        None,
    )
    incomplete_loop = next(
        (
            sp
            for sp in specs
            if sp.get("exists") and sp.get("has_spec") and not sp.get("has_tasks")
        ),
        None,
    )
    closed_slice_with_remaining = next(
        (
            sp
            for sp in specs
            if sp.get("exists")
            and sp.get("has_tasks")
            and int(sp.get("open_tasks") or 0) == 0
            and (feat.get("remaining") if feat else item.get("remaining"))
        ),
        None,
    )

    if "detect finding" in action.lower() or "Investigate detect" in action:
        lines.extend(
            [
                "1. Narrow Toolkit A work — **do not** open a new Spec Kit slice.",
                "2. Minimal fix, update `.pulse/features/`, `generate`, then "
                "`.pulse/bin/pulse mismatch detect`.",
            ]
        )
    elif feat and str(feat.get("next_chunks") or "").strip().lower() in {
        "remaining",
        "per_remaining",
        "chunks",
    }:
        lines.extend(
            [
                "1. Feature uses `next_chunks: remaining` — **one card / one chunk**; stay surgical "
                "unless the chunk title calls for Spec Kit / a large missing card.",
                "2. Read the card playbook in `.pulse/rich-cards-review.md` (match the Action name).",
                "3. Follow product docs / the feature requirements map; use locked SoT numbers (do not invent).",
                "4. Do not edit other cards in this prompt; dual-card / shell smells → raise quality-raise "
                "if a large file split is needed.",
                "5. After the chunk: move the bullet to `done`, update percent, `.pulse/bin/pulse generate`.",
            ]
        )
    elif open_slice:
        lines.extend(
            [
                f"1. Use skill **speckit-implement** with FEATURE_DIR=`{open_slice['path']}`.",
                f"2. Follow `tasks.md` ({open_slice['open_tasks']} open tasks); read plan.md / contracts.",
                "3. Do not invent requirements outside `docs/`; UI numbers from locked SoT only.",
                "4. After tasks: tick tasks.md; sync `.pulse/features/`; `generate`.",
                "5. Before claiming done: detect; optionally `speckit-converge` if gaps vs spec remain.",
                "6. Mid-task conflict/smell/architecture issues → raise `quality-raise`, wait for approval.",
            ]
        )
    elif incomplete_loop:
        lines.extend(
            [
                f"1. Slice `{incomplete_loop['path']}` is missing plan/tasks — "
                "**speckit-plan** then **speckit-tasks** (cite docs); do not code first.",
                "2. Then **speckit-implement** from tasks.md.",
            ]
        )
    elif closed_slice_with_remaining:
        lines.extend(
            [
                f"1. Slice `{closed_slice_with_remaining['path']}` has all tasks checked but BOARD still has remaining "
                f"(e.g. `{action}`).",
                "2. Pick one: (a) **speckit-converge** to append missing tasks to the old slice; "
                "(b) **speckit-specify** a new slice if scope splits; "
                "(c) surgical fix if 1–2 files and FR already exists in `docs/`.",
                "3. Do not claim BOARD done while remaining/mocks remain; sync `.pulse/features/` after choosing.",
            ]
        )
    elif not specs and "Start Spec Kit" in action:
        lines.extend(
            [
                "1. **speckit-specify** for the remaining gap (brownfield: cite product docs / requirements, "
                "real modules under code_roots — no greenfield rewrite).",
                f"2. Continue: {SPECKIT_LOOP}.",
                "3. Attach the slice path to `specs:` on the feature in `.pulse/features/`.",
                "4. Implement only via tasks.md after tasks exist.",
            ]
        )
    else:
        lines.extend(
            [
                "1. Scope is small / remaining is clear — **surgical implement** (skip a new specify).",
                "2. Still read `docs/` listed under `docs=` before editing.",
                "3. If scope grows (>1–2 files / many new acceptance criteria) → propose a Spec Kit slice.",
                "4. When done: `.pulse/features/` + `generate`; detect before claiming done.",
            ]
        )
    return lines

def health_summary(data: dict[str, Any], mismatch: dict[str, Any] | None = None) -> dict[str, Any]:
    mismatch = mismatch if mismatch is not None else load_mismatch_summary()
    from pulse_lib.docs_drift import load_drift_summary

    drift = load_drift_summary()
    counts = {"done": 0, "partial": 0, "todo": 0, "blocked": 0}
    rem_total = 0
    mock_total = 0
    for feat in data.get("features") or []:
        if isinstance(feat, dict):
            st = feat.get("status")
            if st in counts:
                counts[st] += 1
            rem_total += len([x for x in (feat.get("remaining") or []) if str(x).strip()])
            mock_total += len([x for x in (feat.get("mocks") or []) if str(x).strip()])
    totals = drift.get("totals") or {}
    return {
        "updated": data.get("updated"),
        "counts": counts,
        "open_work": {
            "remaining_bullets": rem_total,
            "mocks": mock_total,
        },
        "detect": {
            "exists": mismatch.get("exists"),
            "critical": mismatch.get("critical"),
            "warning": mismatch.get("warning"),
            "info": mismatch.get("info"),
        },
        "drift": {
            "exists": drift.get("exists"),
            "critical": drift.get("critical"),
            "warning": drift.get("warning"),
            "info": drift.get("info"),
            "docs_ids_not_on_board": totals.get("docs_ids_not_on_board"),
            "spec_debt_items": totals.get("spec_debt_items"),
            "tag_gaps": totals.get("tag_gaps"),
            "orphan_code_tags": totals.get("orphan_code_tags"),
            "evidence_untagged_paths": totals.get("evidence_untagged_paths"),
            "generated_at": drift.get("generated_at"),
        },
    }

