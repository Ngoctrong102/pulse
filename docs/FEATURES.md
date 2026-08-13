# Capabilities

| Capability | Status |
|---|---|
| Status cards (feature / bug / tech-debt) | done |
| Focus → Queue / next / explain | done |
| Unified queue (`lane=all`, severity→priority→roi) | done |
| Drift (docs↔board leftover) | done |
| Mismatch detect/heal | done |
| Clean-code scoreboard | done |
| Quality-raise (self-check → backlog) | done |
| Docs↔code sync rule + stop-hook | done |
| Configurable `code_roots` + `tag_prefix` | done |
| Plugins (builtin / host / pip) | done |
| Spec Kit prompts | optional (`speckit`) |

Install surface: **`.pulse/` only** — no forced product layout, no auto-`.gitignore`.

### Agent workflow tips

- Prefer `.pulse/bin/pulse next --prompt` / `next --json` over pasting full `BOARD.md`.
- Derived files (`BOARD.md`, `DRIFT.md`, `*-report.json`) are **summaries** — do not dump full JSON into chat unless debugging detect/heal.
- Edit cards under `.pulse/features/` / `.pulse/cleancode/`; refresh the engine with `pulse upgrade` (do not hand-edit `.pulse/tools/`).

Not in scope: prescribing any product’s concrete stack or folder layout.

See [`VISION.md`](./VISION.md) · [`SCHEMA.md`](./SCHEMA.md).
