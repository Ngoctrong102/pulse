"""Docs / Spec Kit ↔ registry drift — visualize stale board & leftover work after doc/spec changes."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from pulse_lib import Finding, build_id_catalog, load_registry
from pulse_lib.paths import DRIFT_JSON_PATH, DRIFT_MD_PATH, REPO_ROOT
from pulse_lib.next_actions import feature_spec_insights
from pulse_lib.tag_audit import (
    audit_evidence_paths_missing_tags,
    audit_orphan_code_tags,
    project_label,
    scan_code_tags,
    tag_marker,
)


UF_NUM_RE = re.compile(r"^(\d+\.\d+)$")
TECH_DOC_RE = re.compile(r"^(\d+(?:\.\d+)*)$")
ID_TOKEN_RE = re.compile(r"\b((?:FR|NFR|TECH|UF|DEC)[-A-Z0-9.]+)\b")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_doc_ref(kind: str, value: str) -> list[str]:
    """Map card docs: entries (.pulse/features/) to catalog-style IDs where possible."""
    v = value.strip()
    if not v:
        return []
    if ID_TOKEN_RE.fullmatch(v):
        return [v]
    if kind == "uf" and UF_NUM_RE.match(v):
        return [f"UF-{v}"]
    if kind == "decisions" and v.isdigit():
        return [f"DEC-{int(v):03d}"]
    if kind == "decisions" and v.upper().startswith("DEC"):
        return [v if v.startswith("DEC-") else f"DEC-{v.split('-', 1)[-1]}"]
    return []


def _ids_covered_by_feature(feat: dict[str, Any], catalog: dict[str, str]) -> set[str]:
    covered: set[str] = set()
    docs = feat.get("docs") or {}
    if not isinstance(docs, dict):
        return covered
    for kind, values in docs.items():
        if not isinstance(values, list):
            continue
        for raw in values:
            if not isinstance(raw, str):
                continue
            for nid in _normalize_doc_ref(str(kind), raw):
                covered.add(nid)
            if str(kind) == "tech" and TECH_DOC_RE.match(raw.strip()):
                stem = raw.strip()
                for cid, path in catalog.items():
                    norm = f"/{path}"
                    if f"/{stem}-" in norm or path.endswith(f"/{stem}.md") or f"/{stem}." in norm:
                        covered.add(cid)
            if str(kind) == "uf" and UF_NUM_RE.match(raw.strip()):
                num = raw.strip()
                for cid, path in catalog.items():
                    if f"/{num}-" in f"/{path}" or f"user-flows/{num}-" in path:
                        covered.add(cid)
    return covered


def collect_feature_refs(data: dict[str, Any], catalog: dict[str, str]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for feat in data.get("features") or []:
        if not isinstance(feat, dict):
            continue
        fid = str(feat.get("id") or "")
        if not fid:
            continue
        out[fid] = _ids_covered_by_feature(feat, catalog)
    return out


def analyze_docs_drift(data: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = data or load_registry()
    catalog, catalog_warnings = build_id_catalog()
    feature_covers = collect_feature_refs(registry, catalog)
    all_covered: set[str] = set()
    for s in feature_covers.values():
        all_covered |= s

    findings: list[Finding] = []
    for w in catalog_warnings:
        if "duplicate id" in w:
            findings.append(Finding("warning", "duplicate_doc_id", w))

    untracked: list[dict[str, str]] = []
    for req_id, path in sorted(catalog.items()):
        if req_id in all_covered:
            continue
        untracked.append({"id": req_id, "doc": path})
        findings.append(
            Finding(
                "warning" if req_id.startswith(("FR-", "UF-", "NFR-", "DEC-")) else "info",
                "docs_id_not_on_board",
                f"{req_id} exists in docs but no card docs: map (.pulse/features/) covers it",
                req_id=req_id,
                evidence=[path],
            )
        )

    for feat in registry.get("features") or []:
        if not isinstance(feat, dict):
            continue
        fid = str(feat.get("id") or "")
        docs = feat.get("docs") or {}
        if not isinstance(docs, dict):
            continue
        for kind, values in docs.items():
            if not isinstance(values, list):
                continue
            for raw in values:
                if not isinstance(raw, str):
                    continue
                for nid in _normalize_doc_ref(str(kind), raw):
                    if nid not in catalog and ID_TOKEN_RE.fullmatch(nid):
                        findings.append(
                            Finding(
                                "warning",
                                "board_refs_missing_doc_id",
                                f"{fid} docs map references {nid} but id-index has no such ID",
                                feature_id=fid,
                                req_id=nid,
                            )
                        )

    spec_debt: list[dict[str, Any]] = []
    open_work: list[dict[str, Any]] = []
    for feat in registry.get("features") or []:
        if not isinstance(feat, dict):
            continue
        fid = str(feat.get("id") or "")
        status = feat.get("status")
        remaining = [str(x) for x in (feat.get("remaining") or []) if str(x).strip()]
        mocks = [str(x) for x in (feat.get("mocks") or []) if str(x).strip()]
        insights = feature_spec_insights(feat)
        rem_n, mock_n = len(remaining), len(mocks)
        if status != "done" or rem_n or mock_n:
            open_work.append(
                {
                    "id": fid,
                    "name": feat.get("name"),
                    "status": status,
                    "percent": feat.get("percent"),
                    "remaining_count": rem_n,
                    "mocks_count": mock_n,
                    "remaining": remaining,
                    "mocks": mocks,
                    "specs": insights,
                }
            )
        for sp in insights:
            open_tasks = int(sp.get("open_tasks") or 0)
            done_tasks = int(sp.get("done_tasks") or 0)
            if sp.get("exists") and sp.get("has_tasks") and open_tasks == 0 and rem_n:
                findings.append(
                    Finding(
                        "warning",
                        "spec_done_board_remaining",
                        f"{fid}: Spec Kit tasks all checked ({done_tasks}) but board still has "
                        f"{rem_n} remaining — docs/spec scope grew or cleanup not synced",
                        feature_id=fid,
                        evidence=[sp["path"], *remaining[:5]],
                    )
                )
                spec_debt.append(
                    {
                        "id": fid,
                        "kind": "spec_done_board_remaining",
                        "spec": sp["path"],
                        "remaining_count": rem_n,
                        "mocks_count": mock_n,
                        "remaining": remaining,
                    }
                )
            if sp.get("exists") and open_tasks > 0 and status == "done":
                findings.append(
                    Finding(
                        "critical",
                        "board_done_spec_open",
                        f"{fid}: status done but {open_tasks} open tasks in {sp['path']}",
                        feature_id=fid,
                        evidence=[sp["path"]],
                    )
                )
                spec_debt.append(
                    {
                        "id": fid,
                        "kind": "board_done_spec_open",
                        "spec": sp["path"],
                        "open_tasks": open_tasks,
                    }
                )
            if sp.get("exists") and open_tasks == 0 and mock_n and status != "done":
                findings.append(
                    Finding(
                        "info",
                        "spec_done_mocks_remain",
                        f"{fid}: tasks done but {mock_n} mocks still listed — cleanup incomplete",
                        feature_id=fid,
                        evidence=mocks[:5],
                    )
                )

    for feat in registry.get("features") or []:
        if not isinstance(feat, dict):
            continue
        fid = str(feat.get("id") or "")
        status = feat.get("status")
        evidence = feat.get("evidence") or {}
        paths_any = evidence.get("paths_any") if isinstance(evidence, dict) else []
        if not isinstance(paths_any, list):
            continue
        missing = [p for p in paths_any if isinstance(p, str) and not (REPO_ROOT / p).exists()]
        if missing and status in {"partial", "done"}:
            findings.append(
                Finding(
                    "warning",
                    "evidence_path_missing",
                    f"{fid}: evidence.paths_any missing on disk (stale after refactor?)",
                    feature_id=fid,
                    evidence=missing,
                )
            )

    tag_hits = scan_code_tags()
    tag_gaps: list[dict[str, Any]] = []
    for feat in registry.get("features") or []:
        if not isinstance(feat, dict):
            continue
        if feat.get("status") == "todo":
            continue
        fid = str(feat.get("id") or "")
        covered = feature_covers.get(fid) or set()
        for req_id in sorted(x for x in covered if x.startswith(("FR-", "NFR-"))):
            paths = tag_hits.get(req_id) or []
            if not paths:
                tag_gaps.append({"feature_id": fid, "req_id": req_id, "tag_hits": 0})
                findings.append(
                    Finding(
                        "info",
                        "req_id_without_tag",
                        f"{req_id} covered by {fid} on board but no {tag_marker()} tag in code roots "
                        "(unimplemented, unlabeled, or docs-only)",
                        feature_id=fid,
                        req_id=req_id,
                    )
                )

    orphan_findings = audit_orphan_code_tags(catalog)
    findings.extend(orphan_findings)

    evidence_tag_findings, evidence_untagged = audit_evidence_paths_missing_tags(
        list(registry.get("features") or [])
    )
    findings.extend(evidence_tag_findings)

    counts = {
        "critical": sum(1 for f in findings if f.severity == "critical"),
        "warning": sum(1 for f in findings if f.severity == "warning"),
        "info": sum(1 for f in findings if f.severity == "info"),
    }
    totals = {
        "catalog_ids": len(catalog),
        "board_covered_ids": len(all_covered),
        "docs_ids_not_on_board": len(untracked),
        "open_features": len([x for x in open_work if x.get("status") != "done"]),
        "total_remaining_bullets": sum(int(x.get("remaining_count") or 0) for x in open_work),
        "total_mocks": sum(int(x.get("mocks_count") or 0) for x in open_work),
        "spec_debt_items": len(spec_debt),
        "tag_gaps": len(tag_gaps),
        "orphan_code_tags": len(orphan_findings),
        "evidence_untagged_paths": len(
            [r for r in evidence_untagged if r.get("kind") == "no_tag"]
        ),
        "evidence_tag_mismatches": len(
            [r for r in evidence_untagged if r.get("kind") == "mismatch"]
        ),
    }

    return {
        "generated_at": _utc_now(),
        "exists": True,
        "counts": counts,
        "totals": totals,
        "untracked_ids": untracked[:80],
        "spec_debt": spec_debt,
        "open_work": open_work,
        "tag_gaps": tag_gaps[:60],
        "orphan_code_tags": [f.as_dict() for f in orphan_findings[:40]],
        "evidence_untagged": evidence_untagged[:60],
        "findings": [f.as_dict() for f in findings[:80]],
        "truncated": len(findings) > 80,
        "findings_total": len(findings),
    }


def render_drift_md(report: dict[str, Any]) -> str:
    t = report.get("totals") or {}
    c = report.get("counts") or {}
    lines = [
        "# Docs / Spec ↔ Board drift",
        "",
        f"_Generated {report.get('generated_at')} — run `.pulse/bin/pulse drift` or `generate`._",
        "",
        "## Snapshot",
        "",
        f"- Catalog IDs: **{t.get('catalog_ids', 0)}** · covered by board docs maps: **{t.get('board_covered_ids', 0)}**",
        f"- Docs IDs **not** on any feature: **{t.get('docs_ids_not_on_board', 0)}**",
        f"- Open remaining bullets: **{t.get('total_remaining_bullets', 0)}** · mocks: **{t.get('total_mocks', 0)}**",
        f"- Spec↔board debt items: **{t.get('spec_debt_items', 0)}** · FR/NFR without {tag_marker()} tag: **{t.get('tag_gaps', 0)}**",
        f"- Orphan code tags (ID deleted/missing in docs): **{t.get('orphan_code_tags', 0)}**",
        f"- Evidence paths with **no** {tag_marker()} tag: **{t.get('evidence_untagged_paths', 0)}** · tag≠FR map: **{t.get('evidence_tag_mismatches', 0)}**",
        f"- Findings: {c.get('critical', 0)} critical · {c.get('warning', 0)} warning · {c.get('info', 0)} info",
        "",
        "## Open work (code / cleanup still on board)",
        "",
        "| Feature | Status | % | Rem | Mocks |",
        "|---|---|---:|---:|---:|",
    ]
    for row in report.get("open_work") or []:
        if row.get("status") == "done" and not row.get("remaining_count") and not row.get("mocks_count"):
            continue
        lines.append(
            f"| `{row.get('id')}` | {row.get('status')} | {row.get('percent')} | "
            f"{row.get('remaining_count')} | {row.get('mocks_count')} |"
        )
    lines.extend(["", "## Spec Kit vs board (leftover after doc/spec change)", ""])
    debt = report.get("spec_debt") or []
    if not debt:
        lines.append("_None — no closed-slice / open-board mismatches detected._")
    else:
        lines.append("| Feature | Kind | Detail |")
        lines.append("|---|---|---|")
        for d in debt:
            detail = str(d.get("spec") or "")
            if d.get("remaining"):
                detail += " · rem: " + "; ".join(d["remaining"][:3])
            if d.get("open_tasks"):
                detail += f" · open_tasks={d['open_tasks']}"
            lines.append(f"| `{d.get('id')}` | {d.get('kind')} | {detail} |")

    lines.extend(["", "## Docs IDs not mapped on board (sample)", ""])
    untracked = report.get("untracked_ids") or []
    if not untracked:
        lines.append("_All catalog IDs appear on at least one feature docs map._")
    else:
        lines.append("| ID | Doc |")
        lines.append("|---|---|")
        for u in untracked[:40]:
            lines.append(f"| `{u.get('id')}` | {u.get('doc')} |")
        if len(untracked) > 40:
            lines.append(f"| … | +{len(untracked) - 40} more |")

    lines.extend(["", f"## Evidence paths missing / mismatched {tag_marker()} tags", ""])
    ev = report.get("evidence_untagged") or []
    if not ev:
        lines.append("_None — code_roots evidence.paths_any have sparse tags (or no code evidence)._")
    else:
        lines.append("| Feature | Path | Kind |")
        lines.append("|---|---|---|")
        for row in ev[:30]:
            lines.append(
                f"| `{row.get('feature_id')}` | `{row.get('path')}` | {row.get('kind')} |"
            )

    lines.extend(["", "## Orphan code tags (sample)", ""])
    orphans = report.get("orphan_code_tags") or []
    if not orphans:
        lines.append(f"_None — every {tag_marker()} ID resolves in the docs catalog._")
    else:
        lines.append("| ID | Message |")
        lines.append("|---|---|")
        for o in orphans[:20]:
            lines.append(f"| `{o.get('req_id')}` | {o.get('message')} |")

    lines.extend(
        [
            "",
            "## What to do",
            "",
            "1. After editing `docs/` or `specs/`, run `.pulse/bin/pulse drift`.",
            "2. Sync `.pulse/features/` (new row / remaining / mocks / docs map) then `generate`.",
            "3. Leftover code after a doc rewrite: `.pulse/bin/pulse drift --prompt` "
            "(or board **Docs/spec drift**) — raise cleanup via `quality-raise` before big deletes.",
            "4. Tag gaps / evidence untagged / orphans: `tag --feature`, `tag --untagged-cleanup`, "
            "or `.pulse/bin/pulse mismatch detect`.",
            "",
        ]
    )
    return "\n".join(lines)


def write_drift_report(report: dict[str, Any] | None = None) -> dict[str, Any]:
    report = report or analyze_docs_drift()
    DRIFT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    DRIFT_JSON_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    DRIFT_MD_PATH.write_text(render_drift_md(report), encoding="utf-8")
    return report


def load_drift_summary() -> dict[str, Any]:
    if not DRIFT_JSON_PATH.is_file():
        return {"exists": False, "critical": 0, "warning": 0, "info": 0, "totals": {}}
    try:
        data = json.loads(DRIFT_JSON_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"exists": False, "critical": 0, "warning": 0, "info": 0, "totals": {}}
    counts = data.get("counts") or {}
    return {
        "exists": True,
        "critical": int(counts.get("critical") or 0),
        "warning": int(counts.get("warning") or 0),
        "info": int(counts.get("info") or 0),
        "totals": data.get("totals") or {},
        "generated_at": data.get("generated_at"),
    }


def build_docs_drift_prompt(
    data: dict[str, Any] | None = None, report: dict[str, Any] | None = None
) -> str:
    registry = data or load_registry()
    report = report or analyze_docs_drift(registry)
    t = report.get("totals") or {}
    lines = [
        f"Sync the board after docs/specs changes on {project_label()}.",
        "",
        "Read: `.pulse/DRIFT.md` (summary) + `.pulse/features/<id>.yaml` when editing a card. "
        "Do **not** read the full `docs-drift-report.json` unless debugging.",
        "",
        "## Snapshot",
        f"- remaining={t.get('total_remaining_bullets')} mocks={t.get('total_mocks')} "
        f"docs_unmapped={t.get('docs_ids_not_on_board')} spec_debt={t.get('spec_debt_items')}",
        f"- tag_gaps={t.get('tag_gaps')} orphans={t.get('orphan_code_tags')} "
        f"evidence_untagged={t.get('evidence_untagged_paths')} counts={report.get('counts')}",
        "",
        "## Work",
        "1. Sync remaining/mocks on cards to match docs/code.",
        "2. Important docs IDs not on the board → map `docs:` or `pulse new`.",
        "3. Do not mark `done` while mocks/remaining remain. No mismatch-heal unless asked.",
        f"4. Sparse `{tag_marker()}` tags for evidence / orphans per DRIFT.md.",
        "5. `.pulse/bin/pulse generate` then summarize open work.",
        "",
        "## Spec debt (top)",
    ]
    for d in (report.get("spec_debt") or [])[:8]:
        lines.append(
            f"- `{d.get('id')}` [{d.get('kind')}] rem={d.get('remaining_count')}"
        )
    lines.extend(["", "## Open work (top)"])
    for row in sorted(
        report.get("open_work") or [],
        key=lambda r: (-int(r.get("remaining_count") or 0), -int(r.get("mocks_count") or 0)),
    )[:8]:
        lines.append(
            f"- `{row.get('id')}` [{row.get('status')}/{row.get('percent')}%] "
            f"rem={row.get('remaining_count')} mocks={row.get('mocks_count')}"
        )
    return "\n".join(lines)
