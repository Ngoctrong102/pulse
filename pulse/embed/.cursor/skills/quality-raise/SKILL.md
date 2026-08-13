---
name: quality-raise
description: Detect conflicts, code smells, architecture or SOLID/maintainability issues mid-task and auto-log every finding to the tech-debt backlog + status dashboard; defer fixes to the user (raise correctness/security blockers inline). Use whenever quality or design problems are found during implement, docs, or Spec Kit work.
---

# Pulse Quality Raise

**Detect early. Log every finding as a backlog card (dashboard). Fix later on the user's call.** See `.cursor/rules/quality-raise.mdc` for the mandatory self-check gate (commands + required output table) and the Backlog-first workflow — this skill is the reference for *what* to check and *why*. Only correctness / security / privacy blockers are raised inline and paused; everything else is captured with `.pulse/bin/pulse new --type tech-debt|bug …` (a card in `.pulse/features/`, which regenerates the tech-debt view) and deferred.

## When to invoke (eagerly)

| Finding | Examples |
|---|---|
| Conflict | Requirements vs flows vs tech notes; code contradicts docs; Spec Kit vs product docs |
| Oversized / multi-duty file | 1k+ LOC kitchen-sink; View+networking+persistence in one file |
| Stringly-typed control flow | `switch`/`if` on raw string/int literals for a closed vocabulary instead of a typed enum |
| Duplication | Same rule in two layers; same lookup table reimplemented in ≥2 files even if code isn't identical |
| SOLID / structure | Fat router/View, wrong layer owns mutation rules, adding a case needs edits in ≥2 switches (OCP) |
| Over-engineering | New framework/layer/pattern with no real 2nd use case — raise this too |
| Security/privacy | Client secrets, over-retention, missing isolation |

## Clean Code checklist (Robert C. Martin) — one red flag per area

| Area | Red flag |
|---|---|
| Names | Filler words (`data`/`info`/`helper`/`manager`); mixed verbs for the same op (`fetch`/`get`/`load`); magic numbers/strings |
| Functions | >1 responsibility; boolean flag param; >3 params; output (`inout`) params; hidden side effects |
| Comments | Explains *what* not *why*; commented-out code; obsolete/misleading |
| Formatting | Helper far from its only caller; file mixes unrelated concerns |
| Objects/data | Law of Demeter violations (`a.b.c.d.doThing()`); hybrid half-object-half-struct |
| Error handling | Silent `try?`/empty-catch with no fallback rationale; `nil`/`false`/`None` hiding "no data" vs "error" |
| Boundaries | Raw JSON/API dict shapes leaking past the parser into Views/business logic |
| Unit tests | Not F.I.R.S.T (Fast/Independent/Repeatable/Self-validating/Timely); >1 assert-concept per test |
| Classes | Low cohesion / feature envy; volatile choice (vendor/algorithm) not isolated behind an interface/protocol |
| Concurrency | Shared mutable state across tasks; isolation not matching real mutation site |

## SOLID — ask these questions

| Principle | Ask this |
|---|---|
| SRP | More than one reason to change? Can't name it with one verb+noun? |
| OCP | New case needs editing an existing switch/if-chain in ≥2 places instead of one catalog/table row? |
| LSP | Override/conformance narrows preconditions or adds failure modes vs. the base contract? |
| ISP | Interface forces conformers to stub unused methods? |
| DIP | High-level coordinator hardcodes a concrete low-level dep (`URLSession.shared`, `UserDefaults.standard`, global singleton) blocking tests? |

Example smell: a navigator/`route` helper that `switch`es on 15+ raw destination strings with hand-grown aliases — no typed source of truth, already drifted from another layer's destination list.

## Design patterns — use the recognized one, never invent a bespoke one

Reach for the standard pattern only once the problem shape actually recurs (≥2 real call sites, or a named extension point in requirements). Don't fabricate a "manager"/"engine"/"pipeline" that reinvents a known pattern worse; don't force-fit a pattern with no real 2nd use case either (YAGNI).

| Problem shape | Pattern | Watch for |
|---|---|---|
| Object built from external network/AI data | Factory Method | parsers that grow ad hoc `if type ==` |
| Whole family of related objects chosen together (mock vs live) | Abstract Factory | `if mode==` at every call site |
| Multi-step construction, many optional parts | Builder | init growing >5 optional params |
| One shared app-wide instance | Singleton (sparingly) | only stateless infra; never mutable/needs-mocking state |
| Wrapping a 3rd-party API to your own interface | Adapter | SDK types leaking into domain |
| Coordinating subsystems behind one entry point | Facade | god coordinator that also owns business rules |
| Abstraction vs implementation must vary independently | Bridge | content vs delivery channel tangled |
| Tree-shaped data, uniform item/group handling | Composite | special-casing leaves vs groups everywhere |
| Optional behavior without subclass explosion | Decorator | copy-pasted view/handler variants |
| Gating access to a real object (permission/lazy/cache) | Proxy | permission checks duplicated at every call |
| Growing `if type == X` chain on a domain value | Strategy | catalog/table of handlers instead |
| Family of interchangeable algorithms at runtime | Strategy | same as above |
| Fixed algorithm skeleton, swappable sub-steps | Template Method | duplicated report/pipeline shapes |
| Undo/queue/replay user actions | Command | ad hoc retry/confirm logic |
| Request passed through handlers till one deals with it | Chain of Responsibility | giant `handleIntent` switch |
| Reacting to state changes, loosely coupled | Observer | direct cross-module callbacks everywhere |
| Reduce many-to-many object chatter to one point | Mediator | every feature talking to every other |
| Capture/restore state without exposing internals | Memento | leaking internal snapshots |
| Behavior keyed on internal state/transitions | State | branchy status enums without transition rules |
| Persistence access abstracted from business logic | Repository | SQL/HTTP in views/controllers |
| View owns too much state/logic | MVVM / thin View | networking + persistence inside UI |
| Cross-cutting concern applied uniformly | Middleware/Pipeline | auth/logging duplicated per handler |
| One event, many independent listeners | Pub/Sub | coordinator-to-coordinator wiring |
| Network call must fail gracefully after retries | Circuit Breaker/Retry | unbounded retry / no backoff |
| Avoid nil-checks scattered for an "absent" case | Null Object | empty aggregates instead of optional soup |
| No-identity value, compared by content | Value Object | raw tuples/maps for domain quantities |

Rarely relevant — use only if the exact shape appears; don't pre-apply: Prototype, Flyweight, Iterator (language collections usually cover it), Visitor, Interpreter (don't invent a DSL for prompts/config — plain YAML/JSON is correct).

## Code anti-patterns — forbidden, always raise if seen, never introduce

| Anti-pattern | Looks like | Hurts because |
|---|---|---|
| God Object/File | One type owns unrelated responsibilities | Unsafe to review/change |
| Big Ball of Mud | No layering; anything calls anything | Can't bound change blast radius |
| Spaghetti Code | Deep nested conditionals/callbacks | Unreadable, error-prone |
| Shotgun Surgery | One change forces edits across many files | Missing abstraction |
| Lava Flow | Dead code kept "just in case" | Hides real dead paths |
| Copy-Paste Programming | Logic duplicated instead of reused | Diverges silently |
| Golden Hammer | One familiar tool forced on every problem | Wrong abstraction cost |
| Not-Invented-Here | Reinventing a standard pattern poorly | Re-introduces solved bugs |
| Cargo Cult | Copying structure without understanding why | Ceremony, no benefit |
| Premature Optimization | Complexity for unmeasured perf need | Violates Simplicity & Ship |
| Primitive Obsession | Raw strings/ints standing in for a domain concept | No compiler safety, drift |
| Anemic model | Data model with no behavior, rules smeared over callers | Wrong layer owns mutation (SRP/DIP) |
| Poltergeist | Class exists only to call another's methods | Unneeded indirection |
| Boat Anchor | Unused code/dep kept "for the future" | Dead weight |

## Disposition: log a backlog card (default)

Every ⚠️ finding is **recorded, not fixed**. Do this in the same turn, no approval needed to record — one command per finding creates the card and regenerates the dashboard:

```bash
.pulse/bin/pulse new --type tech-debt \
  --id TECH-DEBT-NNN --name "<short title>" \
  --severity low|medium|high|blocker \
  --where "path/symbol:line" \
  --why "what the self-check flagged + why it hurts (maintain/extend/correctness/privacy)" \
  --proposed-fix "1. … 2. …" \
  --ref <owning-feature-id>
```

- Use `--type bug` for a defect instead of tech-debt.
- Card lands in `.pulse/features/<id>.yaml`; the command auto-regenerates BOARD, `DRIFT.md`, and the generated tech-debt view. Never hand-edit the tech-debt view — it is a view.
- `--ref` relates the card to its owning feature (quality-hardening card if present; else the owning feature).
- `--blocks <focus-id>` only when the finding **stops continuing** the current Focus (Continue interrupt). Smells for later work → `--ref` only (park).
- **Continue** the original task; mention which card id you logged. Do **not** deepen the smell (no new copy-paste on top of a known duplicate).

## Inline-raise exception (blockers only)

For **correctness / security / privacy** issues or a docs↔code conflict that would ship wrong behavior, also emit this block and **pause that path** until the user replies (still log a backlog card too):

```markdown
## Quality / architecture finding

- **Severity:** blocker | high
- **Where:** path/symbol (and requirement id if any)
- **Smell / principle:** …
- **Why it can't wait:** correctness / security / privacy
- **Options:** 1. … 2. …
- **Awaiting:** your call
```

## When the user asks to fix a backlog item

Implement only that item, no bonus refactors; keep simplicity principles; add/adjust tests; close the card with `.pulse/bin/pulse set --feature TECH-DEBT-NNN --status done`; update the related feature card if progress changed; fix docs in the same task if they were wrong.

## Workflow anti-patterns (how NOT to handle findings)

- Leaving a finding only in chat — it must land in a backlog card + dashboard, or it's lost
- Silent drive-by cleanup / "while I was here" large renames — recording ≠ fixing; fix only when asked
- Claiming SOLID while adding unused abstractions
- Auto-running mismatch-heal or mass status changes “for quality”
