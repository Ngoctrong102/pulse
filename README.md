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

## Install

From GitHub (recommended):

```bash
pip install "git+https://github.com/Ngoctrong102/pulse.git"
```

Pinned to a commit / tag:

```bash
pip install "git+https://github.com/Ngoctrong102/pulse.git@main"
# or: pip install "git+https://github.com/Ngoctrong102/pulse.git@v0.4.0"
```

From a local checkout:

```bash
git clone https://github.com/Ngoctrong102/pulse.git
cd pulse
pip install -e .
```

Check:

```bash
pulse version
```

## Quick start

```bash
pulse init /path/to/your/project \
  --project MyApp --tag-prefix MYAPP --code-roots src

cd /path/to/your/project
pip install -r .pulse/requirements.txt   # PyYAML for the vendored engine
.pulse/bin/pulse generate
.pulse/bin/pulse next --prompt
```

Optional agent rules (writes into `.cursor/` only when you ask):

```bash
pulse cursor link
pulse cursor unlink   # remove pulse-owned hooks.json entries
```

## Upgrade

When the kit on GitHub moves forward, refresh the **vendored** engine inside a project
(`.pulse/tools/`, `.pulse/cursor/`, `.pulse/bin/pulse`) **without** touching your cards:

```bash
pip install -U "git+https://github.com/Ngoctrong102/pulse.git"
pulse upgrade /path/to/your/project
# alias: pulse update /path/to/your/project
```

Preserved: `.pulse/features/`, `.pulse/cleancode/`, `.pulse/plugins/`, generated views.  
Stamped: `pulse_version` in `_meta.yaml` / `config.json`.

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
