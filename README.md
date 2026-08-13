# pulse

A **project operating system** that lives entirely in **`.pulse/`** inside your repo.

It does **not** rewrite your architecture, force a folder layout, or touch files outside `.pulse/` on `init`. Commit `.pulse/` if the team should share status (pulse never auto-edits `.gitignore`).

## What it helps you do

| Need | How |
|---|---|
| See project status | Cards in `.pulse/features/` → board, explain |
| Next action fast | `.pulse/bin/pulse next --prompt` |
| Tech-debt / bugs | `new --type tech-debt\|bug` |
| Keep code clean | `quality-raise` + cleancode (optional Cursor link) |
| Sync docs ↔ code | drift / mismatch + optional sync rule |
| Stay extensible | `.pulse/plugins/` + pip entry points |

## Quick start

From this kit (dev checkout or `pip install .`):

```bash
pulse init /path/to/your/project \
  --project MyApp --tag-prefix MYAPP --code-roots src

cd /path/to/your/project
pip install -r .pulse/requirements.txt
.pulse/bin/pulse generate
.pulse/bin/pulse next --prompt
```

Refresh the vendored engine later (keeps your cards):

```bash
pulse upgrade /path/to/your/project
```

Optional agent rules (writes into `.cursor/` only when you ask):

```bash
pulse cursor link
pulse cursor unlink   # remove pulse-owned hooks.json entries
```

## Layout after init

```
your-project/
  .pulse/                 ← only pulse workspace
    features/             cards + _meta.yaml
    tools/                engine
    plugins/              host plugins
    bin/pulse             CLI
    cursor/               rule templates (not auto-linked)
    BOARD.md …
  src/ …                  ← your code, untouched
```

`code_roots` in `.pulse/features/_meta.yaml` point at **your** product folders (relative to project root).

Derived views under `.pulse/` (`BOARD.md`, `DRIFT.md`, reports) are summaries for humans/agents — prefer `next --prompt` in chat. Agents should edit **cards**, not vendored `.pulse/tools/` (`pulse upgrade` refreshes the engine).

## Docs

- [`docs/VISION.md`](docs/VISION.md)
- [`docs/PLUGINS.md`](docs/PLUGINS.md)
- [`docs/FEATURES.md`](docs/FEATURES.md)
- [`docs/SCHEMA.md`](docs/SCHEMA.md)
