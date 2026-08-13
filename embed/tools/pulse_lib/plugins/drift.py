"""Docs/spec ↔ board drift plugin."""

from __future__ import annotations

import argparse
import json
from typing import Any

from pulse_lib import load_registry
from pulse_lib.docs_drift import (
    analyze_docs_drift,
    build_docs_drift_prompt,
    write_drift_report,
)
from pulse_lib.plugin import PulseApp


class DriftPlugin:
    name = "drift"

    def setup(self, app: PulseApp) -> None:
        def configure(p: argparse.ArgumentParser) -> None:
            p.add_argument("--json", action="store_true")
            p.add_argument("--prompt", action="store_true")
            p.add_argument("--path", help="Alternate registry path")

        def cmd(args: argparse.Namespace) -> int:
            data = load_registry(None if not args.path else __import__("pathlib").Path(args.path))
            report = analyze_docs_drift(data)
            write_drift_report(report)
            if args.prompt:
                print(build_docs_drift_prompt(data, report))
                return 0
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
                return 0
            t = report.get("totals") or {}
            c = report.get("counts") or {}
            print(
                f"Drift: rem_bullets={t.get('total_remaining_bullets')} mocks={t.get('total_mocks')} "
                f"unmapped_ids={t.get('docs_ids_not_on_board')} spec_debt={t.get('spec_debt_items')} "
                f"tag_gaps={t.get('tag_gaps')} orphan_tags={t.get('orphan_code_tags')} "
                f"evidence_untagged={t.get('evidence_untagged_paths')}"
            )
            print(
                f"Findings: {c.get('critical', 0)} critical · {c.get('warning', 0)} warning · "
                f"{c.get('info', 0)} info"
            )
            print("Wrote .pulse/DRIFT.md")
            return 0

        def on_generate(registry: dict[str, Any]) -> None:
            write_drift_report(analyze_docs_drift(registry))

        app.add_command("drift", help="Docs/spec ↔ board drift report", handler=cmd, configure=configure, plugin=self.name)
        app.on_generate(on_generate, plugin=self.name)


PLUGIN = DriftPlugin()
