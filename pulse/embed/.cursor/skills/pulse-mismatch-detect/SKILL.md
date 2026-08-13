---
name: pulse-mismatch-detect
description: Read-only Toolkit A — detect .pulse cards vs code mismatches and write mismatch-report. Never modifies status cards (.pulse/features/). Never runs heal.
---

# Pulse Mismatch Detect (Toolkit A)

```bash
.pulse/bin/pulse mismatch detect
```

Outputs `.pulse/mismatch-report.json` + `.md`. Exit 1 if CRITICAL.

**MUST NOT** call heal or edit status cards in `.pulse/features/`. To repair, user/agent runs Toolkit B explicitly with `--from-report`.

After detect (especially if warning/critical > 0), suggest:

```bash
.pulse/bin/pulse next
.pulse/bin/pulse explain
```
