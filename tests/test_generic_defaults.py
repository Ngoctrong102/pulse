"""Stack-agnostic defaults (no product folder assumptions)."""

from __future__ import annotations

from pathlib import Path

from pulse_lib import cleancode as cc
from pulse_lib.tag_audit import is_code_evidence_path, scan_code_tags


def test_scan_finds_tags_outside_src(monkeypatch, tmp_path: Path):
    from pulse_lib import tag_audit

    (tmp_path / "services" / "api").mkdir(parents=True)
    (tmp_path / "services" / "api" / "main.py").write_text(
        "# DEMO: FR-001\n", encoding="utf-8"
    )
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "ignored.py").write_text(
        "# DEMO: FR-999\n", encoding="utf-8"
    )
    monkeypatch.setattr(tag_audit, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(tag_audit, "META_PATH", tmp_path / "missing.yaml")
    monkeypatch.setattr(tag_audit, "tag_prefix", lambda: "DEMO")

    hits = scan_code_tags()
    assert hits.get("FR-001") == ["services/api/main.py"]
    assert "FR-999" not in hits


def test_is_code_evidence_path_accepts_any_tree():
    assert is_code_evidence_path("packages/web/app.ts")
    assert is_code_evidence_path("backend/main.go")
    assert not is_code_evidence_path("docs/readme.md")
    assert not is_code_evidence_path("src/tests/foo.py")
    assert not is_code_evidence_path("node_modules/pkg/index.js")


def test_cleancode_accepts_freeform_area():
    mods = [
        {
            "id": "web-app",
            "area": "web",
            "globs": ["src/**"],
            "score": None,
            "findings": [],
        }
    ]
    assert cc.validate_modules(mods) == []


def test_cleancode_rejects_empty_area():
    mods = [{"id": "x", "area": "", "globs": ["src/**"], "findings": []}]
    errs = cc.validate_modules(mods)
    assert any("area" in e for e in errs)


def test_loc_budget_by_extension():
    assert cc._loc_budget_for(Path("a.py"), {}) == 300
    assert cc._loc_budget_for(Path("a.swift"), {}) == 400
    assert cc._loc_budget_for(Path("a.ts"), {}) == 350
    assert cc._loc_budget_for(Path("a.py"), {"loc_budget": 120}) == 120
