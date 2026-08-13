#!/usr/bin/env bash
# Install pulse CLI into an isolated venv (no project .venv required).
#
#   curl -fsSL https://raw.githubusercontent.com/Ngoctrong102/pulse/main/install.sh | bash
#
# Env overrides:
#   PULSE_REPO     git URL (default: https://github.com/Ngoctrong102/pulse.git)
#   PULSE_HOME     install root (default: ~/.local/share/pulse)
#   PULSE_BIN      shim dir     (default: ~/.local/bin)
#   PULSE_PYTHON   python       (default: python3)
set -euo pipefail

REPO="${PULSE_REPO:-https://github.com/Ngoctrong102/pulse.git}"
PREFIX="${PULSE_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/pulse}"
BIN_DIR="${PULSE_BIN:-$HOME/.local/bin}"
PYTHON="${PULSE_PYTHON:-python3}"
VENV="$PREFIX/venv"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "pulse install: need $PYTHON on PATH" >&2
  exit 1
fi

echo "pulse install → $PREFIX"
mkdir -p "$PREFIX" "$BIN_DIR"

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "  creating venv …"
  "$PYTHON" -m venv "$VENV"
fi

echo "  installing from $REPO …"
"$VENV/bin/python" -m pip install -q -U pip
"$VENV/bin/python" -m pip install -q -U "git+${REPO}"

# Remember layout for `pulse uninstall`
cat >"$PREFIX/install-meta.json" <<EOF
{
  "version": 1,
  "repo": "${REPO}",
  "prefix": "${PREFIX}",
  "bin_dir": "${BIN_DIR}",
  "shim": "${BIN_DIR}/pulse"
}
EOF

ln -sfn "$VENV/bin/pulse" "$BIN_DIR/pulse"
chmod +x "$BIN_DIR/pulse" 2>/dev/null || true

echo
echo "Installed pulse $($VENV/bin/pulse version 2>/dev/null || true)"
echo "  shim: $BIN_DIR/pulse"
echo
if ! command -v pulse >/dev/null 2>&1; then
  echo "Add to PATH (then re-open the shell):"
  echo "  export PATH=\"$BIN_DIR:\$PATH\""
  case "${SHELL:-}" in
    */zsh) echo "  # e.g. echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.zshrc" ;;
    */bash) echo "  # e.g. echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.bashrc" ;;
  esac
  echo
fi
echo "Next:"
echo "  pulse init /path/to/your/project"
echo "  pulse update          # later: pull latest + sync .pulse/"
echo "  pulse uninstall       # remove this CLI install"
