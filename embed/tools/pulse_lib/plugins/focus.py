"""Focus / Continue / lane queue — surfaces via ``next --json`` (prompts plugin).

This plugin exists so hosts can disable focus semantics independently later,
and so ``plugins list`` shows Focus as a first-class module.
"""

from __future__ import annotations

from typing import Any

from pulse_lib.plugin import PulseApp


class FocusPlugin:
    name = "focus"

    def setup(self, app: PulseApp) -> None:
        # Ranking lives in next_ranking; prompts plugin calls it.
        # Hook keeps module discoverable / toggleable.
        def _noop(_registry: dict[str, Any]) -> None:
            return None

        app.on_generate(_noop, plugin=self.name)


PLUGIN = FocusPlugin()
