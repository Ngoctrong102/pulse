# Pulse Quality Raise — rubric (Copilot / GitHub)

**Detect early. Log every finding as a backlog card. Fix later on the user's call.**

Only correctness / security / privacy blockers are raised inline and paused; everything else:

```bash
.pulse/bin/pulse new --type tech-debt|bug --id … --name … --severity low|medium|high|blocker --where … --why …
```

## When to log

| Finding | Examples |
|---|---|
| Conflict | Requirements vs code; docs contradict implementation |
| Oversized / multi-duty file | Kitchen-sink modules; View+network+persistence in one file |
| Stringly-typed control flow | switch/if on raw strings for a closed vocabulary |
| Duplication | Same rule/table in ≥2 places |
| SOLID / structure | Fat router/View; wrong layer owns mutation |
| Over-engineering | New framework/layer with no 2nd use case |
| Security/privacy | Client secrets, over-retention, missing isolation |

## Clean Code red flags (sample)

| Area | Red flag |
|---|---|
| Names | Filler (`data`/`info`/`helper`); magic numbers |
| Functions | >1 responsibility; bool flag param; >3 params |
| Error handling | Silent catch / `try?` with no rationale |
| Boundaries | Raw API shapes leaking into UI/business logic |
| Classes | Low cohesion; vendor choice not behind an interface |

## Disposition

1. Log card → continue unless blocker.
2. Blockers: pause, tell the user, still log a card.
3. Do not auto-heal mismatch reports unless asked.
