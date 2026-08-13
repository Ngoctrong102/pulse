---
name: pulse
description: Validate/report/generate project status; explain/next prompts; docs↔code drift; quality loops for a project operating system. Use when updating progress, asking status/next, or regenerating the board.
---

# Pulse CLI

```bash
.pulse/bin/pulse validate|report|generate
.pulse/bin/pulse set --feature <id> --status partial --percent 40 --add-remaining "…"
.pulse/bin/pulse set --focus <id> | --clear-focus
.pulse/bin/pulse new --id <id> --name "…" --type feature|bug|tech-debt
.pulse/bin/pulse next [--json|--prompt] [--lane all|ship|fix|debt|hygiene]
.pulse/bin/pulse explain [--feature id]
.pulse/bin/pulse drift|tag|cleancode|mismatch|plugins
```

**Continue:** `next --prompt` follows `focus_id`; open cards with `blocks` containing focus interrupt first.

## When to update a card

| Trigger | Do |
|---|---|
| Changed product code or product docs | `set` / `new` then `generate` |
| Bug / tech-debt found | `new --type bug|tech-debt` |
| User asks status / next | `explain` / `next` — never invent from memory |

Quality mid-task: `.cursor/skills/quality-raise/SKILL.md` + rule `quality-raise.mdc`.
