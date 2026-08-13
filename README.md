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

## Install / update / uninstall

Recommended (isolated CLI — works even without a system Python):

```bash
curl -fsSL https://raw.githubusercontent.com/Ngoctrong102/pulse/main/install.sh | bash
```

What it does:

1. Use Python **≥ 3.11** if already on the machine
2. Otherwise install **uv**, let uv fetch Python, then install pulse into `~/.local/share/pulse/venv`
3. Put a shim at `~/.local/bin/pulse` (add that dir to `PATH` if needed)

Needs only `curl` (+ network). No project `.venv` required for the CLI itself.

```bash
pulse upgrade                # that's it — pulls latest + syncs nearest .pulse/
pulse uninstall              # remove the CLI install (project cards stay)
```

## Quick start

```bash
pulse init /path/to/your/project \
  --project MyApp --tag-prefix MYAPP --code-roots src
# creates .pulse/ and a project .venv with PyYAML

cd /path/to/your/project
.pulse/bin/pulse generate
.pulse/bin/pulse next --prompt
```

Optional agent rules (only when you ask):

```bash
pulse cursor link            # Cursor rules / skills / hooks
pulse cursor unlink

pulse github link            # GitHub Copilot instructions (.github/)
pulse github unlink
# alias: pulse copilot link
```

## Layout after init

```
your-project/
  .venv/                  ← created by init (engine deps)
  .pulse/                 ← only pulse workspace
    features/             cards + _meta.yaml
    tools/                engine
    plugins/              host plugins
    bin/pulse             CLI
    cursor/               Cursor rule templates (opt-in link)
    github/               Copilot instruction templates (opt-in link)
    BOARD.md …
  src/ …                  ← your code, untouched
```

`code_roots` in `.pulse/features/_meta.yaml` point at **your** product folders (relative to project root).

Derived views under `.pulse/` (`BOARD.md`, `DRIFT.md`, reports) are summaries — prefer `next --prompt` in chat. Agents edit **cards**, not `.pulse/tools/` (`pulse upgrade` refreshes the engine).

## Docs

- [`docs/VISION.md`](docs/VISION.md)
- [`docs/PLUGINS.md`](docs/PLUGINS.md)
- [`docs/FEATURES.md`](docs/FEATURES.md)
- [`docs/SCHEMA.md`](docs/SCHEMA.md)
