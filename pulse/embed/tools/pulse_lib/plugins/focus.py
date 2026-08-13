"""Focus / Continue / lane queue — surfaces via ``next --json`` (prompts plugin).

When this plugin is listed under ``plugins.disabled``, ranking skips focus
semantics (``resolve_continue`` / payload ``focus``) and promotes from the queue only.
"""

from __future__ import annotations

from typing import Any

from pulse_lib.plugin import PulseApp


class FocusPlugin:
    name = "focus"

    def setup(self, app: PulseApp) -> None:
        def _noop(_registry: dict[str, Any]) -> None:
            return None

        app.on_generate(_noop, plugin=self.name)


PLUGIN = FocusPlugin()
