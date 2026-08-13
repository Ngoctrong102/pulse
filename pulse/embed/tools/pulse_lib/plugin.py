"""Extensible plugin API for pulse.

Core stays thin (cards + validate/set/new/generate). Everything else — drift,
focus/queue, explain/next prompts, cleancode, tags, custom analytics — loads
as a plugin.

Host projects add modules under ``.pulse/plugins/``::

    # .pulse/plugins/hello.py
    from pulse_lib.plugin import Plugin, PulseApp

    class HelloPlugin(Plugin):
        name = "hello"
        def setup(self, app: PulseApp) -> None:
            def cmd(args):
                print("hello from a custom pulse plugin")
                return 0
            app.add_command("hello", help="Demo custom command", handler=cmd)

    PLUGIN = HelloPlugin()

Enable/disable via ``.pulse/features/_meta.yaml``::

    plugins:
      enabled: [drift, prompts, focus, cleancode, tags, hello]
      # omit ``enabled`` → load every discovered plugin
      disabled: []
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

import yaml

GenerateHook = Callable[[dict[str, Any]], None]
CommandHandler = Callable[[argparse.Namespace], int]


class Plugin(Protocol):
    name: str

    def setup(self, app: "PulseApp") -> None: ...


@dataclass
class CommandSpec:
    name: str
    help: str
    handler: CommandHandler
    configure: Callable[[argparse.ArgumentParser], None] | None = None
    plugin: str | None = None


@dataclass
class PulseApp:
    """Mutable registry filled by plugins during setup."""

    root: Path
    commands: list[CommandSpec] = field(default_factory=list)
    generate_hooks: list[tuple[str, GenerateHook]] = field(default_factory=list)
    loaded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def add_command(
        self,
        name: str,
        *,
        help: str,
        handler: CommandHandler,
        configure: Callable[[argparse.ArgumentParser], None] | None = None,
        plugin: str | None = None,
    ) -> None:
        self.commands.append(
            CommandSpec(
                name=name,
                help=help,
                handler=handler,
                configure=configure,
                plugin=plugin or name,
            )
        )

    def on_generate(self, hook: GenerateHook, *, plugin: str | None = None) -> None:
        self.generate_hooks.append((plugin or "?", hook))


def _meta_path(root: Path) -> Path:
    # Prefer project/.pulse/features/_meta.yaml
    pulse = root / ".pulse" / "features" / "_meta.yaml"
    if pulse.is_file():
        return pulse
    return root / "docs" / "status" / "features" / "_meta.yaml"  # legacy


def load_plugin_policy(root: Path) -> dict[str, Any]:
    path = _meta_path(root)
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError:
        return {}
    if not isinstance(data, dict):
        return {}
    plugins = data.get("plugins")
    return plugins if isinstance(plugins, dict) else {}


def is_plugin_enabled(name: str, root: Path | None = None) -> bool:
    """Whether ``name`` would load under current ``_meta.yaml`` plugin policy."""
    from pulse_lib.paths import PROJECT_ROOT

    policy = load_plugin_policy(root or PROJECT_ROOT)
    return _is_allowed(name, policy)


def _is_allowed(name: str, policy: dict[str, Any]) -> bool:
    disabled = policy.get("disabled") or []
    if isinstance(disabled, list) and name in disabled:
        return False
    enabled = policy.get("enabled")
    if enabled is None:
        return True
    if isinstance(enabled, list):
        return name in enabled
    return True


def _load_module_from_path(path: Path, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load plugin file: {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _plugin_from_module(mod: Any) -> Plugin | None:
    obj = getattr(mod, "PLUGIN", None)
    if obj is not None:
        return obj  # type: ignore[return-value]
    cls = getattr(mod, "Plugin", None)
    if cls is not None and cls is not Plugin:
        return cls()  # type: ignore[return-value]
    return None


def discover_builtin_plugin_modules() -> list[tuple[str, str]]:
    return [
        ("drift", "pulse_lib.plugins.drift"),
        ("prompts", "pulse_lib.plugins.prompts"),
        ("focus", "pulse_lib.plugins.focus"),
        ("cleancode", "pulse_lib.plugins.cleancode"),
        ("tags", "pulse_lib.plugins.tags"),
        ("mismatch", "pulse_lib.plugins.mismatch"),
    ]


def discover_host_plugin_files(root: Path) -> list[Path]:
    directory = root / ".pulse" / "plugins"
    if not directory.is_dir():
        return []
    return sorted(
        p
        for p in directory.glob("*.py")
        if p.name != "__init__.py" and not p.name.startswith("_")
    )


def discover_entry_point_plugins() -> list[tuple[str, Any]]:
    """Load third-party plugins registered under entry point group ``pulse.plugins``."""
    found: list[tuple[str, Any]] = []
    try:
        from importlib.metadata import entry_points
    except ImportError:  # pragma: no cover
        return found

    try:
        eps = entry_points()
        # Python 3.10+: select; 3.9 compat fallback
        if hasattr(eps, "select"):
            selected = list(eps.select(group="pulse.plugins"))
        else:
            selected = list(eps.get("pulse.plugins", []))  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001
        return found

    for ep in selected:
        try:
            loaded = ep.load()
            plugin = loaded
            if not hasattr(plugin, "setup"):
                plugin = _plugin_from_module(loaded) if hasattr(loaded, "__dict__") else None
                if plugin is None and callable(loaded):
                    plugin = loaded()
            if plugin is None:
                raise RuntimeError(f"entry point {ep.name} did not yield a Plugin")
            name = getattr(plugin, "name", None) or ep.name
            found.append((str(name), plugin))
        except Exception as exc:  # noqa: BLE001
            print(f"pulse: entry-point plugin `{ep.name}` failed: {exc}", file=sys.stderr)
    return found


def load_plugins(app: PulseApp) -> None:
    policy = load_plugin_policy(app.root)

    for name, import_path in discover_builtin_plugin_modules():
        if not _is_allowed(name, policy):
            app.skipped.append(name)
            continue
        try:
            mod = importlib.import_module(import_path)
            plugin = _plugin_from_module(mod)
            if plugin is None:
                raise RuntimeError(f"{import_path} has no PLUGIN")
            plugin.setup(app)
            app.loaded.append(getattr(plugin, "name", name))
        except Exception as exc:  # noqa: BLE001
            print(f"pulse: plugin `{name}` failed to load: {exc}", file=sys.stderr)
            app.skipped.append(name)

    for name, plugin in discover_entry_point_plugins():
        if not _is_allowed(name, policy):
            app.skipped.append(name)
            continue
        try:
            plugin.setup(app)
            app.loaded.append(name)
        except Exception as exc:  # noqa: BLE001
            print(f"pulse: entry-point plugin `{name}` failed to setup: {exc}", file=sys.stderr)
            app.skipped.append(name)

    for path in discover_host_plugin_files(app.root):
        name = path.stem
        if not _is_allowed(name, policy):
            app.skipped.append(name)
            continue
        try:
            mod = _load_module_from_path(path, f"pulse_host_plugin_{name}")
            plugin = _plugin_from_module(mod)
            if plugin is None:
                raise RuntimeError(f"{path} has no PLUGIN / Plugin")
            plugin.setup(app)
            app.loaded.append(getattr(plugin, "name", name))
        except Exception as exc:  # noqa: BLE001
            print(f"pulse: host plugin `{name}` failed to load: {exc}", file=sys.stderr)
            app.skipped.append(name)


def run_generate_hooks(app: PulseApp, registry: dict[str, Any]) -> None:
    for _name, hook in app.generate_hooks:
        hook(registry)
