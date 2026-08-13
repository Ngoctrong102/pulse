#!/usr/bin/env python3
"""pulse — install a self-contained ``.pulse/`` workspace into a project.

Does not modify the host project's architecture, docs layout, or ``.gitignore``.
Optional agent rules stay under ``.pulse/cursor/`` until the user runs
``pulse cursor link``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parents[1]
EMBED_ROOT = KIT_ROOT / "embed"
__version__ = "0.4.0"


def _die(msg: str, code: int = 1) -> None:
    print(f"pulse: {msg}", file=sys.stderr)
    raise SystemExit(code)


def _copytree(src: Path, dst: Path, *, force: bool) -> None:
    if not src.exists():
        return
    for path in src.rglob("*"):
        if path.is_dir():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        # Host plugins live at .pulse/plugins, not tools/pulse_plugins
        rel = path.relative_to(src)
        if rel.parts[:1] == ("pulse_plugins",):
            continue
        target = dst / rel
        if target.exists() and not force:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def _write_text(path: Path, text: str, *, force: bool) -> bool:
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def _bin_pulse() -> str:
    return '''#!/usr/bin/env bash
set -euo pipefail
PULSE_HOME="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT_ROOT="$(cd "$PULSE_HOME/.." && pwd)"
export PULSE_HOME PROJECT_ROOT
export PULSE_ROOT="$PROJECT_ROOT"
PY="${PROJECT_ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then PY="python3"; fi
export PYTHONPATH="${PULSE_HOME}/tools${PYTHONPATH:+:$PYTHONPATH}"
exec "$PY" "${PULSE_HOME}/tools/pulse-cli/__main__.py" "$@"
'''


def _meta_yaml(project: str, tag_prefix: str, code_roots: list[str]) -> str:
    roots = ", ".join(f'"{r}"' for r in code_roots)
    return f"""version: 1
project: {project}
tag_prefix: {tag_prefix}
code_roots: [{roots}]
speckit: false
updated: '1970-01-01'
focus_id: null
plugins:
  # omit enabled → load all discovered plugins
  disabled: []
"""


def _sample_feature(project: str) -> str:
    return f"""id: getting-started
type: feature
name: Getting started with pulse
phase: 0
status: partial
percent: 10
priority: 1
roi: 10
mvp: true
docs: {{}}
specs: []
mocks: []
done:
- pulse init (.pulse/ workspace) into {project}
remaining:
- Add real feature cards with .pulse/bin/pulse new
- Set code_roots in .pulse/features/_meta.yaml to your folders
- Try .pulse/bin/pulse next --prompt
evidence:
  paths_any: []
"""


def _readme(project: str) -> str:
    return f"""# {project} — pulse workspace

This folder is the **project operating system** workspace. It does not prescribe
your product architecture — only cards, views, and tools live here.

```bash
.pulse/bin/pulse validate
.pulse/bin/pulse next --prompt
.pulse/bin/pulse explain
.pulse/bin/pulse generate
.pulse/bin/pulse mismatch detect
```

Optional agent rules: `.pulse/cursor/` — link into Cursor with:

```bash
pulse cursor link
```

Commit `.pulse/` if the team should share status (pulse never auto-edits `.gitignore`).
"""


def init_project(
    target: Path,
    *,
    project: str,
    tag_prefix: str,
    code_roots: list[str],
    force: bool,
) -> None:
    if not EMBED_ROOT.is_dir():
        _die(f"embed templates missing at {EMBED_ROOT}")

    project_root = target.expanduser().resolve()
    project_root.mkdir(parents=True, exist_ok=True)
    pulse = project_root / ".pulse"

    # Engine
    _copytree(EMBED_ROOT / "tools", pulse / "tools", force=force)

    # Host plugins
    plugins_src = EMBED_ROOT / "tools" / "pulse_plugins"
    if plugins_src.is_dir():
        _copytree(plugins_src, pulse / "plugins", force=force)
    (pulse / "plugins").mkdir(parents=True, exist_ok=True)

    # Agent templates (NOT installed into .cursor unless user links)
    if (EMBED_ROOT / ".cursor").is_dir():
        _copytree(EMBED_ROOT / ".cursor", pulse / "cursor", force=force)

    # Bin
    bin_pulse = pulse / "bin" / "pulse"
    if _write_text(bin_pulse, _bin_pulse(), force=force):
        bin_pulse.chmod(bin_pulse.stat().st_mode | 0o111)

    # Cards + views stubs
    features = pulse / "features"
    features.mkdir(parents=True, exist_ok=True)
    (pulse / "cleancode").mkdir(parents=True, exist_ok=True)
    _write_text(features / "_meta.yaml", _meta_yaml(project, tag_prefix, code_roots), force=force)
    _write_text(features / "getting-started.yaml", _sample_feature(project), force=force)
    _write_text(pulse / "README.md", _readme(project), force=force)
    _write_text(
        pulse / "implementation-phases.md",
        f"# Implementation phases — {project}\n\n<!-- STATUS:BEGIN -->\n_Run .pulse/bin/pulse generate._\n<!-- STATUS:END -->\n",
        force=force,
    )
    _write_text(pulse / "tech-debt.md", "# Tech Debt\n\n<!-- generated by pulse -->\n", force=force)
    _write_text(pulse / "clean-code.md", "# Clean-Code Scoreboard\n\n<!-- generated by pulse -->\n", force=force)
    _write_text(pulse / "requirements.txt", "PyYAML>=6.0\n", force=force)

    (pulse / "config.json").write_text(
        json.dumps(
            {
                "version": 1,
                "project": project,
                "tag_prefix": tag_prefix,
                "code_roots": code_roots,
                "pulse_version": __version__,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"pulse init → {pulse}")
    print(f"  project_root={project_root}")
    print(f"  project={project}  tag_prefix={tag_prefix}  code_roots={code_roots}")
    print("  (only .pulse/ was written — no other project files touched)")
    print("  next:")
    print("    pip install -r .pulse/requirements.txt")
    print("    .pulse/bin/pulse generate")
    print("    .pulse/bin/pulse next --prompt")
    print("    pulse cursor link   # optional: install agent rules into .cursor/")


def cursor_link(project_root: Path, *, force: bool) -> None:
    """Opt-in: copy ``.pulse/cursor`` templates into the project's ``.cursor``."""
    project_root = project_root.expanduser().resolve()
    src = project_root / ".pulse" / "cursor"
    if not src.is_dir():
        _die("missing .pulse/cursor — run `pulse init` first")
    dst = project_root / ".cursor"
    # Copy rules/skills/hooks; merge hooks.json carefully
    for sub in ("rules", "skills", "hooks"):
        s = src / sub
        if s.is_dir():
            _copytree(s, dst / sub, force=force)
    hooks_src = src / "hooks.json"
    hooks_dst = dst / "hooks.json"
    if hooks_src.is_file() and (force or not hooks_dst.exists()):
        # Point hook command at .pulse copy if present
        text = hooks_src.read_text(encoding="utf-8")
        text = text.replace(
            ".cursor/hooks/status-sync-stop.sh",
            ".cursor/hooks/status-sync-stop.sh",
        )
        hooks_dst.parent.mkdir(parents=True, exist_ok=True)
        hooks_dst.write_text(text, encoding="utf-8")
    print(f"pulse cursor link → {dst}")
    print("  Agent rules/skills/hooks installed. Re-run with --force to refresh.")


def _find_bin_pulse(start: Path) -> Path | None:
    for cand in [start, *start.parents]:
        script = cand / ".pulse" / "bin" / "pulse"
        if script.is_file():
            return script
    return None


def _run_vendored(argv: list[str]) -> int:
    start = Path(os.environ.get("PULSE_ROOT") or Path.cwd()).resolve()
    script = _find_bin_pulse(start)
    if script is None:
        _die("no .pulse/bin/pulse found — run `pulse init` in the project first")
    project = script.resolve().parents[2]  # .pulse/bin/pulse → project
    os.environ["PULSE_ROOT"] = str(project)
    os.environ["PULSE_HOME"] = str(script.resolve().parents[1])
    os.execv(str(script), [str(script), *argv])
    return 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    known = {"init", "run", "version", "cursor", "-h", "--help"}
    if argv and argv[0] not in known and not argv[0].startswith("-"):
        return _run_vendored(argv)

    p = argparse.ArgumentParser(
        prog="pulse",
        description="Project operating system — self-contained .pulse/ workspace.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    init = sub.add_parser("init", help="Create only <project>/.pulse/ (touches nothing else)")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--project", default=None)
    init.add_argument("--tag-prefix", default=None)
    init.add_argument(
        "--code-roots",
        default="src",
        help="Product code folders relative to project root (default: src)",
    )
    init.add_argument("--force", action="store_true")

    cur = sub.add_parser("cursor", help="Optional Cursor agent integration")
    cur_sub = cur.add_subparsers(dest="cursor_cmd", required=True)
    link = cur_sub.add_parser("link", help="Copy .pulse/cursor templates into .cursor/")
    link.add_argument("path", nargs="?", default=".")
    link.add_argument("--force", action="store_true")

    run = sub.add_parser("run", help="Forward to .pulse/bin/pulse")
    run.add_argument("args", nargs=argparse.REMAINDER)

    sub.add_parser("version")

    args = p.parse_args(argv)
    if args.cmd == "version":
        print(__version__)
        return 0
    if args.cmd == "run":
        fwd = list(args.args)
        if fwd and fwd[0] == "--":
            fwd = fwd[1:]
        return _run_vendored(fwd)
    if args.cmd == "cursor" and args.cursor_cmd == "link":
        cursor_link(Path(args.path), force=bool(args.force))
        return 0
    if args.cmd == "init":
        target = Path(args.path)
        project = args.project or target.expanduser().resolve().name
        tag_prefix = (args.tag_prefix or project).upper().replace(" ", "")
        code_roots = [x.strip() for x in str(args.code_roots).split(",") if x.strip()]
        init_project(
            target,
            project=project,
            tag_prefix=tag_prefix,
            code_roots=code_roots,
            force=bool(args.force),
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
