# Card / meta schema (informal)

Source of truth for project settings and cards is **`.pulse/features/`**.
`config.json` is only a kit version stamp (`pulse_version`).

## `_meta.yaml`

| Key | Type | Notes |
|---|---|---|
| `version` | int | Registry format version (currently `1`) |
| `project` | string | Display name |
| `tag_prefix` | string | Uppercase product tag prefix |
| `speckit` | bool | When false, prompts omit Spec Kit jargon |
| `pulse_version` | string | Kit version that last init/upgrade stamped |
| `updated` | date string | Last board touch |
| `focus_id` | string \| null | Active focus card id |
| `plugins` | mapping | `enabled` / `disabled` lists |

Unknown keys are preserved on save.

## Feature card (`type: feature`)

Required: `id`, `type`, `name`, `status` ∈ {done, partial, todo, blocked},
`percent` 0–100, `priority` int, `roi` int.

`status: done` forbids non-empty `mocks` or `remaining`.

## Backlog card (`type: bug` \| `tech-debt`)

Required: `id`, `type`, `name`, `status`, `priority`, `severity` ∈ {low, medium, high, blocker}.

## Clean-code module (`.pulse/cleancode/<id>.yaml`)

Required: `id`, `area` (free-form label), `globs` (non-empty list).
`score` is int 0–100 or null (unscanned).
