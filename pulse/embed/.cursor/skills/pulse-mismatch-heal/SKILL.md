---
name: pulse-mismatch-heal
description: Toolkit B — apply safe patches to status cards (.pulse/features/) from a detect report only (--dry-run then --apply). Never invent findings without --from-report.
---

# Pulse Mismatch Heal (Toolkit B)

Requires a report from Toolkit A:

```bash
.pulse/bin/pulse mismatch heal --from-report .pulse/mismatch-report.json --dry-run
.pulse/bin/pulse mismatch heal --from-report .pulse/mismatch-report.json --apply
```

Does not touch production DB. Does not auto-run from hooks. Does not silently re-detect as a substitute for a missing report.
