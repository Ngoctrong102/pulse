# Plugins

Host plugins live under **`.pulse/plugins/`** (created by `pulse init`).

```python
# .pulse/plugins/mything.py
from pulse_lib.plugin import Plugin, PulseApp

class MyThing(Plugin):
    name = "mything"

    def setup(self, app: PulseApp) -> None:
        def cmd(args):
            print("mything ok")
            return 0
        app.add_command("mything", help="Demo", handler=cmd)

PLUGIN = MyThing()
```

```bash
.pulse/bin/pulse plugins
.pulse/bin/pulse mything
.pulse/bin/pulse generate   # runs on_generate hooks
```

Toggle in `.pulse/features/_meta.yaml`:

```yaml
plugins:
  enabled: [drift, prompts, focus, cleancode, tags, mismatch, mything]
  disabled: []
```

Pip entry points: group `pulse.plugins`.
