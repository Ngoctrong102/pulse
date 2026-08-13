#!/usr/bin/env python3
"""Clean-code module cards — load / save / validate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from pulse_lib import StatusError
from pulse_lib.paths import CLEANCODE_DIR

CARD_KEY_ORDER = [
    "id", "type", "name", "area", "globs", "score", "scanned_at",
    "summary", "subscores", "findings", "last_scan_commit",
]

# Load / save
# --------------------------------------------------------------------------- #
def _module_dir(directory: Path | None) -> Path:
    return directory or CLEANCODE_DIR


def load_modules(directory: Path | None = None) -> list[dict[str, Any]]:
    target = _module_dir(directory)
    if not target.is_dir():
        return []
    mods: list[dict[str, Any]] = []
    for path in sorted(target.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        card = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(card, dict):
            raise StatusError(f"Clean-code module is not a mapping: {path}")
        card.setdefault("type", "cleancode")
        mods.append(card)
    return sorted(mods, key=lambda m: (str(m.get("area", "")), str(m.get("id", ""))))


def load_module(module_id: str, directory: Path | None = None) -> dict[str, Any] | None:
    for mod in load_modules(directory):
        if mod.get("id") == module_id:
            return mod
    return None


def _dump_module(card: dict[str, Any]) -> str:
    ordered: dict[str, Any] = {k: card[k] for k in CARD_KEY_ORDER if k in card}
    for k, v in card.items():
        if k not in ordered:
            ordered[k] = v
    return yaml.safe_dump(ordered, allow_unicode=True, sort_keys=False, default_flow_style=False)


def save_module(card: dict[str, Any], directory: Path | None = None) -> None:
    target = _module_dir(directory)
    target.mkdir(parents=True, exist_ok=True)
    mid = card.get("id")
    if not mid:
        raise StatusError("Clean-code module missing id")
    (target / f"{mid}.yaml").write_text(_dump_module(card), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def validate_modules(mods: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for i, mod in enumerate(mods):
        prefix = f"cleancode[{i}]"
        mid = mod.get("id")
        if not isinstance(mid, str) or not mid.strip():
            errors.append(f"{prefix}: missing id")
        elif mid in seen:
            errors.append(f"{prefix}: duplicate id {mid}")
        else:
            seen.add(mid)
        area = mod.get("area")
        if not isinstance(area, str) or not area.strip():
            errors.append(f"{prefix} ({mid}): area must be a non-empty label")
        exts = mod.get("exts")
        if exts is not None and (
            not isinstance(exts, list) or any(not isinstance(x, str) for x in exts)
        ):
            errors.append(f"{prefix} ({mid}): exts must be a list of strings when set")
        loc_budget = mod.get("loc_budget")
        if loc_budget is not None and (not isinstance(loc_budget, int) or loc_budget <= 0):
            errors.append(f"{prefix} ({mid}): loc_budget must be a positive int when set")
        globs = mod.get("globs")
        if not isinstance(globs, list) or not globs:
            errors.append(f"{prefix} ({mid}): globs must be a non-empty list")
        score = mod.get("score")
        if score is not None and (not isinstance(score, int) or score < 0 or score > 100):
            errors.append(f"{prefix} ({mid}): score must be int 0-100 or null")
        findings = mod.get("findings") or []
        if not isinstance(findings, list) or any(not isinstance(x, str) for x in findings):
            errors.append(f"{prefix} ({mid}): findings must be a list of card ids")
        subs = mod.get("subscores") or {}
        if not isinstance(subs, dict):
            errors.append(f"{prefix} ({mid}): subscores must be a mapping")
    return errors


# --------------------------------------------------------------------------- #
