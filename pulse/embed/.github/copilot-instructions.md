<!-- pulse:begin -->
# Pulse — project operating system (GitHub Copilot)

Status lives in **`.pulse/features/`** (one YAML card per feature / bug / tech-debt; `_meta.yaml` has `focus_id` + `code_roots`). Chat does **not** update the board until a card is written and you run generate.

Prefer the CLI:

```bash
.pulse/bin/pulse set --feature <id> --status partial --percent 40 --add-remaining "…"
.pulse/bin/pulse new --id <id> --name "…" --type feature|bug|tech-debt
.pulse/bin/pulse next --prompt
.pulse/bin/pulse explain
.pulse/bin/pulse generate
```

Edit **cards** under `.pulse/features/` / `.pulse/cleancode/`. Do **not** edit vendored `.pulse/tools/` — refresh with `pulse upgrade`.

## When you must sync a card

| Change | Action |
|---|---|
| Product code under `_meta.code_roots` | Patch matching card |
| Product docs treated as SoT | Same — or `new --type feature` |
| Bug / tech-debt found | `new --type bug` / `new --type tech-debt` |

Then `.pulse/bin/pulse generate` and/or `drift`.

## Done / mocks / heal

- Chat “done” ≠ board done — update the card.
- `status: done` forbids non-empty `mocks` or `remaining`.
- Before claiming done: `.pulse/bin/pulse mismatch detect`.
- Heal only when the user asks (`mismatch heal`).

## Quality raise

While touching code/docs: do not leave quality issues silent.

1. Log every non-blocker as a backlog card: `.pulse/bin/pulse new --type tech-debt|bug …`
2. Do not fix large smells unless the user asks — triage on the board.
3. Correctness / security / privacy blockers → raise inline + pause (still log a card).
4. After a turn that edited code: short `## Quality self-check` (even if clean).

Rubric details: `.pulse/github/quality-raise.md` (also installed under `.github/` when linked).

## Status questions

User asks status / next → run `explain` / `next --prompt` — do not invent remaining/mocks from memory.
<!-- pulse:end -->
