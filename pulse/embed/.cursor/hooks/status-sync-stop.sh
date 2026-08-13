#!/usr/bin/env bash
# Fail-open: product code/docs changed without .pulse feature cards.
set -euo pipefail
ROOT="${CURSOR_PROJECT_DIR:-$(pwd)}"
cd "$ROOT"

paths=()
while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  p="${line:3}"
  if [[ "$p" == *" -> "* ]]; then p="${p##* -> }"; fi
  p="${p#\"}"; p="${p%\"}"
  paths+=("$p")
done < <(git status --porcelain=v1 2>/dev/null || true)

has_product=false
has_yaml=false
for p in "${paths[@]}"; do
  [[ -z "$p" ]] && continue
  case "$p" in
    .pulse/features/*|.pulse/features/|.pulse/features)
      has_yaml=true; continue ;;
    .pulse/*) continue ;;
    node_modules/*|.venv/*|venv/*|vendor/*|dist/*|build/*|target/*|__pycache__/*)
      continue ;;
    *)
      has_product=true ;;
  esac
done

if $has_product && ! $has_yaml; then
  cat <<'MSG'
{"additional_context":"pulse sync reminder: product code/docs changed without .pulse/features/*.yaml. Update a card (or .pulse/bin/pulse new), then .pulse/bin/pulse generate. Do NOT auto-run mismatch-heal."}
MSG
fi
exit 0
