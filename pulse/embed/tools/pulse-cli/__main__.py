#!/usr/bin/env python3
"""pulse CLI — core cards + pluggable modules."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

# __file__ = <project>/.pulse/tools/pulse-cli/__main__.py
_pulse_home = Path(__file__).resolve().parents[2]  # .pulse
_project = _pulse_home.parent
if _pulse_home.name != ".pulse":
    # legacy / kit-dev layout
    _project = Path(os.environ.get("PULSE_ROOT") or Path(__file__).resolve().parents[2]).resolve()
    _pulse_home = _project / ".pulse"
os.environ["PULSE_HOME"] = str(_pulse_home)
os.environ["PULSE_ROOT"] = str(_project)
sys.path.insert(0, str(_pulse_home / "tools"))
ROOT = _project

from pulse_lib import (  # noqa: E402
    BACKLOG_TYPES,
    DEFAULT_REGISTRY,
    StatusError,
    filter_features,
    generate_views,
    load_registry,
    save_registry,
    sort_features,
    validate_registry,
)
from pulse_lib.plugin import (  # noqa: E402
    PulseApp,
    load_plugins,
    run_generate_hooks,
)

_APP: PulseApp | None = None


def _app() -> PulseApp:
    global _APP
    if _APP is None:
        _APP = PulseApp(root=ROOT)
        load_plugins(_APP)
    return _APP


def cmd_validate(args: argparse.Namespace) -> int:
    data = load_registry(Path(args.path) if args.path else None)
    errors = validate_registry(data)
    if errors:
        print("INVALID:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"OK — {len(data.get('features') or [])} features")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    data = load_registry(Path(args.path) if args.path else None)
    errors = validate_registry(data)
    if errors:
        print("INVALID registry; fix before report:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    features = list(data.get("features") or [])
    features = filter_features(features, status=args.status, mvp=True if args.mvp else None)
    features = sort_features(features, args.sort)
    if args.json:
        print(json.dumps(features, ensure_ascii=False, indent=2))
        return 0
    print(f"{'ID':<28} {'Ph':>3} {'Status':<8} {'%':>3} {'Pri':>3} {'ROI':>3} MVP  Name")
    for f in features:
        print(
            f"{f.get('id', ''):<28} {f.get('phase', ''):>3} {f.get('status', ''):<8} "
            f"{f.get('percent', 0):>3} {f.get('priority', 0):>3} {f.get('roi', 0):>3} "
            f"{'Y' if f.get('mvp') else '-':<3}  {f.get('name', '')}"
        )
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    try:
        data = load_registry(Path(args.path) if args.path else None)
        generate_views(data)
        run_generate_hooks(_app(), data)
    except StatusError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    loaded = ", ".join(_app().loaded) or "(none)"
    print(f"Generated core views + plugin hooks [{loaded}]")
    return 0


def cmd_plugins(args: argparse.Namespace) -> int:
    app = _app()
    if args.json:
        print(
            json.dumps(
                {
                    "loaded": app.loaded,
                    "skipped": app.skipped,
                    "commands": [
                        {"name": c.name, "plugin": c.plugin, "help": c.help}
                        for c in app.commands
                    ],
                },
                indent=2,
            )
        )
        return 0
    print("Loaded plugins:", ", ".join(app.loaded) or "(none)")
    if app.skipped:
        print("Skipped:", ", ".join(app.skipped))
    print("Commands from plugins:")
    for c in app.commands:
        print(f"  {c.name:<12} [{c.plugin}] {c.help}")
    return 0


def _find_card(data: dict, cid: str) -> dict | None:
    for card in list(data.get("features") or []) + list(data.get("backlog") or []):
        if card.get("id") == cid:
            return card
    return None


def _regenerate(data: dict, path: Path | None) -> None:
    data["updated"] = date.today().isoformat()
    errors = validate_registry(data)
    if errors:
        raise StatusError("validate failed:\n- " + "\n- ".join(errors))
    save_registry(data, path)
    if path is None or Path(path).resolve() == DEFAULT_REGISTRY.resolve():
        fresh = load_registry()
        generate_views(fresh)
        run_generate_hooks(_app(), fresh)


def cmd_set(args: argparse.Namespace) -> int:
    path = Path(args.path) if args.path else None
    data = load_registry(path)
    touched_meta = False
    if getattr(args, "clear_focus", False):
        data.pop("focus_id", None)
        touched_meta = True
    focus_id = getattr(args, "focus", None)
    if focus_id:
        if _find_card(data, focus_id) is None:
            print(f"Unknown focus id: {focus_id}", file=sys.stderr)
            return 2
        data["focus_id"] = focus_id
        touched_meta = True

    if not args.feature:
        if not touched_meta:
            print("set requires --feature and/or --focus / --clear-focus", file=sys.stderr)
            return 2
        try:
            _regenerate(data, path)
        except StatusError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        msg = (
            f"focus_id={data.get('focus_id')!r}"
            if not getattr(args, "clear_focus", False)
            else "focus cleared"
        )
        print(f"Updated meta ({msg}); regenerated views.")
        return 0

    card = _find_card(data, args.feature)
    if card is None:
        print(f"Unknown card id: {args.feature}", file=sys.stderr)
        return 2
    for key in ("status", "name", "severity", "where", "why", "proposed_fix"):
        val = getattr(args, key)
        if val is not None:
            card[key] = val
    for key in ("percent", "priority", "roi", "phase"):
        val = getattr(args, key)
        if val is not None:
            card[key] = val
    if args.mvp is not None:
        card["mvp"] = args.mvp
    if args.clear_remaining:
        card["remaining"] = []
    if args.clear_mocks:
        card["mocks"] = []
    if getattr(args, "clear_blocks", False):
        card["blocks"] = []
    for bid in getattr(args, "add_blocks", None) or []:
        blocks = card.setdefault("blocks", [])
        if bid not in blocks:
            blocks.append(bid)
    for text in args.add_remaining or []:
        card.setdefault("remaining", []).append(text)
    for text in args.add_done or []:
        card.setdefault("done", []).append(text)
    for text in args.add_mock or []:
        card.setdefault("mocks", []).append(text)
    try:
        _regenerate(data, path)
    except StatusError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Updated {args.feature}; regenerated views.")
    return 0


def _new_card(args: argparse.Namespace) -> dict:
    card: dict = {"id": args.id, "type": args.type, "name": args.name}
    status = args.status or "todo"
    if args.type in BACKLOG_TYPES:
        card.update(
            {
                "status": status,
                "priority": args.priority if args.priority is not None else 5,
                "severity": args.severity or "medium",
            }
        )
        if args.where:
            card["where"] = args.where
        if args.why:
            card["why"] = args.why
        if args.proposed_fix:
            card["proposed_fix"] = args.proposed_fix
        if args.refs:
            card["refs"] = args.refs
        if getattr(args, "blocks", None):
            card["blocks"] = list(args.blocks)
    else:
        card.update(
            {
                "phase": args.phase,
                "status": status,
                "percent": args.percent
                if args.percent is not None
                else (100 if status == "done" else 0),
                "priority": args.priority if args.priority is not None else 5,
                "roi": args.roi if args.roi is not None else 5,
                "mvp": bool(args.mvp),
                "docs": {},
                "specs": [],
                "mocks": [],
                "done": [],
                "remaining": [],
                "evidence": {"paths_any": [], "paths_missing_means_todo": [], "pytest": []},
            }
        )
        if getattr(args, "blocks", None):
            card["blocks"] = list(args.blocks)
    return card


def cmd_new(args: argparse.Namespace) -> int:
    path = Path(args.path) if args.path else None
    data = load_registry(path)
    if _find_card(data, args.id) is not None:
        print(f"Card id already exists: {args.id}", file=sys.stderr)
        return 2
    card = _new_card(args)
    bucket = "backlog" if args.type in BACKLOG_TYPES else "features"
    data.setdefault(bucket, []).append(card)
    try:
        _regenerate(data, path)
    except StatusError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Created {args.type} card {args.id}; regenerated views.")
    return 0


def main() -> int:
    app = _app()
    parser = argparse.ArgumentParser(
        prog="pulse",
        description="Project pulse — core cards + pluggable modules",
    )
    parser.add_argument("--path", help="Registry YAML path")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_val = sub.add_parser("validate", help="Validate cards")
    p_val.set_defaults(func=cmd_validate)

    p_rep = sub.add_parser("report", help="Tabular feature report")
    p_rep.add_argument("--status", choices=["done", "partial", "todo", "blocked"])
    p_rep.add_argument("--mvp", action="store_true")
    p_rep.add_argument(
        "--sort",
        default="priority",
        choices=["priority", "roi", "percent", "phase", "name"],
    )
    p_rep.add_argument("--json", action="store_true")
    p_rep.set_defaults(func=cmd_report)

    p_gen = sub.add_parser("generate", help="Regenerate board + plugin views")
    p_gen.set_defaults(func=cmd_generate)

    p_plug = sub.add_parser("plugins", help="List loaded / skipped plugins")
    p_plug.add_argument("--json", action="store_true")
    p_plug.set_defaults(func=cmd_plugins)

    p_set = sub.add_parser("set", help="Patch one card and/or focus")
    p_set.add_argument("--feature", required=False)
    p_set.add_argument("--focus", help="Set workspace focus_id")
    p_set.add_argument("--clear-focus", action="store_true")
    p_set.add_argument("--status", choices=["done", "partial", "todo", "blocked"])
    p_set.add_argument("--name")
    p_set.add_argument("--percent", type=int)
    p_set.add_argument("--priority", type=int)
    p_set.add_argument("--roi", type=int)
    p_set.add_argument("--phase", type=int)
    p_set.add_argument("--severity", choices=["low", "medium", "high", "blocker"])
    p_set.add_argument("--where")
    p_set.add_argument("--why")
    p_set.add_argument("--proposed-fix", dest="proposed_fix")
    mvp_grp = p_set.add_mutually_exclusive_group()
    mvp_grp.add_argument("--mvp", dest="mvp", action="store_true", default=None)
    mvp_grp.add_argument("--no-mvp", dest="mvp", action="store_false")
    p_set.add_argument("--add-remaining", action="append", dest="add_remaining")
    p_set.add_argument("--add-done", action="append", dest="add_done")
    p_set.add_argument("--add-mock", action="append", dest="add_mock")
    p_set.add_argument("--add-blocks", action="append", dest="add_blocks")
    p_set.add_argument("--clear-blocks", action="store_true")
    p_set.add_argument("--clear-remaining", action="store_true")
    p_set.add_argument("--clear-mocks", action="store_true")
    p_set.set_defaults(func=cmd_set)

    p_new = sub.add_parser("new", help="Create feature | bug | tech-debt card")
    p_new.add_argument("--id", required=True)
    p_new.add_argument("--name", required=True)
    p_new.add_argument("--type", default="feature", choices=["feature", "bug", "tech-debt"])
    p_new.add_argument("--phase", type=int)
    p_new.add_argument("--status", choices=["done", "partial", "todo", "blocked"])
    p_new.add_argument("--percent", type=int)
    p_new.add_argument("--priority", type=int)
    p_new.add_argument("--roi", type=int)
    p_new.add_argument("--mvp", action="store_true")
    p_new.add_argument("--severity", choices=["low", "medium", "high", "blocker"])
    p_new.add_argument("--where")
    p_new.add_argument("--why")
    p_new.add_argument("--proposed-fix", dest="proposed_fix")
    p_new.add_argument("--ref", action="append", dest="refs")
    p_new.add_argument("--blocks", action="append", dest="blocks")
    p_new.set_defaults(func=cmd_new)

    # Plugin-registered commands
    for spec in app.commands:
        p = sub.add_parser(spec.name, help=f"{spec.help} [{spec.plugin}]")
        if spec.configure:
            spec.configure(p)
        p.set_defaults(func=spec.handler)

    args = parser.parse_args()
    # Allow top-level --path to flow into plugin commands lacking path
    if getattr(args, "path", None) is None and getattr(parser.parse_args, "__self__", None):
        pass
    try:
        return int(args.func(args))
    except StatusError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
