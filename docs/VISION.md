# Vision — pulse as a project operating system

pulse is a thin **project operating system**: status, next actions, quality loops, and docs↔code honesty — stack-agnostic.

## Containment

On `init`, pulse writes **``.pulse/``** inside the host project (and, by default, a local
**``.venv/``** for engine deps — skip with ``--no-venv``).

- No forced product architecture or folder layout
- No automatic edits to ``.gitignore`` (commit ``.pulse/`` when the team should share status)
- Agent rules stay under ``.pulse/cursor/`` / ``.pulse/github/`` until you link
  them (``pulse init`` asks, or ``pulse cursor link`` / ``pulse github link``)

## Jobs to be done

1. **Know status** — done / partial / mocked / blocked
2. **Know next** — Continue + ship/fix/debt/hygiene queues
3. **Know debt** — tech-debt and bug cards on one board
4. **Keep clean** — quality self-check → backlog
5. **Keep docs honest** — drift + mismatch detect
6. **Sparse tags** — configurable `tag_prefix`, whole-repo scan
7. **Stay extensible** — plugins

## Quality loop

```
implement → quality-raise self-check → log TECH-DEBT if needed
         → update .pulse/features card
         → generate / drift / mismatch detect
         → next --prompt  → repeat
```

The dashboard is project memory. Chat is ephemeral; cards are not.
