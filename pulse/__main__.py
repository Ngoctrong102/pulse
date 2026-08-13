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
import subprocess
import sys
from pathlib import Path
from typing import Any

from pulse import __version__

# Templates ship inside the installed package (``pulse/embed``). Dev checkouts
# use the same layout.
EMBED_ROOT = Path(__file__).resolve().parent / "embed"

# Marker key in host hooks.json entries owned by pulse (safe unlink).
_PULSE_HOOK_ID = "pulse-status-sync"


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
pulse_version: {__version__}
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

**Agents:** edit cards under `.pulse/features/` (and `.pulse/cleancode/`), not vendored
`.pulse/tools/` — refresh the engine with `pulse upgrade` from the kit.
"""


def _write_version_stamp(pulse: Path, *, project: str | None = None) -> None:
    """Kit version stamp only — SoT for project settings remains ``_meta.yaml``."""
    payload: dict[str, Any] = {
        "version": 1,
        "pulse_version": __version__,
    }
    if project:
        payload["project"] = project
    (pulse / "config.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def _bump_meta_pulse_version(meta_path: Path) -> None:
    if not meta_path.is_file():
        return
    try:
        import yaml
    except ImportError:
        return
    data = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return
    if data.get("pulse_version") == __version__:
        return
    data["pulse_version"] = __version__
    meta_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


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
    _write_version_stamp(pulse, project=project)

    print(f"pulse init → {pulse}")
    print(f"  project_root={project_root}")
    print(f"  project={project}  tag_prefix={tag_prefix}  code_roots={code_roots}")
    print("  (only .pulse/ was written — no other project files touched)")
    print("  next:")
    print("    pip install -r .pulse/requirements.txt")
    print("    .pulse/bin/pulse generate")
    print("    .pulse/bin/pulse next --prompt")
    print("    pulse cursor link   # optional: install agent rules into .cursor/")


GIT_REPO = "https://github.com/Ngoctrong102/pulse.git"
PIP_SPEC = f"git+{GIT_REPO}"


def _pip_install_latest() -> None:
    print(f"pulse update: installing latest from {GIT_REPO} …")
    rc = subprocess.call(
        [sys.executable, "-m", "pip", "install", "-U", PIP_SPEC],
    )
    if rc != 0:
        _die("pip install failed — fix network/permissions, then retry `pulse update`")


def _pip_uninstall() -> None:
    print("pulse uninstall: removing package …")
    rc = subprocess.call(
        [sys.executable, "-m", "pip", "uninstall", "-y", "pulse"],
    )
    if rc != 0:
        _die("pip uninstall failed")
    print("Done. Project `.pulse/` folders were left alone (your cards stay).")


def upgrade_project(target: Path) -> None:
    """Refresh vendored ``.pulse/tools`` (+ cursor templates + bin) from this kit.

    Preserves host SoT: ``features/``, ``cleancode/``, ``plugins/``, generated views.
    """
    if not EMBED_ROOT.is_dir():
        _die(f"embed templates missing at {EMBED_ROOT}")

    project_root = target.expanduser().resolve()
    pulse = project_root / ".pulse"
    if not pulse.is_dir():
        _die("no .pulse/ — run `pulse init` first")

    _copytree(EMBED_ROOT / "tools", pulse / "tools", force=True)
    if (EMBED_ROOT / ".cursor").is_dir():
        _copytree(EMBED_ROOT / ".cursor", pulse / "cursor", force=True)

    bin_pulse = pulse / "bin" / "pulse"
    bin_pulse.parent.mkdir(parents=True, exist_ok=True)
    bin_pulse.write_text(_bin_pulse(), encoding="utf-8")
    bin_pulse.chmod(bin_pulse.stat().st_mode | 0o111)

    _write_version_stamp(pulse)
    _bump_meta_pulse_version(pulse / "features" / "_meta.yaml")

    print(f"pulse update → synced {pulse} to kit {__version__}")
    print("  preserved: features/, cleancode/, plugins/, generated views")


def update_cmd(target: Path, *, fetch: bool = True) -> None:
    """Install latest kit from GitHub, then sync ``.pulse/`` in the project (if any)."""
    project_root = target.expanduser().resolve()
    if fetch and os.environ.get("PULSE_NO_FETCH") != "1":
        _pip_install_latest()
        # Re-enter with the freshly installed package (this process still has old code).
        rc = subprocess.call(
            [
                sys.executable,
                "-m",
                "pulse",
                "update",
                str(project_root),
                "--no-fetch",
            ]
        )
        if rc != 0:
            raise SystemExit(rc)
        return

    pulse = project_root / ".pulse"
    if pulse.is_dir():
        upgrade_project(project_root)
        return
    print(
        f"pulse update: package is current ({__version__}); "
        "no .pulse/ here — run inside a project (or `pulse init`) to sync tools."
    )


def _default_hooks_json() -> dict[str, Any]:
    return {
        "version": 1,
        "hooks": {
            "stop": [
                {
                    "command": ".cursor/hooks/status-sync-stop.sh",
                    "pulse_id": _PULSE_HOOK_ID,
                }
            ]
        },
    }


def _merge_hooks(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge pulse hook entries into host hooks.json without wiping other hooks."""
    out = dict(existing) if isinstance(existing, dict) else {}
    if "version" not in out and "version" in incoming:
        out["version"] = incoming["version"]
    hooks_out: dict[str, Any] = dict(out.get("hooks") or {}) if isinstance(out.get("hooks"), dict) else {}
    hooks_in = incoming.get("hooks") if isinstance(incoming.get("hooks"), dict) else {}
    for event, entries in hooks_in.items():
        if not isinstance(entries, list):
            continue
        cur = list(hooks_out.get(event) or []) if isinstance(hooks_out.get(event), list) else []
        # Drop previous pulse-owned entries for this event, then append incoming.
        kept = [
            e
            for e in cur
            if not (isinstance(e, dict) and e.get("pulse_id") == _PULSE_HOOK_ID)
        ]
        for e in entries:
            if isinstance(e, dict):
                kept.append(dict(e))
            else:
                kept.append(e)
        hooks_out[event] = kept
    out["hooks"] = hooks_out
    return out


def _strip_pulse_hooks(existing: dict[str, Any]) -> dict[str, Any]:
    out = dict(existing)
    hooks = out.get("hooks")
    if not isinstance(hooks, dict):
        return out
    new_hooks: dict[str, Any] = {}
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            new_hooks[event] = entries
            continue
        filtered = [
            e
            for e in entries
            if not (isinstance(e, dict) and e.get("pulse_id") == _PULSE_HOOK_ID)
        ]
        if filtered:
            new_hooks[event] = filtered
    out["hooks"] = new_hooks
    return out


def cursor_link(project_root: Path, *, force: bool) -> None:
    """Opt-in: copy ``.pulse/cursor`` templates into the project's ``.cursor``."""
    project_root = project_root.expanduser().resolve()
    src = project_root / ".pulse" / "cursor"
    if not src.is_dir():
        _die("missing .pulse/cursor — run `pulse init` first")
    dst = project_root / ".cursor"
    for sub in ("rules", "skills", "hooks"):
        s = src / sub
        if s.is_dir():
            _copytree(s, dst / sub, force=force)

    hooks_src = src / "hooks.json"
    hooks_dst = dst / "hooks.json"
    if hooks_src.is_file():
        incoming: dict[str, Any] = json.loads(hooks_src.read_text(encoding="utf-8"))
    else:
        incoming = _default_hooks_json()
    if not isinstance(incoming, dict):
        incoming = _default_hooks_json()
    stop = ((incoming.get("hooks") or {}).get("stop")) if isinstance(incoming.get("hooks"), dict) else None
    if isinstance(stop, list):
        for e in stop:
            if isinstance(e, dict) and "pulse_id" not in e:
                e["pulse_id"] = _PULSE_HOOK_ID

    if hooks_dst.is_file():
        try:
            existing = json.loads(hooks_dst.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
        if not isinstance(existing, dict):
            existing = {}
        merged = _merge_hooks(existing, incoming)
    else:
        merged = incoming

    hooks_dst.parent.mkdir(parents=True, exist_ok=True)
    hooks_dst.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    print(f"pulse cursor link → {dst}")
    print("  Agent rules/skills/hooks installed (hooks.json merged). Re-run with --force to refresh files.")


def cursor_unlink(project_root: Path) -> None:
    """Remove pulse-owned Cursor hook entries; leave other hooks and files alone."""
    project_root = project_root.expanduser().resolve()
    hooks_dst = project_root / ".cursor" / "hooks.json"
    if not hooks_dst.is_file():
        print("pulse cursor unlink: no .cursor/hooks.json — nothing to do")
        return
    try:
        existing = json.loads(hooks_dst.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        _die("corrupt .cursor/hooks.json")
    if not isinstance(existing, dict):
        _die("corrupt .cursor/hooks.json")
    stripped = _strip_pulse_hooks(existing)
    hooks_dst.write_text(json.dumps(stripped, indent=2) + "\n", encoding="utf-8")
    print(f"pulse cursor unlink → removed pulse hooks from {hooks_dst}")
    print("  (rules/skills/hook scripts left in place — delete manually if desired)")


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
    known = {
        "init",
        "update",
        "upgrade",
        "uninstall",
        "run",
        "version",
        "cursor",
        "-h",
        "--help",
    }
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

    up = sub.add_parser(
        "update",
        aliases=["upgrade"],
        help="Install latest pulse from GitHub, then sync .pulse/ in this project",
    )
    up.add_argument("path", nargs="?", default=".")
    up.add_argument(
        "--no-fetch",
        action="store_true",
        help=argparse.SUPPRESS,  # internal: skip pip (used after self-update / tests)
    )

    sub.add_parser("uninstall", help="Uninstall the pulse package (keeps project .pulse/ cards)")

    cur = sub.add_parser("cursor", help="Optional Cursor agent integration")
    cur_sub = cur.add_subparsers(dest="cursor_cmd", required=True)
    link = cur_sub.add_parser("link", help="Copy .pulse/cursor templates into .cursor/")
    link.add_argument("path", nargs="?", default=".")
    link.add_argument("--force", action="store_true")
    unlink = cur_sub.add_parser("unlink", help="Remove pulse-owned entries from .cursor/hooks.json")
    unlink.add_argument("path", nargs="?", default=".")

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
    if args.cmd == "cursor" and args.cursor_cmd == "unlink":
        cursor_unlink(Path(args.path))
        return 0
    if args.cmd in {"update", "upgrade"}:
        update_cmd(Path(args.path), fetch=not bool(getattr(args, "no_fetch", False)))
        return 0
    if args.cmd == "uninstall":
        _pip_uninstall()
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
