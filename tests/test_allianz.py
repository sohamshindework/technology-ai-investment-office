"""Allianz admission, common-engine valuation and four-workflow regressions."""

import copy
import io
import json
import shutil
import zipfile
from pathlib import Path

import pytest
import yaml
from streamlit.testing.v1 import AppTest

from invest_engine.case_config import admitted_cases, case_fingerprint
from invest_engine.reporting import bundle, memo, settings, tables
from invest_engine.schema import CaseError, load_case
from invest_engine.service import analyse
from scripts.validate_case import audit

ROOT = Path(__file__).resolve().parents[1]
ALLIANZ = ROOT / "cases/allianz"


@pytest.fixture(scope="module")
def allianz_analysis():
    return analyse(load_case(ALLIANZ))


def test_catalog_admits_three_complete_business_cases():
    assert [p.name for p in admitted_cases(ROOT)] == ["dhl_supply_chain", "allianz", "bmw_group"]


def test_profile_and_evidence_changes_invalidate_case_identity(tmp_path):
    for name in ("case.yaml", "initiatives.yaml", "profile.yaml", "evidence.yaml"):
        shutil.copy2(ALLIANZ / name, tmp_path / name)
    before = case_fingerprint(tmp_path, "quarterly-cohorts-v1")
    profile = yaml.safe_load((tmp_path / "profile.yaml").read_text())
    profile["accent"]["primary"] = "#557399"
    (tmp_path / "profile.yaml").write_text(yaml.safe_dump(profile, sort_keys=False))
    assert case_fingerprint(tmp_path, "quarterly-cohorts-v1") != before
    before = case_fingerprint(tmp_path, "quarterly-cohorts-v1")
    evidence = yaml.safe_load((tmp_path / "evidence.yaml").read_text())
    evidence["assumptions"][0]["rationale"] += " Updated review."
    (tmp_path / "evidence.yaml").write_text(yaml.safe_dump(evidence, sort_keys=False))
    assert case_fingerprint(tmp_path, "quarterly-cohorts-v1") != before


@pytest.mark.parametrize("folder", ["../allianz", "dhl_supply_chain"])
def test_catalog_rejects_path_traversal_or_duplicate_folder(tmp_path, folder):
    cases = tmp_path / "cases"
    cases.mkdir()
    raw = yaml.safe_load((ROOT / "cases/catalog.yaml").read_text())
    for entry in raw["cases"]:
        entry["admission"] = "planned"
    raw["cases"][1]["folder"] = folder
    (cases / "catalog.yaml").write_text(yaml.safe_dump(raw, sort_keys=False))
    with pytest.raises(CaseError, match="invalid folder"):
        admitted_cases(tmp_path)


def test_allianz_independent_finance_capacity_dependency_and_optimum(allianz_analysis):
    a = allianz_analysis
    result = audit(a)
    assert len(a.case.initiatives) == 10
    assert a.case.profile.industry_id == "insurance"
    assert result["max_sample_error_EUR_k"] < 1e-7
    assert result["independent_enumeration"]["choice"] == a.portfolio.choice
    assert result["independent_enumeration"]["feasible_portfolios"] > 0
    assert not a.spill
    assert sum(r.sites for r in a.roadmap) == sum(a.portfolio.choice.values())
    assert max(result["quarterly_deployments"]) <= a.case.max_sites_per_quarter
    assert a.portfolio.mean == pytest.approx(tables(a)["quarterly_cash_flows"].discounted_cash_EUR_k.sum())


def test_allianz_case_profile_does_not_change_valuation(allianz_analysis):
    changed = copy.deepcopy(allianz_analysis.case)
    changed.profile.accent["primary"] = "#557399"
    changed.profile.kpis[0]["label"] = "Different display label"
    alternative = analyse(changed)
    assert alternative.portfolio.choice == allianz_analysis.portfolio.choice
    assert alternative.portfolio.mean == allianz_analysis.portfolio.mean
    assert tables(alternative)["quarterly_cash_flows"].equals(tables(allianz_analysis)["quarterly_cash_flows"])


def test_allianz_changed_benefits_reoptimise_and_export_current_state(allianz_analysis):
    changed = analyse(load_case(ALLIANZ), benefit_factor=0.8)
    assert changed.portfolio.mean != allianz_analysis.portfolio.mean
    assert settings(changed)["case_profile"]["industry_id"] == "insurance"
    with zipfile.ZipFile(io.BytesIO(bundle(changed))) as pack:
        assert json.loads(pack.read("settings.json"))["case"] == "allianz"
        assert pack.read("memo.md").decode() == memo(changed)
        assert "DHL Supply Chain" not in pack.read("memo.md").decode()
        assert b"team-workflow deployments" in pack.read("memo.md")


@pytest.mark.parametrize(
    ("filename", "path", "value", "message"),
    [
        ("profile.yaml", ("schema_version",), 2, "schema_version"),
        ("profile.yaml", ("accent", "primary"), "red", "accent"),
        ("profile.yaml", ("kpis", 0, "unit"), "unknown", "KPI unit"),
        ("profile.yaml", ("kpis", 2, "denominator"), "", "kpi.denominator"),
        ("profile.yaml", ("kpis", 0, "initiative_ids"), ["DHL_ONLY"], "unknown initiative"),
        ("profile.yaml", ("governance", "profile_id"), "workplace_v1", "insurance operations"),
        ("profile.yaml", ("views", "portfolio"), ["not_a_chart"], "unsupported chart"),
        ("evidence.yaml", ("claims", 0, "source_ids"), ["DHL_SOURCE"], "unknown source"),
        ("case.yaml", ("model", "regulatory_capital"), 1000, "unsupported"),
    ],
)
def test_allianz_admission_rejects_invalid_configuration(tmp_path, filename, path, value, message):
    for name in ("case.yaml", "initiatives.yaml", "profile.yaml", "evidence.yaml"):
        shutil.copy2(ALLIANZ / name, tmp_path / name)
    raw = yaml.safe_load((tmp_path / filename).read_text())
    target = raw
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    (tmp_path / filename).write_text(yaml.safe_dump(raw, sort_keys=False))
    with pytest.raises(CaseError, match=message):
        load_case(tmp_path)


def test_allianz_four_pages_and_switch_isolation(allianz_analysis):
    from invest_engine.benefits import observation_template

    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    app.selectbox(key="case_selector").set_value(str(ALLIANZ)).run()
    assert not app.exception
    assert app.session_state.active_config["discount"] == 0.10
    actuals = observation_template(allianz_analysis.benefits)
    actuals["observed_benefit_EUR_k"] = 12.0
    actuals["source"] = "Synthetic Allianz test ledger"
    actuals["observation_date"] = actuals.reporting_period_end
    actuals["confidence"] = "high"
    actuals["is_simulated"] = False
    app.session_state["benefits_actuals"] = actuals.to_csv(index=False).encode()
    app.session_state["review_name"] = "Previous reviewer"
    for page in ("Scenario Lab", "Delivery Plan", "Decision Brief", "Portfolio"):
        app.radio[0].set_value(page).run()
        assert not app.exception, page
    app.selectbox(key="case_selector").set_value(str(ROOT / "cases/dhl_supply_chain")).run()
    assert not app.exception
    assert "benefits_actuals" not in app.session_state
    assert "review_name" not in app.session_state
    assert app.session_state.active_config["discount"] == 0.09
    app.selectbox(key="case_selector").set_value(str(ALLIANZ)).run()
    assert not app.exception
    assert app.session_state.active_config["discount"] == 0.10
