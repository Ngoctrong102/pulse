#!/usr/bin/env python3
"""Shared load/validate/generate helpers for pulse status toolkits.

Source of truth is the per-card directory ``.pulse/features/`` (Jira-style,
one file per card) plus ``_meta.yaml``. Each card has a ``type``:

- ``feature`` — a product feature row (default); assembled into ``data["features"]``.
- ``bug`` / ``tech-debt`` — backlog items; assembled into ``data["backlog"]``.

Keeping backlog cards out of ``data["features"]`` means every existing consumer
that iterates ``data["features"]`` keeps its old behaviour untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from pulse_lib.paths import (  # noqa: E402
    BOARD_PATH,
    DEFAULT_REGISTRY,
    FEATURES_DIR,
    META_PATH,
    PHASES_PATH,
    PROJECT_ROOT,
    PULSE_HOME,
    REPO_ROOT,
    TECHDEBT_PATH,
    ID_INDEX_PATH,
)



STATUSES = frozenset({"done", "partial", "todo", "blocked"})
TYPES = frozenset({"feature", "bug", "tech-debt"})
BACKLOG_TYPES = frozenset({"bug", "tech-debt"})
SEVERITIES = frozenset({"low", "medium", "high", "blocker"})
STATUS_BEGIN = "<!-- STATUS:BEGIN -->"
STATUS_END = "<!-- STATUS:END -->"

STATUS_EMOJI = {
    "done": "✅",
    "partial": "🟡",
    "todo": "⬜",
    "blocked": "🚫",
}

# Backlog status reads more naturally with issue-tracker words.
BACKLOG_STATUS_LABEL = {
    "todo": "deferred",
    "partial": "in-progress",
    "done": "done",
    "blocked": "blocked",
}

# Preferred key order when writing a card file, for human readability.
CARD_KEY_ORDER = [
    "id", "type", "name", "phase", "status", "percent", "priority", "roi", "mvp",
    "severity", "where", "why", "proposed_fix", "refs", "blocks", "next_chunks",
    "docs", "specs", "mocks", "done", "remaining", "evidence",
]
# Keys that belong on cards lists, not in _meta.yaml.
_META_EXCLUDE = frozenset({"features", "backlog"})
# Preferred order when writing _meta.yaml (unknown keys appended after).
META_KEY_ORDER = (
    "version",
    "project",
    "tag_prefix",
    "code_roots",
    "speckit",
    "updated",
    "focus_id",
    "plugins",
)
# Back-compat alias: previously the only keys written to _meta.yaml.
META_KEYS = META_KEY_ORDER


class StatusError(Exception):
    pass


def _meta_from_registry(data: dict[str, Any]) -> dict[str, Any]:
    """Extract _meta.yaml payload — preserve all non-card keys."""
    meta: dict[str, Any] = {}
    for k in META_KEY_ORDER:
        if k not in data:
            continue
        if k == "focus_id" and (data[k] is None or str(data[k]).strip() == ""):
            continue
        meta[k] = data[k]
    for k, v in data.items():
        if k in _META_EXCLUDE or k in meta:
            continue
        if k == "focus_id" and (v is None or str(v).strip() == ""):
            continue
        meta[k] = v
    return meta


# --------------------------------------------------------------------------- #
# Load / save (per-card directory, with single-file legacy fallback)
# --------------------------------------------------------------------------- #
def _card_type(card: dict[str, Any]) -> str:
    return str(card.get("type") or "feature")


def _sort_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        cards,
        key=lambda c: (c.get("phase") is None, c.get("phase") or 0, c.get("id") or ""),
    )


def _load_dir(directory: Path) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    meta_file = directory / "_meta.yaml"
    if meta_file.is_file():
        loaded = yaml.safe_load(meta_file.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            meta = loaded
    features: list[dict[str, Any]] = []
    backlog: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.yaml")):
        if path.name == "_meta.yaml":
            continue
        card = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(card, dict):
            raise StatusError(f"Card is not a mapping: {path}")
        card.setdefault("type", "feature")
        if _card_type(card) in BACKLOG_TYPES:
            backlog.append(card)
        else:
            features.append(card)
    data: dict[str, Any] = dict(meta)
    data["features"] = _sort_cards(features)
    data["backlog"] = _sort_cards(backlog)
    return data


def _is_dir_target(path: Path | None) -> bool:
    if path is None:
        return True
    if path.is_dir():
        return True
    if path.suffix in (".yaml", ".yml"):
        return False
    return True


def load_registry(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_REGISTRY
    if _is_dir_target(target):
        if not target.is_dir():
            raise StatusError(f"Registry directory not found: {target}")
        return _load_dir(target)
    # Legacy single-file registry (used by --path / heal tests).
    if not target.is_file():
        raise StatusError(f"Registry not found: {target}")
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise StatusError("Registry root must be a mapping")
    data.setdefault("features", data.get("features") or [])
    return data


def _dump_card(card: dict[str, Any]) -> str:
    ordered: dict[str, Any] = {k: card[k] for k in CARD_KEY_ORDER if k in card}
    for k, v in card.items():
        if k not in ordered:
            ordered[k] = v
    return yaml.safe_dump(
        ordered, allow_unicode=True, sort_keys=False, default_flow_style=False
    )


def _save_dir(data: dict[str, Any], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    meta = _meta_from_registry(data)
    (directory / "_meta.yaml").write_text(
        yaml.safe_dump(meta, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    existing = {p.name for p in directory.glob("*.yaml") if p.name != "_meta.yaml"}
    written: set[str] = set()
    for card in list(data.get("features") or []) + list(data.get("backlog") or []):
        cid = card.get("id")
        if not cid:
            continue
        name = f"{cid}.yaml"
        (directory / name).write_text(_dump_card(card), encoding="utf-8")
        written.add(name)
    for stale in existing - written:
        (directory / stale).unlink()


def save_registry(data: dict[str, Any], path: Path | None = None) -> None:
    target = path or DEFAULT_REGISTRY
    if _is_dir_target(target):
        _save_dir(data, target)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(
        data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
    target.write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------- #
# Validation (type-aware)
# --------------------------------------------------------------------------- #
def _validate_card(
    card: Any, prefix: str, seen: set[str]
) -> list[str]:
    errors: list[str] = []
    if not isinstance(card, dict):
        return [f"{prefix}: must be a mapping"]
    fid = card.get("id")
    if not isinstance(fid, str) or not fid.strip():
        errors.append(f"{prefix}: missing id")
        fid = None
    elif fid in seen:
        errors.append(f"{prefix}: duplicate id {fid}")
    else:
        seen.add(fid)
    ctype = _card_type(card)
    if ctype not in TYPES:
        errors.append(f"{prefix} ({fid}): invalid type {ctype!r}")
    status = card.get("status")
    if status not in STATUSES:
        errors.append(f"{prefix} ({fid}): invalid status {status!r}")

    is_feature = ctype == "feature"
    if is_feature:
        percent = card.get("percent")
        if not isinstance(percent, int) or percent < 0 or percent > 100:
            errors.append(f"{prefix} ({fid}): percent must be int 0–100")
        elif status == "done" and percent < 100:
            errors.append(f"{prefix} ({fid}): status done requires percent 100")
        elif status == "todo" and percent > 0:
            errors.append(f"{prefix} ({fid}): status todo should have percent 0")
        for key in ("priority", "roi"):
            if not isinstance(card.get(key), int):
                errors.append(f"{prefix} ({fid}): {key} must be int")
        if "mvp" in card and not isinstance(card.get("mvp"), bool):
            errors.append(f"{prefix} ({fid}): mvp must be bool")
        mocks = card.get("mocks") or []
        if status == "done" and isinstance(mocks, list) and any(str(m).strip() for m in mocks):
            errors.append(
                f"{prefix} ({fid}): status done forbids non-empty mocks "
                "(keep partial until mocks are closed or removed)"
            )
        remaining = card.get("remaining") or []
        if status == "done" and isinstance(remaining, list) and any(str(r).strip() for r in remaining):
            errors.append(f"{prefix} ({fid}): status done forbids non-empty remaining")
    else:
        if not isinstance(card.get("priority"), int):
            errors.append(f"{prefix} ({fid}): priority must be int")
        sev = card.get("severity")
        if not isinstance(sev, str) or not sev.strip():
            errors.append(f"{prefix} ({fid}): {ctype} requires severity")
        elif sev not in SEVERITIES:
            errors.append(f"{prefix} ({fid}): severity must be one of {sorted(SEVERITIES)}")
        percent = card.get("percent")
        if percent is not None and (not isinstance(percent, int) or percent < 0 or percent > 100):
            errors.append(f"{prefix} ({fid}): percent must be int 0–100 when set")

    evidence = card.get("evidence")
    if evidence is not None and not isinstance(evidence, dict):
        errors.append(f"{prefix} ({fid}): evidence must be mapping")
    blocks = card.get("blocks")
    if blocks is not None:
        if not isinstance(blocks, list):
            errors.append(f"{prefix} ({fid}): blocks must be a list of card ids")
        else:
            for j, bid in enumerate(blocks):
                if not isinstance(bid, str) or not bid.strip():
                    errors.append(f"{prefix} ({fid}): blocks[{j}] must be non-empty string")
    return errors


def validate_registry(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("version") is None:
        errors.append("missing version")
    features = data.get("features")
    if not isinstance(features, list) or not features:
        errors.append("features must be a non-empty list")
        return errors
    seen: set[str] = set()
    for i, feat in enumerate(features):
        errors.extend(_validate_card(feat, f"features[{i}]", seen))
    backlog = data.get("backlog") or []
    if not isinstance(backlog, list):
        errors.append("backlog must be a list")
        backlog = []
    for i, item in enumerate(backlog):
        errors.extend(_validate_card(item, f"backlog[{i}]", seen))
    # Cross-card: blocks + focus_id must reference known ids.
    for bucket_name, cards in (("features", features), ("backlog", backlog)):
        for i, card in enumerate(cards):
            if not isinstance(card, dict):
                continue
            blocks = card.get("blocks")
            if not isinstance(blocks, list):
                continue
            fid = card.get("id")
            for bid in blocks:
                if isinstance(bid, str) and bid.strip() and bid not in seen:
                    errors.append(
                        f"{bucket_name}[{i}] ({fid}): blocks references unknown id {bid!r}"
                    )
    focus_id = data.get("focus_id")
    if focus_id is not None and str(focus_id).strip() != "":
        fid = str(focus_id).strip()
        if fid not in seen:
            errors.append(f"focus_id references unknown id {fid!r}")
        # Done focus is allowed on disk; runtime treats as empty (Health hint only).
    return errors


# --------------------------------------------------------------------------- #
# Query helpers
# --------------------------------------------------------------------------- #
def filter_features(
    features: list[dict[str, Any]],
    *,
    status: str | None = None,
    mvp: bool | None = None,
) -> list[dict[str, Any]]:
    out = features
    if status:
        out = [f for f in out if f.get("status") == status]
    if mvp is True:
        out = [f for f in out if f.get("mvp") is True]
    return out


def sort_features(
    features: list[dict[str, Any]],
    sort_key: str = "priority",
) -> list[dict[str, Any]]:
    reverse = sort_key in {"roi", "percent"}
    if sort_key == "phase":
        return sorted(features, key=lambda f: (f.get("phase") is None, f.get("phase") or 0, f.get("id") or ""))
    if sort_key == "name":
        return sorted(features, key=lambda f: (f.get("name") or "").lower())
    return sorted(
        features,
        key=lambda f: (f.get(sort_key) is None, f.get(sort_key) if f.get(sort_key) is not None else 0, f.get("id") or ""),
        reverse=reverse,
    )


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def render_board(data: dict[str, Any]) -> str:
    features = sort_features(list(data.get("features") or []), "priority")
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
    features = sort_features(list(data.get("features") or []), "phase")
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
    cards = sorted(cards, key=lambda c: c.get("id") or "")
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
            "",
        ]
    )
    if not cards:
        lines.append("_No tech-debt cards yet._")
        return "\n".join(lines) + "\n"
    for c in cards:
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
    return "\n".join(lines).rstrip() + "\n"


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
    registry = data or load_registry()
    errors = validate_registry(registry)
    if errors:
        raise StatusError("validate failed:\n- " + "\n- ".join(errors))
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


@dataclass
class Finding:
    severity: str
    code: str
    message: str
    feature_id: str | None = None
    req_id: str | None = None
    evidence: list[str] | None = None

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }
        if self.feature_id:
            d["feature_id"] = self.feature_id
        if self.req_id:
            d["req_id"] = self.req_id
        if self.evidence:
            d["evidence"] = self.evidence
        return d
