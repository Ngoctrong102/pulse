# pulse

A **project operating system** that lives entirely in **`.pulse/`** inside your repo.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/Ngoctrong102/pulse/main/install.sh | bash
```

```bash
pulse upgrade      # later: pull latest + sync this project
pulse uninstall    # remove the CLI (project cards stay)
```

## Use

```bash
cd your-project
pulse init
```

That’s it — project name / tag prefix come from the folder. Creates `.pulse/` + `.venv`, runs `generate`, then asks whether to link Cursor / GitHub Copilot rules.

Day-to-day (optional): ask the board what to do next, then paste into the agent:

```bash
.pulse/bin/pulse next --prompt
```

## Layout

```
your-project/
  .venv/
  .pulse/          ← status cards, engine, board
  src/ …           ← your code, untouched
```

## Docs

- [`docs/VISION.md`](docs/VISION.md)
- [`docs/PLUGINS.md`](docs/PLUGINS.md)
- [`docs/FEATURES.md`](docs/FEATURES.md)
- [`docs/SCHEMA.md`](docs/SCHEMA.md)
