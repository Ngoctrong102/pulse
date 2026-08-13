---
applyTo: "**"
---

# Pulse quality (code edits)

When editing product code:

1. Sync the matching `.pulse/features/` card (or `pulse new` for bugs/tech-debt).
2. Log smells with `.pulse/bin/pulse new --type tech-debt|bug` — do not silent-skip.
3. Before claiming done: `.pulse/bin/pulse mismatch detect`.
4. End with a short `## Quality self-check` if you changed code.

Full rubric: `.pulse/github/quality-raise.md` or `.github/pulse-quality-raise.md` after `pulse github link`.
