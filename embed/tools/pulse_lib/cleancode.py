#!/usr/bin/env python3
"""Clean-code scoreboard: per-module clean-code scores for the status dashboard.

Source of truth is the per-module directory ``.pulse/cleancode/`` (one YAML
file per module). Each module carries the file ``globs`` it owns plus a
clean-code ``score`` (0-100) set by the most recent AI scan. ``score: null``
means the module has not been scanned yet, so it shows no score.

Scoring is AI-judged against the ``quality-raise`` rubric: the dashboard
exposes two copy-prompt buttons per module — *Scan* (survey for smells, log
tech-debt cards, set the score) and *Fix* (clean the module, then rescan). The
agent writes results back with ``pulse cleancode set``.
"""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from pulse_lib import StatusError
from pulse_lib.cleancode_prompts import RUBRIC_CHECKS, build_fix_prompt, build_scan_prompt
from pulse_lib.paths import CLEANCODE_DIR, CLEANCODE_VIEW, FEATURES_DIR, REPO_ROOT


# Rubric dimensions mirror the quality-raise self-check table.
SUBSCORE_DIMS = (
    "size",
    "responsibilities",
    "duplication",
    "naming",
    "error-handling",
    "dead-code",
)

CARD_KEY_ORDER = [
    "id", "type", "name", "area", "globs", "score", "scanned_at",
    "summary", "subscores", "findings", "last_scan_commit",
]

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
# Rendering
# --------------------------------------------------------------------------- #
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
    for m in mods:
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
    for m in mods:
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


# --------------------------------------------------------------------------- #
# Prompts (copy-to-chat)
# --------------------------------------------------------------------------- #
def _module_or_die(module_id: str, directory: Path | None) -> dict[str, Any]:
    mod = load_module(module_id, directory)
    if not mod:
        raise StatusError(f"Clean-code module not found: {module_id}")
    return mod


# --------------------------------------------------------------------------- #
# CLI command handlers (wired from tools/pulse-cli/__main__.py)
# --------------------------------------------------------------------------- #
def _regenerate(directory: Path | None) -> None:
    """Regenerate dashboard views, but only when writing the real registry."""
    if directory is not None and directory != CLEANCODE_DIR:
        errors = validate_modules(load_modules(directory))
        if errors:
            raise StatusError("cleancode validate failed:\n- " + "\n- ".join(errors))
        return
    from pulse_lib import generate_views

    generate_views()


def cmd_cleancode_list(args: Any) -> int:
    directory = Path(args.path) if getattr(args, "path", None) else None
    mods = load_modules(directory)
    stale = stale_module_ids(mods)
    metrics = _metrics_map(mods)
    if getattr(args, "json", False):
        import json

        payload = [
            {**m, "stale": m.get("id") in stale, **metrics[str(m.get("id"))]}
            for m in mods
        ]
        print(json.dumps({"modules": payload}, ensure_ascii=False))
        return 0
    scanned, total, avg = _averages(mods)
    struct_avg = _structure_average(metrics)
    open_total = sum(v["open_findings"] for v in metrics.values())
    tail = f" · avg {avg}" if avg is not None else ""
    tail += f" · {len(stale)} stale" if stale else ""
    print(
        f"Clean-code: struct avg {struct_avg} · {open_total} open findings · "
        f"AI {scanned}/{total} scanned{tail}"
    )
    for m in mods:
        emoji, _label = score_band(m.get("score"))
        score = m.get("score")
        met = metrics[str(m.get("id"))]
        s_emoji, _s = score_band(met["structure_score"])
        flag = " ⚠️ rescan" if m.get("id") in stale else ""
        ai = str(score) if isinstance(score, int) else "—"
        print(
            f"  {s_emoji} struct {met['structure_score']:>3}  {emoji} AI {ai:>3}  "
            f"{met['open_findings']}/{met['total_findings']} fnd  "
            f"{str(m.get('id')):<20} {m.get('scanned_at') or 'never'}{flag}"
        )
    return 0


def cmd_cleancode_scan(args: Any) -> int:
    directory = Path(args.path) if getattr(args, "path", None) else None
    print(build_scan_prompt(_module_or_die(args.module, directory)))
    return 0


def cmd_cleancode_fix(args: Any) -> int:
    directory = Path(args.path) if getattr(args, "path", None) else None
    print(build_fix_prompt(_module_or_die(args.module, directory)))
    return 0


def _parse_subscore(pairs: list[str] | None) -> dict[str, int]:
    out: dict[str, int] = {}
    for raw in pairs or []:
        if "=" not in raw:
            raise StatusError(f"--subscore expects dim=value, got {raw!r}")
        dim, val = raw.split("=", 1)
        try:
            out[dim.strip()] = int(val)
        except ValueError as exc:
            raise StatusError(f"--subscore value must be int: {raw!r}") from exc
    return out


def cmd_cleancode_set(args: Any) -> int:
    directory = Path(args.path) if getattr(args, "path", None) else None
    mod = _module_or_die(args.module, directory)
    if args.score is not None:
        if args.score < 0 or args.score > 100:
            raise StatusError("--score must be 0-100")
        mod["score"] = args.score
    if args.summary is not None:
        mod["summary"] = args.summary
    subs = _parse_subscore(args.subscore)
    if subs:
        mod["subscores"] = {**(mod.get("subscores") or {}), **subs}
    if args.clear_findings:
        mod["findings"] = []
    if args.finding:
        existing = list(mod.get("findings") or [])
        for f in args.finding:
            if f not in existing:
                existing.append(f)
        mod["findings"] = existing
    mod["scanned_at"] = date.today().isoformat()
    commit = head_commit()
    if commit:
        mod["last_scan_commit"] = commit
    save_module(mod, directory)
    _regenerate(directory)
    regenerated = directory is None or directory == CLEANCODE_DIR
    tail = "; regenerated views." if regenerated else " (isolated; views not regenerated)."
    print(f"Updated clean-code module {args.module}{tail}")
    return 0
