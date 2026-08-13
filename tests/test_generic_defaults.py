"""Stack-agnostic defaults (no product folder assumptions)."""

from __future__ import annotations

from pulse_lib import cleancode as cc
from pulse_lib.tag_audit import code_roots


def test_default_code_roots_is_src_only(monkeypatch, tmp_path):
    # No _meta → fallback roots
    from pulse_lib import tag_audit

    monkeypatch.setattr(tag_audit, "META_PATH", tmp_path / "missing.yaml")
    assert code_roots() == ["src"]


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
    from pathlib import Path

    assert cc._loc_budget_for(Path("a.py"), {}) == 300
    assert cc._loc_budget_for(Path("a.swift"), {}) == 400
    assert cc._loc_budget_for(Path("a.ts"), {}) == 350
    assert cc._loc_budget_for(Path("a.py"), {"loc_budget": 120}) == 120
