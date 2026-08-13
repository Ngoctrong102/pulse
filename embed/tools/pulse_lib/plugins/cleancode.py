"""Clean-code scoreboard plugin."""

from __future__ import annotations

import argparse
from typing import Any

from pulse_lib import BOARD_PATH, StatusError, render_board
from pulse_lib import cleancode as _cc
from pulse_lib.plugin import PulseApp


class CleancodePlugin:
    name = "cleancode"

    def setup(self, app: PulseApp) -> None:
        def configure(p: argparse.ArgumentParser) -> None:
            sub = p.add_subparsers(dest="cc_action", required=True)

            cc_list = sub.add_parser("list", help="List module scores")
            cc_list.add_argument("--json", action="store_true")
            cc_list.add_argument("--path", help="Alternate cleancode dir")
            cc_list.set_defaults(_cc_fn=_cc.cmd_cleancode_list)

            cc_set = sub.add_parser("set", help="Set a module's clean-code score")
            cc_set.add_argument("--module", required=True)
            cc_set.add_argument("--score", type=int)
            cc_set.add_argument("--summary")
            cc_set.add_argument("--subscore", action="append", help="dim=value")
            cc_set.add_argument("--finding", action="append")
            cc_set.add_argument("--clear-findings", action="store_true")
            cc_set.add_argument("--path")
            cc_set.set_defaults(_cc_fn=_cc.cmd_cleancode_set)

            cc_scan = sub.add_parser("scan", help="Paste-ready scan prompt")
            cc_scan.add_argument("--module", required=True)
            cc_scan.add_argument("--path")
            cc_scan.set_defaults(_cc_fn=_cc.cmd_cleancode_scan)

            cc_fix = sub.add_parser("fix", help="Paste-ready fix prompt")
            cc_fix.add_argument("--module", required=True)
            cc_fix.add_argument("--path")
            cc_fix.set_defaults(_cc_fn=_cc.cmd_cleancode_fix)

        def cmd(args: argparse.Namespace) -> int:
            fn = getattr(args, "_cc_fn", None)
            if fn is None:
                return 2
            return int(fn(args))

        def on_generate(registry: dict[str, Any]) -> None:
            if not _cc.CLEANCODE_DIR.is_dir():
                return
            mods = _cc.load_modules()
            cc_errors = _cc.validate_modules(mods)
            if cc_errors:
                raise StatusError("cleancode validate failed:\n- " + "\n- ".join(cc_errors))
            stale_ids = _cc.stale_module_ids(mods)
            section = _cc.render_cleancode_board_section(mods, stale_ids)
            board_text = render_board(registry)
            if section:
                board_text = board_text + "\n" + section + "\n"
            BOARD_PATH.write_text(board_text, encoding="utf-8")
            _cc.CLEANCODE_VIEW.parent.mkdir(parents=True, exist_ok=True)
            _cc.CLEANCODE_VIEW.write_text(
                _cc.render_cleancode_view(mods, stale_ids), encoding="utf-8"
            )

        app.add_command(
            "cleancode",
            help="Clean-code scoreboard (list/set/scan/fix)",
            handler=cmd,
            configure=configure,
            plugin=self.name,
        )
        app.on_generate(on_generate, plugin=self.name)


PLUGIN = CleancodePlugin()
