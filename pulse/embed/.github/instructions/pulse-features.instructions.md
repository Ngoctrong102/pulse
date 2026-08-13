---
applyTo: ".pulse/features/**,.pulse/cleancode/**"
---

# Pulse cards

These YAML files are the status source of truth. Prefer `.pulse/bin/pulse set` / `new` / `generate` over hand-editing large diffs.

- Do not mark `status: done` while `mocks` or `remaining` are non-empty.
- Keep `tag_prefix` / `plugins` in `_meta.yaml` when editing meta.
- After card changes: `.pulse/bin/pulse generate`.
