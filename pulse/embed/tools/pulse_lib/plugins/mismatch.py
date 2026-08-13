"""Mismatch detect / heal plugin."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pulse_lib import StatusError
from pulse_lib.paths import MISMATCH_REPORT
from pulse_lib.mismatch import detect, write_report
from pulse_lib.mismatch_heal import run_heal
from pulse_lib.plugin import PulseApp


class MismatchPlugin:
    name = "mismatch"

    def setup(self, app: PulseApp) -> None:
        def configure(p: argparse.ArgumentParser) -> None:
            sub = p.add_subparsers(dest="mismatch_action", required=True)

            det = sub.add_parser("detect", help="Read-only mismatch detect → report")
            det.add_argument("--registry", type=Path, default=None)
            det.add_argument(
                "--out",
                type=Path,
                default=None,
                help="Default: .pulse/mismatch-report.json",
            )
            det.add_argument(
                "--verbose",
                action="store_true",
                help="Write full findings list (default: top-N truncated on disk)",
            )
            det.set_defaults(_mm="detect")

            heal = sub.add_parser(
                "heal",
                help="Apply safe patches from a detect report (requires --from-report)",
            )
            heal.add_argument("--from-report", type=Path, required=True)
            heal.add_argument("--dry-run", action="store_true")
            heal.add_argument("--apply", action="store_true")
            heal.set_defaults(_mm="heal")

        def cmd(args: argparse.Namespace) -> int:
            action = getattr(args, "_mm", None) or args.mismatch_action
            if action == "detect":
                out = args.out or MISMATCH_REPORT
                try:
                    _findings, report = detect(args.registry)
                except StatusError as exc:
                    print(str(exc), file=sys.stderr)
                    return 2
                write_report(report, out, verbose=bool(getattr(args, "verbose", False)))
                print(f"Wrote {out} and {out.with_suffix('.md')}")
                print(
                    f"Summary: critical={report['summary']['critical']} "
                    f"warning={report['summary']['warning']} "
                    f"info={report['summary']['info']}"
                    + (" (full)" if getattr(args, "verbose", False) else " (truncated on disk)")
                )
                return 1 if report["summary"]["critical"] else 0

            if action == "heal":
                apply = bool(args.apply)
                dry_run = bool(args.dry_run) or not apply
                return run_heal(
                    from_report=Path(args.from_report),
                    apply=apply,
                    dry_run=dry_run,
                    registry=None,
                )

            return 2

        app.add_command(
            "mismatch",
            help="Mismatch detect/heal (Toolkit A/B)",
            handler=cmd,
            configure=configure,
            plugin=self.name,
        )


PLUGIN = MismatchPlugin()
