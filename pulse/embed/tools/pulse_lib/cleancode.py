#!/usr/bin/env python3
"""Clean-code scoreboard: per-module clean-code scores for the status dashboard.

Source of truth is the per-module directory ``.pulse/cleancode/`` (one YAML
file per module). Facade re-exporting store / metrics / render / CLI.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from pulse_lib import StatusError
from pulse_lib.cleancode_prompts import build_fix_prompt, build_scan_prompt
from pulse_lib.cleancode_metrics import (  # noqa: F401
    DEFAULT_CODE_EXTS,
    DEFAULT_LOC_BUDGET,
    DEFAULT_SEV_WEIGHT,
    LOC_BUDGET_BY_EXT,
    SEV_WEIGHT,
    SUBSCORE_DIMS,
    _loc_budget_for,
    _module_exts,
    finding_index,
    head_commit,
    is_module_stale,
    module_metrics,
    score_band,
    stale_module_ids,
)
from pulse_lib.cleancode_store import (  # noqa: F401
    CARD_KEY_ORDER,
    load_module,
    load_modules,
    save_module,
    validate_modules,
)
from pulse_lib.cleancode_render import (  # noqa: F401
    _averages,
    _metrics_map,
    _structure_average,
    render_cleancode_board_section,
    render_cleancode_view,
)
from pulse_lib.paths import CLEANCODE_DIR, CLEANCODE_VIEW  # noqa: F401

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
