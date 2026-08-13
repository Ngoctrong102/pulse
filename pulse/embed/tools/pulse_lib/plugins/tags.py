"""Requirement-tag audit helpers (used by drift; exposed as toggleable module).

When listed under ``plugins.disabled``, ``analyze_docs_drift`` skips tag gaps,
orphan code tags, and evidence-untagged audits.
"""

from __future__ import annotations

from typing import Any

from pulse_lib.plugin import PulseApp


class TagsPlugin:
    name = "tags"

    def setup(self, app: PulseApp) -> None:
        def _noop(_registry: dict[str, Any]) -> None:
            return None

        app.on_generate(_noop, plugin=self.name)


PLUGIN = TagsPlugin()
