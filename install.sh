#!/usr/bin/env bash
# Install pulse CLI into an isolated venv.
# Works even if the machine has no (suitable) Python — bootstraps via uv.
#
#   curl -fsSL https://raw.githubusercontent.com/Ngoctrong102/pulse/main/install.sh | bash
#
# Env overrides:
#   PULSE_REPO       git URL (default: https://github.com/Ngoctrong102/pulse.git)
#   PULSE_HOME       install root (default: ~/.local/share/pulse)
#   PULSE_BIN        shim dir (default: ~/.local/bin)
#   PULSE_PYTHON     force a python binary (skip discovery / uv)
#   PULSE_PY_VERSION python to fetch via uv when needed (default: 3.12)
#   PULSE_NO_UV=1    never bootstrap uv; fail if no suitable python
set -euo pipefail

REPO="${PULSE_REPO:-https://github.com/Ngoctrong102/pulse.git}"
PREFIX="${PULSE_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/pulse}"
BIN_DIR="${PULSE_BIN:-$HOME/.local/bin}"
PY_WANT="${PULSE_PY_VERSION:-3.12}"
VENV="$PREFIX/venv"
UV_BIN=""

log() { printf '%s\n' "$*"; }
err() { printf 'pulse install: %s\n' "$*" >&2; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

# Return 0 if $1 is python >= 3.11
python_ok() {
  local py="$1"
  [[ -x "$py" ]] || return 1
  "$py" - <<'PY' 2>/dev/null
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
}

find_system_python() {
  local cand
  if [[ -n "${PULSE_PYTHON:-}" ]]; then
    printf '%s\n' "$PULSE_PYTHON"
    return 0
  fi
  for cand in python3.13 python3.12 python3.11 python3; do
    if need_cmd "$cand" && python_ok "$(command -v "$cand")"; then
      command -v "$cand"
      return 0
    fi
  done
  return 1
}

ensure_uv() {
  if need_cmd uv; then
    UV_BIN="$(command -v uv)"
    return 0
  fi
  # Common install locations before PATH refresh
  for cand in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
    if [[ -x "$cand" ]]; then
      UV_BIN="$cand"
      return 0
    fi
  done
  if [[ "${PULSE_NO_UV:-}" == "1" ]]; then
    return 1
  fi
  if ! need_cmd curl; then
    err "need curl to bootstrap uv (or install Python 3.11+ yourself)"
    return 1
  fi
  log "  no suitable Python — installing uv (can fetch Python) …"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:${HOME}/.cargo/bin:${PATH}"
  if need_cmd uv; then
    UV_BIN="$(command -v uv)"
    return 0
  fi
  for cand in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
    if [[ -x "$cand" ]]; then
      UV_BIN="$cand"
      return 0
    fi
  done
  return 1
}

print_manual_python_help() {
  err "could not find or install Python >= 3.11"
  err ""
  err "Install one of these, then re-run this script:"
  err "  macOS:   brew install python@3.12"
  err "  Ubuntu:  sudo apt update && sudo apt install -y python3.12 python3.12-venv curl"
  err "  Fedora:  sudo dnf install -y python3.12"
  err "  Or:      https://www.python.org/downloads/"
  err ""
  err "Or install uv first (bootstraps Python without a system interpreter):"
  err "  curl -LsSf https://astral.sh/uv/install.sh | sh"
  err "  then re-run this install.sh"
}

resolve_python() {
  local py
  if py="$(find_system_python)"; then
    log "  using system Python: $py ($("$py" -c 'import sys; print("%d.%d"%sys.version_info[:2])'))"
    printf '%s\n' "$py"
    return 0
  fi
  if ! ensure_uv; then
    print_manual_python_help
    return 1
  fi
  log "  ensuring Python ${PY_WANT} via uv …"
  "$UV_BIN" python install "$PY_WANT" >/dev/null
  py="$("$UV_BIN" python find "$PY_WANT")"
  if ! python_ok "$py"; then
    print_manual_python_help
    return 1
  fi
  log "  using uv Python: $py"
  printf '%s\n' "$py"
}

# --- main ---
log "pulse install → $PREFIX"
mkdir -p "$PREFIX" "$BIN_DIR"

PYTHON="$(resolve_python)" || exit 1

if [[ ! -x "$VENV/bin/python" ]]; then
  log "  creating venv …"
  if [[ -n "${UV_BIN:-}" && -x "$UV_BIN" ]]; then
    "$UV_BIN" venv --python "$PYTHON" "$VENV"
  else
    "$PYTHON" -m venv "$VENV"
  fi
fi

if [[ ! -x "$VENV/bin/python" ]]; then
  err "failed to create venv at $VENV"
  exit 1
fi

log "  installing from $REPO …"
if [[ -n "${UV_BIN:-}" && -x "$UV_BIN" ]]; then
  "$UV_BIN" pip install --python "$VENV/bin/python" -U "git+${REPO}"
else
  "$VENV/bin/python" -m pip install -q -U pip
  "$VENV/bin/python" -m pip install -q -U "git+${REPO}"
fi

cat >"$PREFIX/install-meta.json" <<EOF
{
  "version": 1,
  "repo": "${REPO}",
  "prefix": "${PREFIX}",
  "bin_dir": "${BIN_DIR}",
  "shim": "${BIN_DIR}/pulse",
  "python": "${PYTHON}"
}
EOF

ln -sfn "$VENV/bin/pulse" "$BIN_DIR/pulse"
chmod +x "$BIN_DIR/pulse" 2>/dev/null || true

log ""
log "Installed pulse $($VENV/bin/pulse version 2>/dev/null || true)"
log "  shim: $BIN_DIR/pulse"
log ""
if ! need_cmd pulse; then
  log "Add to PATH (then re-open the shell):"
  log "  export PATH=\"$BIN_DIR:\$PATH\""
  case "${SHELL:-}" in
    */zsh) log "  # e.g. echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.zshrc" ;;
    */bash) log "  # e.g. echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.bashrc" ;;
  esac
  log ""
fi
log "Next:"
log "  cd your-project && pulse init"
log "  pulse upgrade"
log "  pulse uninstall"
