"""pulse installer package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pulse")
except PackageNotFoundError:  # pragma: no cover — editable / source tree
    __version__ = "0.4.3"
