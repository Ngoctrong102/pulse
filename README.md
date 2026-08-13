# pulse

A **project operating system** that lives entirely in `.pulse/` inside your repo.

## Install

```bash
curl -fsSL "https://raw.githubusercontent.com/Ngoctrong102/pulse/main/install.sh" | bash
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

That’s it — project name / tag prefix come from the folder. Creates `.pulse/`, runs `generate`, then asks whether to link Cursor / GitHub Copilot rules and whether to install the Pulse board extension. Does **not** create or touch a project `.venv`.

Later (switch tools, or you skipped linking at init):

```bash
pulse cursor link
pulse github link
pulse extension install   # Cursor / VS Code status board
```



## Layout

```
your-project/
  .pulse/          ← status cards, engine, board
  src/ …           ← your code + your own .venv, untouched
```



## Docs

- [`docs/VISION.md`](docs/VISION.md)
- [`docs/PLUGINS.md`](docs/PLUGINS.md)
- [`docs/FEATURES.md`](docs/FEATURES.md)
- [`docs/SCHEMA.md`](docs/SCHEMA.md)

