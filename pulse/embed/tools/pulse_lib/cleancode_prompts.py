"""Clean-code scan/fix paste-ready prompts."""

from __future__ import annotations

from typing import Any

# Kept in sync with quality-raise skill self-check themes.
RUBRIC_CHECKS = (
    "Oversized file / god module (past language LOC budget, or mixed jobs)",
    "SOLID / boundary violations (routers vs services vs models; views vs services)",
    "Duplicate logic or duplicate lookup tables that should be one module",
    "Stringly-typed control flow (switch/if on raw String/Int for a closed vocab)",
    "Long / param-heavy / flag-param functions (>~40 lines, >3 params, Bool switch)",
    "Silent error swallow (try?/catch {}/except: with no fallback rationale)",
    "Dead code, leaky abstractions, newly introduced singleton / global mutable state",
)


def _rubric_block() -> str:
    return "\n".join(f"{i + 1}. {c}" for i, c in enumerate(RUBRIC_CHECKS))


def _globs_block(mod: dict[str, Any]) -> str:
    return "\n".join(f"- {g}" for g in (mod.get("globs") or []))


def build_scan_prompt(mod: dict[str, Any]) -> str:
    mid = mod.get("id")
    return f"""Scan clean-code for module **{mod.get('name')}** (`{mid}`).

Scope (read-only within these globs — do NOT edit code):
{_globs_block(mod)}

Budget: sample the module — prefer entrypoints / public APIs / recently changed files.
If a folder is huge, do **not** read every file; note skipped paths and still score.

Score against the quality-raise rubric:
{_rubric_block()}

For EACH smell found, log a tech-debt card:
`.pulse/bin/pulse new --type tech-debt --id TECH-DEBT-NNN --name "…" --severity low|medium|high|blocker --where "file:line" --why "…" --proposed-fix "…" --ref {mid}`

After listing findings, score /100 (🟢>=85 clean · 🟡60-84 · 🔴<60) and write it back:
`.pulse/bin/pulse cleancode set --module {mid} --score N --summary "1-2 sentence summary" [--subscore size=NN --subscore duplication=NN …] [--finding TECH-DEBT-NNN …]`

Do not edit product code in this turn — only scan, log cards, and set the score."""


def build_fix_prompt(mod: dict[str, Any]) -> str:
    mid = mod.get("id")
    findings = mod.get("findings") or []
    findings_line = (
        "Prioritize closing open findings for this module: " + ", ".join(findings)
        if findings
        else "No findings recorded yet — audit against the rubric below."
    )
    return f"""Clean dirty code in module **{mod.get('name')}** (`{mid}`).

Scope (edit only within these globs — do not expand outside):
{_globs_block(mod)}

{findings_line}

Budget: fix the worst smells first; if the module is large, stay within a small file set this turn.

Rubric to satisfy (fix every violation you touch):
{_rubric_block()}

Requirements:
- Keep pytest / build green; minimal changes, module-scoped only.
- For each fixed tech-debt card: `.pulse/bin/pulse set --feature TECH-DEBT-NNN --status done`.
- Then rescan and update the score: `.pulse/bin/pulse cleancode set --module {mid} --score N --summary "…"`."""
