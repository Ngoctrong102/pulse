#!/usr/bin/env bash
# Fail-open: product code/docs changed without .pulse feature cards.
set -euo pipefail
ROOT="${CURSOR_PROJECT_DIR:-$(pwd)}"
cd "$ROOT"

roots=""
meta=".pulse/features/_meta.yaml"
if [[ -f "$meta" ]]; then
  roots=$(python3 - <<'PY' 2>/dev/null || true
import yaml
from pathlib import Path
p = Path(".pulse/features/_meta.yaml")
data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
roots = data.get("code_roots") or ["src"]
if isinstance(roots, list):
    print(" ".join(str(r).strip().strip("/") for r in roots if str(r).strip()))
PY
)
fi
roots="${roots:-src app backend frontend}"

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
    docs/*|specs/*|specs/) has_product=true; continue ;;
  esac
  for r in $roots; do
    case "$p" in
      "$r"/*|"$r"/) has_product=true; break ;;
    esac
  done
done

if $has_product && ! $has_yaml; then
  cat <<'MSG'
{"additional_context":"pulse sync reminder: product code/docs changed without .pulse/features/*.yaml. Update a card (or .pulse/bin/pulse new), then .pulse/bin/pulse generate. Do NOT auto-run mismatch-heal."}
MSG
fi
exit 0
