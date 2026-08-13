"""Explain / next / tag paste-ready prompt plugin."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pulse_lib import load_registry
from pulse_lib.next_actions import (
    build_explain_feature_prompt,
    build_explain_project_prompt,
    build_next_action_prompt,
    build_tag_prompt,
    build_untagged_cleanup_prompt,
    load_mismatch_summary,
)
from pulse_lib.next_ranking import build_next_payload
from pulse_lib.plugin import PulseApp


class PromptsPlugin:
    name = "prompts"

    def setup(self, app: PulseApp) -> None:
        def cfg_explain(p: argparse.ArgumentParser) -> None:
            p.add_argument("--feature", help="Feature / backlog id")
            p.add_argument("--path")

        def cmd_explain(args: argparse.Namespace) -> int:
            data = load_registry(Path(args.path) if getattr(args, "path", None) else None)
            mismatch = load_mismatch_summary()
            if args.feature:
                print(build_explain_feature_prompt(data, args.feature, mismatch))
            else:
                print(build_explain_project_prompt(data, mismatch))
            return 0

        def cfg_next(p: argparse.ArgumentParser) -> None:
            p.add_argument("--json", action="store_true")
            p.add_argument("--prompt", action="store_true")
            p.add_argument("--feature")
            p.add_argument("--sub", type=int, default=None)
            p.add_argument("--limit", type=int, default=7)
            p.add_argument("--lane", default="all", choices=["all", "ship", "fix", "debt", "hygiene"])
            p.add_argument("--mvp", action="store_true")
            p.add_argument("--path")

        def cmd_next(args: argparse.Namespace) -> int:
            data = load_registry(Path(args.path) if getattr(args, "path", None) else None)
            mismatch = load_mismatch_summary()
            lane = getattr(args, "lane", None) or "all"
            limit = int(args.limit or 7)
            if args.prompt:
                print(
                    build_next_action_prompt(
                        data,
                        feature_id=args.feature,
                        mismatch=mismatch,
                        sub_index=args.sub,
                        lane=lane,
                    )
                )
                return 0
            payload = build_next_payload(
                data,
                mismatch=mismatch,
                lane=lane,
                limit=limit,
                mvp_only=bool(args.mvp),
            )
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0
            items = payload.get("queue") or []
            cont = payload.get("continue") or {}
            focus = payload.get("focus")
            if focus and focus.get("valid"):
                print(f"Focus: {focus.get('id')} ({focus.get('status')} {focus.get('percent')}%)")
            print(f"Continue [{cont.get('kind')}]: {cont.get('id')} — {cont.get('action')}")
            print(f"Lane={lane} queue={len(items)}")
            if not items:
                print("Queue empty.")
                return 0
            print(f"{'#':<3} {'Lane':<7} {'ID':<28} {'P':>2} Action")
            for i, item in enumerate(items, 1):
                print(
                    f"{i:<3} {str(item.get('lane') or '-'):<7} {str(item.get('id') or ''):<28} "
                    f"{item.get('priority', '')!s:>2} {str(item.get('action') or '')[:50]}"
                )
                print(f"    why: {item.get('why')}")
            return 0

        def cfg_tag(p: argparse.ArgumentParser) -> None:
            p.add_argument("--feature")
            p.add_argument("--untagged-cleanup", action="store_true")
            p.add_argument(
                "--all",
                action="store_true",
                help="With --untagged-cleanup: whole-project (default is focus / top features)",
            )
            p.add_argument("--path")

        def cmd_tag(args: argparse.Namespace) -> int:
            data = load_registry(Path(args.path) if getattr(args, "path", None) else None)
            if args.untagged_cleanup:
                print(
                    build_untagged_cleanup_prompt(
                        data, all_project=bool(getattr(args, "all", False))
                    )
                )
                return 0
            if not args.feature:
                print(
                    "tag requires --feature ID, or --untagged-cleanup",
                    file=sys.stderr,
                )
                return 2
            print(build_tag_prompt(data, args.feature))
            return 0

        app.add_command(
            "explain",
            help="Paste-ready status explain prompt",
            handler=cmd_explain,
            configure=cfg_explain,
            plugin=self.name,
        )
        app.add_command(
            "next",
            help="Ranked next actions / Continue prompt",
            handler=cmd_next,
            configure=cfg_next,
            plugin=self.name,
        )
        app.add_command(
            "tag",
            help="Paste-ready requirement-tag prompt",
            handler=cmd_tag,
            configure=cfg_tag,
            plugin=self.name,
        )


PLUGIN = PromptsPlugin()
