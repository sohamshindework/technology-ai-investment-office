"""Export branding must agree across cases without changing numerical table schemas."""

import io
import json
import zipfile
from pathlib import Path

import pytest

from invest_engine import load_case
from invest_engine.reporting import bundle, memo, settings
from invest_engine.service import analyse

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("case_id", ["dhl_supply_chain", "synthetic"])
def test_current_export_identity(case_id):
    a = analyse(load_case(ROOT / "cases" / case_id))
    title = "Technology & AI Investment Strategy"
    subtitle = "Portfolio Optimization · Financial Modeling · Scenario Planning"
    document = memo(a)
    assert document.startswith(f"# {title}\n\n{subtitle}\n")
    assert f"## Investment committee memo — {a.case.title}" in document
    metadata = settings(a)
    assert metadata["project_title"] == title
    assert metadata["project_subtitle"] == subtitle
    assert metadata["case_title"] == a.case.title
    with zipfile.ZipFile(io.BytesIO(bundle(a))) as pack:
        assert pack.read("memo.md").decode() == document
        assert json.loads(pack.read("settings.json")) == metadata
    if case_id == "dhl_supply_chain":
        assert a.case.title == "DHL Supply Chain — Logistics & Automation"
        assert metadata["company"] == "DHL Supply Chain"
