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
    "pulse_version",
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
# Views (implemented in views_board; re-exported for stable imports)
# --------------------------------------------------------------------------- #
from pulse_lib.views_board import (  # noqa: E402
    render_board,
    render_backlog_section,
    render_status_table,
    patch_phases_file,
    render_tech_debt_doc,
    parse_frontmatter,
    build_id_catalog,
    render_id_index,
    generate_views,
)

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
