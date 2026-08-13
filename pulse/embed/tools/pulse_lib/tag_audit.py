"""Requirement-tag audit — orphans + evidence paths missing tags.

Configured via ``.pulse/features/_meta.yaml``:

```yaml
tag_prefix: MYAPP          # → // MYAPP: FR-001
```

Scans the whole project tree (skips vendored / hidden / venv paths).
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import yaml

from pulse_lib import Finding
from pulse_lib.paths import META_PATH, REPO_ROOT

ID_TOKEN_RE = re.compile(r"\b((?:FR|NFR|TECH|UF|DEC)[-A-Z0-9.]+)\b")
CODE_SUFFIXES = {".py", ".swift", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".kt"}
_SKIP_DIR_NAMES = {
    "node_modules",
    ".venv",
    "venv",
    "vendor",
    "dist",
    "build",
    "target",
    "__pycache__",
    ".pulse",
    ".git",
}

_DEFAULT_PREFIX = "SK"


def _load_meta() -> dict[str, Any]:
    if not META_PATH.is_file():
        return {}
    try:
        data = yaml.safe_load(META_PATH.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return data if isinstance(data, dict) else {}


def tag_prefix() -> str:
    meta = _load_meta()
    raw = meta.get("tag_prefix") or meta.get("project") or _DEFAULT_PREFIX
    return str(raw).strip().upper().replace(" ", "") or _DEFAULT_PREFIX


def project_label() -> str:
    meta = _load_meta()
    return str(meta.get("project") or "this project")


def tag_marker() -> str:
    return f"{tag_prefix()}:"


def tag_re() -> re.Pattern[str]:
    return re.compile(rf"{re.escape(tag_prefix())}:\s*([A-Z0-9_.,\- ]+)", re.I)


def _should_skip_path(path: Path) -> bool:
    return any(part in _SKIP_DIR_NAMES or part.startswith(".") for part in path.parts)


def _iter_code_files(base: Path) -> Iterable[Path]:
    if base.is_file():
        if base.suffix.lower() in CODE_SUFFIXES and not _should_skip_path(base):
            yield base
        return
    if not base.is_dir():
        return
    for path in base.rglob("*"):
        if path.suffix.lower() not in CODE_SUFFIXES:
            continue
        try:
            rel_parts = path.relative_to(REPO_ROOT).parts
        except ValueError:
            rel_parts = path.parts
        if any(part in _SKIP_DIR_NAMES or part.startswith(".") for part in rel_parts):
            continue
        yield path


def extract_tag_ids_from_text(text: str) -> set[str]:
    ids: set[str] = set()
    for m in tag_re().finditer(text):
        for tok in ID_TOKEN_RE.findall(m.group(1)):
            ids.add(tok)
    return ids


def scan_code_tags(roots: list[Path] | None = None) -> dict[str, list[str]]:
    """req_id -> relative paths that mention it."""
    hits: dict[str, list[str]] = defaultdict(list)
    prefix_l = tag_prefix().lower() + ":"
    scan_roots = roots if roots is not None else [REPO_ROOT]
    for root in scan_roots:
        if not root.exists():
            continue
        for path in _iter_code_files(root):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if prefix_l not in text.lower():
                continue
            rel = str(path.relative_to(REPO_ROOT))
            for req_id in extract_tag_ids_from_text(text):
                if rel not in hits[req_id]:
                    hits[req_id].append(rel)
    return dict(hits)


def path_tag_ids(rel: str) -> set[str]:
    base = REPO_ROOT / rel
    found: set[str] = set()
    for path in _iter_code_files(base):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        found |= extract_tag_ids_from_text(text)
    return found


def is_code_evidence_path(rel: str) -> bool:
    """True if ``rel`` looks like product code (any folder; skips tests/vendor)."""
    parts = Path(rel).parts
    if not parts:
        return False
    if any(part in _SKIP_DIR_NAMES or part.startswith(".") for part in parts):
        return False
    if "Tests" in parts or "tests" in parts:
        return False
    name = parts[-1]
    if name.startswith("test_") or name.endswith("Tests.swift") or name.endswith("_test.py"):
        return False
    suffix = Path(name).suffix.lower()
    if suffix and suffix not in CODE_SUFFIXES:
        return False
    return True


def feature_fr_nfr_ids(feat: dict[str, Any]) -> set[str]:
    docs = feat.get("docs") or {}
    out: set[str] = set()
    if not isinstance(docs, dict):
        return out
    for key in ("fr", "nfr"):
        for raw in docs.get(key) or []:
            if isinstance(raw, str) and raw.startswith(("FR-", "NFR-")):
                out.add(raw.strip())
    return out


def audit_orphan_code_tags(catalog: dict[str, str]) -> list[Finding]:
    findings: list[Finding] = []
    for path in _iter_code_files(REPO_ROOT):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(path.relative_to(REPO_ROOT))
        for req_id in extract_tag_ids_from_text(text):
            if req_id not in catalog:
                findings.append(
                    Finding(
                        "warning",
                        "orphan_code_tags",
                        f"Tag {req_id} in {rel} not in docs catalog",
                        req_id=req_id,
                        evidence=[rel],
                    )
                )
    return findings


def audit_evidence_paths_missing_tags(
    features: list[Any],
) -> tuple[list[Finding], list[dict[str, Any]]]:
    findings: list[Finding] = []
    rows: list[dict[str, Any]] = []
    marker = tag_marker()
    for feat in features:
        if not isinstance(feat, dict):
            continue
        status = feat.get("status")
        if status not in {"partial", "done"}:
            continue
        fid = str(feat.get("id") or "")
        evidence = feat.get("evidence") or {}
        paths_any = evidence.get("paths_any") if isinstance(evidence, dict) else []
        if not isinstance(paths_any, list):
            continue
        wanted = feature_fr_nfr_ids(feat)
        for rel in paths_any:
            if not isinstance(rel, str) or not is_code_evidence_path(rel):
                continue
            base = REPO_ROOT / rel
            if not base.exists():
                continue
            if not list(_iter_code_files(base)):
                continue
            ids = path_tag_ids(rel)
            if not ids:
                sev = "warning" if status == "done" else "info"
                findings.append(
                    Finding(
                        sev,
                        "evidence_path_missing_tag",
                        f"{fid}: evidence path `{rel}` has no {marker} tag "
                        "(public anchor should be sparsely labeled)",
                        feature_id=fid,
                        evidence=[rel],
                    )
                )
                rows.append(
                    {
                        "feature_id": fid,
                        "path": rel,
                        "status": status,
                        "kind": "no_tag",
                        "wanted_ids": sorted(wanted),
                    }
                )
                continue
            if wanted and ids.isdisjoint(wanted):
                findings.append(
                    Finding(
                        "info",
                        "evidence_path_tag_mismatch",
                        f"{fid}: evidence path `{rel}` has {marker} tags {sorted(ids)[:5]} "
                        f"but none of mapped FR/NFR {sorted(wanted)[:5]}",
                        feature_id=fid,
                        evidence=[rel],
                    )
                )
                rows.append(
                    {
                        "feature_id": fid,
                        "path": rel,
                        "status": status,
                        "kind": "mismatch",
                        "found_ids": sorted(ids),
                        "wanted_ids": sorted(wanted),
                    }
                )
    return findings, rows
