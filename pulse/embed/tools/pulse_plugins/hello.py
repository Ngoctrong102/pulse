"""Example host plugin — copy into a project's .pulse/plugins/.

Shows how to add a new command without forking pulse core.
"""

from __future__ import annotations

import argparse

from pulse_lib.plugin import PulseApp


class HelloPlugin:
    name = "hello"

    def setup(self, app: PulseApp) -> None:
        def configure(p: argparse.ArgumentParser) -> None:
            p.add_argument("--name", default="world")

        def cmd(args: argparse.Namespace) -> int:
            print(f"hello, {args.name} — custom pulse plugin works")
            return 0

        app.add_command(
            "hello",
            help="Demo custom command (example plugin)",
            handler=cmd,
            configure=configure,
            plugin=self.name,
        )


PLUGIN = HelloPlugin()
