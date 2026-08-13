"""Requirement-tag audit helpers (used by drift; exposed as toggleable module)."""

from __future__ import annotations

from typing import Any

from pulse_lib.plugin import PulseApp


class TagsPlugin:
    name = "tags"

    def setup(self, app: PulseApp) -> None:
        def _noop(_registry: dict[str, Any]) -> None:
            return None

        # Tag audit is invoked from docs_drift; this plugin gates whether
        # hosts consider tagging part of their pulse surface.
        app.on_generate(_noop, plugin=self.name)


PLUGIN = TagsPlugin()
