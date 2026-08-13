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
PY=""
for cand in \\
  "${PROJECT_ROOT}/.venv/bin/python" \\
  "${PROJECT_ROOT}/venv/bin/python"
do
  if [[ -x "$cand" ]]; then PY="$cand"; break; fi
done
if [[ -z "$PY" ]]; then PY="python3"; fi
export PYTHONPATH="${PULSE_HOME}/tools${PYTHONPATH:+:$PYTHONPATH}"
exec "$PY" "${PULSE_HOME}/tools/pulse-cli/__main__.py" "$@"
'''


def _meta_yaml(project: str, tag_prefix: str) -> str:
    return f"""version: 1
project: {project}
tag_prefix: {tag_prefix}
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

Optional agent rules: `.pulse/cursor/` (Cursor) and `.pulse/github/` (GitHub Copilot) — link with:

```bash
pulse cursor link
pulse github link
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


def _infer_project_name(root: Path) -> str:
    name = root.resolve().name.strip() or "project"
    return name


def _infer_tag_prefix(project: str) -> str:
    raw = "".join(ch if ch.isalnum() else "_" for ch in project.upper())
    raw = "_".join(p for p in raw.split("_") if p)
    return raw or "APP"


def init_project(
    target: Path,
    *,
    project: str | None = None,
    tag_prefix: str | None = None,
    force: bool = False,
    with_venv: bool = True,
    generate: bool = True,
) -> None:
    if not EMBED_ROOT.is_dir():
        _die(f"embed templates missing at {EMBED_ROOT}")

    project_root = target.expanduser().resolve()
    project_root.mkdir(parents=True, exist_ok=True)
    pulse = project_root / ".pulse"

    project = project or _infer_project_name(project_root)
    tag_prefix = tag_prefix or _infer_tag_prefix(project)

    # Engine
    _copytree(EMBED_ROOT / "tools", pulse / "tools", force=force)

    # Host plugins
    plugins_src = EMBED_ROOT / "tools" / "pulse_plugins"
    if plugins_src.is_dir():
        _copytree(plugins_src, pulse / "plugins", force=force)
    (pulse / "plugins").mkdir(parents=True, exist_ok=True)

    # Agent templates (NOT installed into .cursor / .github unless user links)
    if (EMBED_ROOT / ".cursor").is_dir():
        _copytree(EMBED_ROOT / ".cursor", pulse / "cursor", force=force)
    if (EMBED_ROOT / ".github").is_dir():
        _copytree(EMBED_ROOT / ".github", pulse / "github", force=force)

    # Bin
    bin_pulse = pulse / "bin" / "pulse"
    if _write_text(bin_pulse, _bin_pulse(), force=force):
        bin_pulse.chmod(bin_pulse.stat().st_mode | 0o111)

    # Cards + views stubs
    features = pulse / "features"
    features.mkdir(parents=True, exist_ok=True)
    (pulse / "cleancode").mkdir(parents=True, exist_ok=True)
    _write_text(features / "_meta.yaml", _meta_yaml(project, tag_prefix), force=force)
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

    if with_venv:
        ensure_project_venv(project_root)

    if generate:
        _run_project_generate(project_root)

    print(f"pulse init → {pulse}")
    print(f"  project={project}  tag_prefix={tag_prefix}")
    print("  optional: pulse cursor link · pulse github link")


def _run_project_generate(project_root: Path) -> None:
    """Best-effort ``generate`` after init so BOARD.md exists immediately."""
    script = project_root / ".pulse" / "bin" / "pulse"
    if not script.is_file():
        return
    env = {
        **os.environ,
        "PULSE_ROOT": str(project_root),
        "PULSE_HOME": str(project_root / ".pulse"),
        "PYTHONPATH": str(project_root / ".pulse" / "tools"),
    }
    py = project_root / ".venv" / "bin" / "python"
    if not py.is_file():
        py = Path(sys.executable)
    try:
        subprocess.check_call(
            [str(py), str(project_root / ".pulse" / "tools" / "pulse-cli" / "__main__.py"), "generate"],
            cwd=str(project_root),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        print("pulse: hint — run `.pulse/bin/pulse generate` once deps are ready", file=sys.stderr)


GIT_REPO = "https://github.com/Ngoctrong102/pulse.git"
PIP_SPEC = f"git+{GIT_REPO}"
# Layout created by install.sh (curl | bash)
_DEFAULT_CURL_PREFIX = Path(
    os.environ.get("PULSE_HOME")
    or (Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")) / "pulse")
)


def _curl_install_meta() -> dict[str, Any] | None:
    meta_path = _DEFAULT_CURL_PREFIX / "install-meta.json"
    if not meta_path.is_file():
        # Also detect if we are running from the curl venv without meta (older).
        try:
            exe = Path(sys.executable).resolve()
        except OSError:
            return None
        marker = Path.home() / ".local" / "share" / "pulse" / "venv"
        if marker.is_dir() and str(marker) in str(exe):
            return {
                "prefix": str(marker.parent),
                "bin_dir": str(Path.home() / ".local" / "bin"),
                "shim": str(Path.home() / ".local" / "bin" / "pulse"),
            }
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _pip_install_latest() -> None:
    print(f"pulse upgrade: installing latest from {GIT_REPO} …")
    rc = subprocess.call(
        [sys.executable, "-m", "pip", "install", "-U", PIP_SPEC],
    )
    if rc != 0:
        _die("pip install failed — fix network/permissions, then retry `pulse upgrade`")


def _pip_uninstall() -> None:
    """Remove the pulse package; if installed via install.sh, drop venv + shim too."""
    meta = _curl_install_meta()
    print("pulse uninstall: removing package …")
    rc = subprocess.call(
        [sys.executable, "-m", "pip", "uninstall", "-y", "pulse"],
    )
    if rc != 0:
        # Still try to wipe curl layout if present
        if meta is None:
            _die("pip uninstall failed")

    if meta:
        prefix = Path(str(meta.get("prefix") or _DEFAULT_CURL_PREFIX))
        shim = Path(str(meta.get("shim") or (Path.home() / ".local" / "bin" / "pulse")))
        if shim.is_symlink() or shim.is_file():
            try:
                # Only remove shim if it points at our venv
                target = shim.resolve() if shim.is_symlink() else shim
                venv_bin = prefix / "venv" / "bin" / "pulse"
                if target == venv_bin.resolve() or str(prefix / "venv") in str(target):
                    shim.unlink()
                    print(f"  removed shim {shim}")
            except OSError:
                pass
        if prefix.is_dir() and (prefix / "venv").is_dir():
            shutil.rmtree(prefix, ignore_errors=True)
            print(f"  removed {prefix}")

    print("Done. Project `.pulse/` folders were left alone (your cards stay).")


def ensure_project_venv(project_root: Path) -> Path | None:
    """Create ``project/.venv`` if missing and install ``.pulse/requirements.txt``.

    Returns the venv python path, or None if skipped/failed soft.
    """
    project_root = project_root.resolve()
    venv = project_root / ".venv"
    py = venv / "bin" / "python"
    req = project_root / ".pulse" / "requirements.txt"
    try:
        if not py.is_file():
            print("pulse: creating project .venv …")
            subprocess.check_call(
                [sys.executable, "-m", "venv", str(venv)],
                stdout=subprocess.DEVNULL,
            )
        if req.is_file():
            print("pulse: installing .pulse/requirements.txt into .venv …")
            subprocess.check_call(
                [str(py), "-m", "pip", "install", "-q", "-U", "pip"],
                stdout=subprocess.DEVNULL,
            )
            subprocess.check_call(
                [str(py), "-m", "pip", "install", "-q", "-r", str(req)],
            )
        return py if py.is_file() else None
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"pulse: warning — could not prepare .venv ({exc})", file=sys.stderr)
        print("  Install deps later: python3 -m venv .venv && .venv/bin/pip install -r .pulse/requirements.txt", file=sys.stderr)
        return None


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
    if (EMBED_ROOT / ".github").is_dir():
        _copytree(EMBED_ROOT / ".github", pulse / "github", force=True)

    bin_pulse = pulse / "bin" / "pulse"
    bin_pulse.parent.mkdir(parents=True, exist_ok=True)
    bin_pulse.write_text(_bin_pulse(), encoding="utf-8")
    bin_pulse.chmod(bin_pulse.stat().st_mode | 0o111)

    _write_version_stamp(pulse)
    _bump_meta_pulse_version(pulse / "features" / "_meta.yaml")

    print(f"pulse upgrade → synced {pulse} to kit {__version__}")
    print("  preserved: features/, cleancode/, plugins/, generated views")


def find_pulse_project(start: Path | None = None) -> Path | None:
    """Nearest directory that contains ``.pulse/`` walking from *start* (cwd by default)."""
    cur = (start or Path.cwd()).expanduser().resolve()
    for cand in [cur, *cur.parents]:
        if (cand / ".pulse").is_dir():
            return cand
    return None


def upgrade_cmd(*, fetch: bool = True) -> None:
    """Upgrade the CLI from GitHub, then sync the nearest project ``.pulse/``.

    User-facing: just run ``pulse upgrade`` (no URL, no path).
    """
    if fetch and os.environ.get("PULSE_NO_FETCH") != "1":
        _pip_install_latest()
        # Re-enter with the freshly installed package (this process still has old code).
        # Keep cwd so project discovery still works.
        rc = subprocess.call([sys.executable, "-m", "pulse", "upgrade", "--no-fetch"])
        if rc != 0:
            raise SystemExit(rc)
        return

    root = find_pulse_project()
    if root is not None:
        upgrade_project(root)
        return
    print(
        f"pulse upgrade: CLI is {__version__} "
        "(no .pulse/ near this directory — only the package was updated)"
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


_PULSE_GH_BEGIN = "<!-- pulse:begin -->"
_PULSE_GH_END = "<!-- pulse:end -->"
_PULSE_GH_OWNED = (
    "instructions/pulse-features.instructions.md",
    "instructions/pulse-quality.instructions.md",
    "pulse-quality-raise.md",
)


def _merge_marked_block(existing: str, block: str) -> str:
    """Insert or replace a <!-- pulse:begin -->…<!-- pulse:end --> section."""
    block = block.strip()
    if _PULSE_GH_BEGIN not in block:
        block = f"{_PULSE_GH_BEGIN}\n{block}\n{_PULSE_GH_END}"
    if _PULSE_GH_BEGIN in existing and _PULSE_GH_END in existing:
        start = existing.index(_PULSE_GH_BEGIN)
        end = existing.index(_PULSE_GH_END) + len(_PULSE_GH_END)
        return (existing[:start].rstrip() + "\n\n" + block + "\n\n" + existing[end:].lstrip()).strip() + "\n"
    if existing.strip():
        return existing.rstrip() + "\n\n" + block + "\n"
    return block + "\n"


def _strip_marked_block(existing: str) -> str:
    if _PULSE_GH_BEGIN not in existing or _PULSE_GH_END not in existing:
        return existing
    start = existing.index(_PULSE_GH_BEGIN)
    end = existing.index(_PULSE_GH_END) + len(_PULSE_GH_END)
    return (existing[:start].rstrip() + "\n\n" + existing[end:].lstrip()).strip() + (
        "\n" if existing.endswith("\n") or existing[end:].strip() else ""
    )


def github_link(project_root: Path, *, force: bool) -> None:
    """Opt-in: install GitHub Copilot instructions from ``.pulse/github``."""
    project_root = project_root.expanduser().resolve()
    src = project_root / ".pulse" / "github"
    if not src.is_dir():
        _die("missing .pulse/github — run `pulse init` (or `pulse upgrade`) first")
    dst = project_root / ".github"
    dst.mkdir(parents=True, exist_ok=True)

    # Path-specific instructions + rubric appendix
    for rel in (
        "instructions/pulse-features.instructions.md",
        "instructions/pulse-quality.instructions.md",
    ):
        s = src / rel
        if not s.is_file():
            continue
        t = dst / rel
        if t.exists() and not force:
            continue
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, t)

    rubric_src = src / "quality-raise.md"
    if rubric_src.is_file():
        rubric_dst = dst / "pulse-quality-raise.md"
        if force or not rubric_dst.exists():
            shutil.copy2(rubric_src, rubric_dst)

    # Repo-wide Copilot instructions — merge marked block so host text survives
    instr_src = src / "copilot-instructions.md"
    if instr_src.is_file():
        block = instr_src.read_text(encoding="utf-8")
        instr_dst = dst / "copilot-instructions.md"
        if instr_dst.is_file() and not force:
            merged = _merge_marked_block(instr_dst.read_text(encoding="utf-8"), block)
        elif instr_dst.is_file() and force:
            merged = _merge_marked_block(instr_dst.read_text(encoding="utf-8"), block)
        else:
            merged = block if block.endswith("\n") else block + "\n"
            if _PULSE_GH_BEGIN not in merged:
                merged = f"{_PULSE_GH_BEGIN}\n{merged.rstrip()}\n{_PULSE_GH_END}\n"
        instr_dst.write_text(merged, encoding="utf-8")

    print(f"pulse github link → {dst}")
    print("  Copilot instructions installed. Re-run with --force to refresh pulse sections.")


def github_unlink(project_root: Path) -> None:
    """Remove pulse-owned GitHub Copilot instruction files / marked blocks."""
    project_root = project_root.expanduser().resolve()
    dst = project_root / ".github"
    if not dst.is_dir():
        print("pulse github unlink: no .github/ — nothing to do")
        return

    instr = dst / "copilot-instructions.md"
    if instr.is_file():
        text = instr.read_text(encoding="utf-8")
        stripped = _strip_marked_block(text).strip()
        if stripped and stripped != text.strip():
            instr.write_text(stripped + "\n", encoding="utf-8")
            print(f"  stripped pulse block from {instr}")
        elif _PULSE_GH_BEGIN in text:
            # File was only pulse content
            only_pulse = _strip_marked_block(text).strip() == ""
            if only_pulse:
                instr.unlink()
                print(f"  removed {instr}")
            else:
                instr.write_text(stripped + "\n" if stripped else "", encoding="utf-8")

    for rel in _PULSE_GH_OWNED:
        path = dst / rel
        if path.is_file():
            path.unlink()
            print(f"  removed {path}")

    print(f"pulse github unlink → {dst}")


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
        "github",
        "copilot",
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

    init = sub.add_parser("init", help="Init .pulse/ in the current project (infers name)")
    init.add_argument(
        "path",
        nargs="?",
        default=".",
        help=argparse.SUPPRESS,  # power users / tests — normal flow is just `pulse init`
    )
    init.add_argument("--project", default=None, help=argparse.SUPPRESS)
    init.add_argument("--tag-prefix", default=None, help=argparse.SUPPRESS)
    init.add_argument("--force", action="store_true", help=argparse.SUPPRESS)
    init.add_argument("--no-venv", action="store_true", help=argparse.SUPPRESS)
    init.add_argument("--no-generate", action="store_true", help=argparse.SUPPRESS)

    up = sub.add_parser(
        "upgrade",
        aliases=["update"],
        help="Upgrade pulse (from GitHub) and sync .pulse/ in the current project",
    )
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

    gh = sub.add_parser(
        "github",
        aliases=["copilot"],
        help="Optional GitHub Copilot integration",
    )
    gh_sub = gh.add_subparsers(dest="github_cmd", required=True)
    gh_link = gh_sub.add_parser("link", help="Install Copilot instructions into .github/")
    gh_link.add_argument("path", nargs="?", default=".")
    gh_link.add_argument("--force", action="store_true")
    gh_unlink = gh_sub.add_parser("unlink", help="Remove pulse-owned Copilot instruction files")
    gh_unlink.add_argument("path", nargs="?", default=".")

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
    if args.cmd in {"github", "copilot"} and getattr(args, "github_cmd", None) == "link":
        github_link(Path(args.path), force=bool(args.force))
        return 0
    if args.cmd in {"github", "copilot"} and getattr(args, "github_cmd", None) == "unlink":
        github_unlink(Path(args.path))
        return 0
    if args.cmd in {"update", "upgrade"}:
        upgrade_cmd(fetch=not bool(getattr(args, "no_fetch", False)))
        return 0
    if args.cmd == "uninstall":
        _pip_uninstall()
        return 0
    if args.cmd == "init":
        target = Path(args.path)
        init_project(
            target,
            project=args.project,  # may be None → inferred
            tag_prefix=args.tag_prefix,
            force=bool(args.force),
            with_venv=not bool(getattr(args, "no_venv", False)),
            generate=not bool(getattr(args, "no_generate", False)),
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
