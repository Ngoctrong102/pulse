"""Tag / untagged-cleanup paste prompts."""

from __future__ import annotations

from typing import Any

from pulse_lib.prompt_common import _card_path, _list_preview
from pulse_lib.tag_audit import project_label, tag_marker


def build_tag_prompt(data: dict[str, Any], feature_id: str) -> str:
    """Paste-ready prompt: bidirectional requirement tagging for one feature."""
    feat = next(
        (f for f in (data.get("features") or []) if isinstance(f, dict) and f.get("id") == feature_id),
        None,
    )
    if not feat:
        return f"Feature id `{feature_id}` not found in .pulse/features/."
    evidence = feat.get("evidence") or {}
    paths_any = evidence.get("paths_any") if isinstance(evidence, dict) else []
    docs = feat.get("docs") or {}
    fr_ids = list(docs.get("fr") or []) if isinstance(docs, dict) else []
    uf_ids = list(docs.get("uf") or []) if isinstance(docs, dict) else []
    lines = [
        f"Sync `{tag_marker()}` tags **bidirectionally** for feature "
        f"`{feature_id}` (`{feat.get('name')}`) — this feature only, sparse.",
        "",
        "## Rules",
        f"- Comment form: `// {tag_marker()} FR-…` / `# {tag_marker()} FR-…`",
        "- IDs must exist in `docs/`. Max ~3 IDs per anchor. Public symbols only.",
        "- Large smells → quality-raise; wait for approval before a big retag.",
        "",
        f"Card: `{_card_path(feature_id)}`",
        f"status={feat.get('status')} percent={feat.get('percent')}",
        f"docs.fr={fr_ids} docs.uf={uf_ids}",
        f"evidence.paths_any={_list_preview(paths_any, limit=8)}",
        f"remaining(top)={_list_preview(feat.get('remaining'), limit=3)}",
        "",
        "## Work (both directions)",
        f"A) In the paths above: `rg '{tag_marker()}'` — add/fix sparse tags for shipped FRs.",
        "B) Every implemented FR/UF needs ≥1 tag hit; not implemented yet → do not invent tags.",
        "Do not change product behavior; do not mark `done` while mocks/remaining remain.",
        "",
        "Reply with tables: Code→docs | Docs→code (path or “not implemented”).",
    ]
    return "\n".join(lines)


def build_untagged_cleanup_prompt(data: dict[str, Any], *, all_project: bool = False) -> str:
    """Paste-ready prompt: review untagged requirement tags.

    Default scope: ``focus_id`` when set, else top mvp/partial features.
    Pass ``all_project=True`` (CLI ``--all``) for a whole-repo pass.
    """
    features = [f for f in (data.get("features") or []) if isinstance(f, dict)]
    focus_id = data.get("focus_id")
    scope_note: str
    ranked: list[dict[str, Any]]

    if not all_project and focus_id:
        focus = next((f for f in features if f.get("id") == focus_id), None)
        ranked = [focus] if focus else []
        scope_note = f"Scoped to focus `{focus_id}` (pass `--all` for whole project)."
    elif not all_project:
        ranked = sorted(
            features,
            key=lambda f: (
                0 if f.get("mvp") else 1,
                0 if f.get("status") in {"partial", "done"} else 1,
                int(f.get("priority") or 99),
                str(f.get("id") or ""),
            ),
        )[:8]
        scope_note = (
            "Scoped to top mvp/partial features (default). "
            "Pass `--all` for a whole-project pass."
        )
    else:
        ranked = sorted(
            features,
            key=lambda f: (
                0 if f.get("mvp") else 1,
                0 if f.get("status") in {"partial", "done"} else 1,
                int(f.get("priority") or 99),
                str(f.get("id") or ""),
            ),
        )
        scope_note = "Whole-project pass (`--all`)."

    lines = [
        f"Review `{tag_marker()}` on {project_label()} — sparse; prioritize public anchors missing tags.",
        "",
        f"## Scope — {scope_note}",
        f"- Prefer `rg '{tag_marker()}'` limited to evidence paths below (skip vendor/tests).",
        "- Max ~3 IDs/anchor; skip test/generated/vendor. No spam. No auto-heal.",
        "- Large smells → quality-raise + approval before a big cleanup.",
        "",
        "## Features in scope",
    ]
    if not ranked:
        lines.append("_No features in scope — set focus or pass `--all`._")
    for f in ranked:
        ev = f.get("evidence") or {}
        paths = ev.get("paths_any") if isinstance(ev, dict) else []
        docs = f.get("docs") or {}
        fr = (docs.get("fr") if isinstance(docs, dict) else None) or []
        lines.append(
            f"- `{f.get('id')}` [{f.get('status')}] fr={_list_preview(fr, limit=4)} "
            f"paths={_list_preview(paths, limit=4)}"
        )
    lines.extend(
        [
            "",
            "Output: untagged→proposed tags | cleaned | intentionally untagged (+ reason).",
        ]
    )
    return "\n".join(lines)
