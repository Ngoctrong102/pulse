#!/usr/bin/env python3
"""Deterministic clean-code structure metrics."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import yaml

from pulse_lib.paths import FEATURES_DIR, REPO_ROOT

SUBSCORE_DIMS = (
    "size",
    "responsibilities",
    "duplication",
    "naming",
    "error-handling",
    "dead-code",
)

# Deterministic structure signals (no AI): recomputed on every render/generate so
# the board auto-updates like the backlog — closing a linked tech-debt card lowers
# open-findings, and a file growing past budget lowers the structure score.
#
# ``area`` is a free-form label (backend, mobile, web, …). Language/LOC policy is
# by file extension — not by product folder names.
DEFAULT_CODE_EXTS = {
    ".py",
    ".swift",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".go",
    ".rs",
    ".kt",
    ".java",
}
LOC_BUDGET_BY_EXT = {
    ".py": 300,
    ".swift": 400,
    ".ts": 350,
    ".tsx": 350,
    ".js": 350,
    ".jsx": 350,
    ".go": 400,
    ".rs": 400,
    ".kt": 400,
    ".java": 400,
}
DEFAULT_LOC_BUDGET = 350
SEV_WEIGHT = {"blocker": 20, "high": 12, "medium": 6, "low": 3}
DEFAULT_SEV_WEIGHT = 6


def _module_exts(mod: dict[str, Any]) -> set[str]:
    """Optional per-module ``exts: [.py, .ts]``; else the default language set."""
    raw = mod.get("exts")
    if isinstance(raw, list) and raw:
        return {str(x) if str(x).startswith(".") else f".{x}" for x in raw}
    return set(DEFAULT_CODE_EXTS)


def _loc_budget_for(path: Path, mod: dict[str, Any]) -> int:
    override = mod.get("loc_budget")
    if isinstance(override, int) and override > 0:
        return override
    return int(LOC_BUDGET_BY_EXT.get(path.suffix.lower(), DEFAULT_LOC_BUDGET))

# score -> (emoji, label)
_BANDS = (
    (85, "🟢", "clean"),
    (60, "🟡", "warn"),
    (0, "🔴", "dirty"),
)


def score_band(score: int | None) -> tuple[str, str]:
    """Return (emoji, label) for a score; unscanned modules get a neutral band."""
    if score is None:
        return ("⚪", "unscanned")
    for threshold, emoji, label in _BANDS:
        if score >= threshold:
            return (emoji, label)
    return ("🔴", "dirty")


# --------------------------------------------------------------------------- #
# Staleness (deterministic, git-based): a scanned module is stale when files
# under its globs changed since the last scan. This never re-scores — it only
# flags that the AI score may be out of date and the module should be rescanned.
# --------------------------------------------------------------------------- #
def _pathspecs(globs: list[str] | None) -> list[str]:
    specs: list[str] = []
    for g in globs or []:
        if g.endswith("/**"):
            specs.append(g[:-3] + "/")
        elif g.endswith("/*"):
            specs.append(g[:-2] + "/")
        else:
            specs.append(g)
    return specs


def _git(args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def head_commit() -> str | None:
    out = _git(["rev-parse", "--short", "HEAD"])
    return out.strip() if out and out.strip() else None


def is_module_stale(mod: dict[str, Any]) -> bool:
    """True when a scanned module's files changed since it was last scanned."""
    if mod.get("score") is None:
        return False
    specs = _pathspecs(mod.get("globs"))
    if not specs:
        return False
    commit = mod.get("last_scan_commit")
    if commit:
        diff = _git(["diff", "--name-only", str(commit), "--", *specs])
        if diff is None:
            return False
        if diff.strip():
            return True
        others = _git(["ls-files", "--others", "--exclude-standard", "--", *specs])
        return bool(others and others.strip())
    scanned = mod.get("scanned_at")
    if scanned:
        log = _git(["log", "--since", str(scanned), "--name-only", "--pretty=format:", "--", *specs])
        return bool(log and log.strip())
    return False


def stale_module_ids(mods: list[dict[str, Any]]) -> set[str]:
    return {str(m.get("id")) for m in mods if is_module_stale(m)}


# --------------------------------------------------------------------------- #
# Deterministic metrics (findings-driven + structure score). Unlike the AI
# ``score``, these are recomputed on every render/generate, so the board reflects
# reality automatically: closing a linked tech-debt card lowers open-findings, and
# an oversized file lowers the structure score — no AI pass required.
# --------------------------------------------------------------------------- #
def finding_index(features_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    """Map status-card id -> {status, severity} for every card on disk."""
    target = features_dir or FEATURES_DIR
    index: dict[str, dict[str, Any]] = {}
    if not target.is_dir():
        return index
    for path in sorted(target.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        try:
            card = yaml.safe_load(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if isinstance(card, dict) and card.get("id"):
            index[str(card["id"])] = {
                "status": card.get("status"),
                "severity": card.get("severity"),
            }
    return index


def _module_code_files(mod: dict[str, Any]) -> list[Path]:
    """Resolve a module's globs to concrete source files (by extension policy)."""
    exts = {e.lower() for e in _module_exts(mod)}
    if not exts:
        return []
    found: set[Path] = set()
    for g in mod.get("globs") or []:
        if g.endswith("/**"):
            base = REPO_ROOT / g[:-3]
            candidates = base.rglob("*") if base.is_dir() else []
        elif g.endswith("/*"):
            base = REPO_ROOT / g[:-2]
            candidates = base.glob("*") if base.is_dir() else []
        elif any(ch in g for ch in "*?["):
            candidates = REPO_ROOT.glob(g)
        else:
            p = REPO_ROOT / g
            candidates = [p] if p.is_file() else []
        for p in candidates:
            if p.is_file() and p.suffix.lower() in exts:
                found.add(p)
    return sorted(found)


def _loc(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def module_metrics(
    mod: dict[str, Any], findings_index: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Deterministic health signals for a module (findings + structure)."""
    idx = finding_index() if findings_index is None else findings_index
    findings = [str(f) for f in (mod.get("findings") or [])]
    open_ids = [f for f in findings if (idx.get(f) or {}).get("status") != "done"]
    weighted = sum(
        SEV_WEIGHT.get(str((idx.get(f) or {}).get("severity")), DEFAULT_SEV_WEIGHT)
        for f in open_ids
    )
    files = _module_code_files(mod)
    file_stats = [(_loc(p), _loc_budget_for(p, mod)) for p in files]
    locs = [n for n, _ in file_stats]
    oversized = sum(1 for n, budget in file_stats if n > budget)
    # Report the tightest budget in play (or module override / default).
    if isinstance(mod.get("loc_budget"), int) and mod["loc_budget"] > 0:
        report_budget = int(mod["loc_budget"])
    elif file_stats:
        report_budget = min(b for _, b in file_stats)
    else:
        report_budget = DEFAULT_LOC_BUDGET
    structure = max(0, 100 - min(45, oversized * 9) - min(45, weighted))
    return {
        "open_findings": len(open_ids),
        "total_findings": len(findings),
        "code_files": len(locs),
        "oversized_files": oversized,
        "max_loc": max(locs) if locs else 0,
        "loc_budget": report_budget,
        "structure_score": structure,
    }


# --------------------------------------------------------------------------- #
