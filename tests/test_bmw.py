"""BMW manufacturing admission, independent valuation and three-case isolation."""

import copy
import io
import json
import shutil
import zipfile
from pathlib import Path

import pytest
import yaml
from streamlit.testing.v1 import AppTest

from frontend.components import View, rationale
from invest_engine.case_config import admitted_cases
from invest_engine.reporting import bundle, memo, settings, tables
from invest_engine.schema import CaseError, load_case
from invest_engine.service import analyse
from scripts.validate_case import audit

ROOT = Path(__file__).resolve().parents[1]
BMW = ROOT / "cases/bmw_group"


@pytest.fixture(scope="module")
def bmw_analysis():
    return analyse(load_case(BMW))


def test_bmw_is_third_admitted_business_case(bmw_analysis):
    assert [p.name for p in admitted_cases(ROOT)] == ["dhl_supply_chain", "allianz", "bmw_group"]
    assert len(bmw_analysis.case.initiatives) == 10
    assert bmw_analysis.case.profile.industry_id == "automotive"


def test_bmw_independent_finance_schedule_and_optimum(bmw_analysis):
    a = bmw_analysis
    result = audit(a)
    assert result["max_sample_error_EUR_k"] < 1e-7
    assert result["independent_enumeration"]["choice"] == a.portfolio.choice
    assert result["independent_enumeration"]["feasible_portfolios"] > 0
    assert not a.spill
    assert sum(r.sites for r in a.roadmap) == sum(a.portfolio.choice.values())
    assert max(result["quarterly_deployments"]) <= a.case.max_sites_per_quarter
    t = tables(a)
    assert a.portfolio.mean == pytest.approx(t["quarterly_cash_flows"].discounted_cash_EUR_k.sum())
    assert t["cash_flows"].benefit_EUR_k.sum() == pytest.approx(t["quarterly_cash_flows"].benefit_EUR_k.sum())
    assert t["cash_flows"].capex_EUR_k.sum() == pytest.approx(t["quarterly_cash_flows"].capex_EUR_k.sum())


def test_bmw_profile_is_presentation_only(bmw_analysis):
    changed = copy.deepcopy(bmw_analysis.case)
    changed.profile.accent["primary"] = "#557399"
    changed.profile.kpis[0]["label"] = "Different display label"
    other = analyse(changed)
    assert other.portfolio.choice == bmw_analysis.portfolio.choice
    assert other.portfolio.mean == bmw_analysis.portfolio.mean
    assert tables(other)["quarterly_cash_flows"].equals(tables(bmw_analysis)["quarterly_cash_flows"])


def test_bmw_enabler_copy_reflects_zero_baseline_coverage(bmw_analysis):
    explanation = rationale(View(bmw_analysis), bmw_analysis.case.get("LINE_DATA"))
    assert "enabling rollout must complete" in explanation
    assert "Existing coverage" not in explanation


def test_bmw_downside_reoptimizes_and_exports_current_case(bmw_analysis):
    changed = analyse(load_case(BMW), benefit_factor=0.8)
    assert changed.portfolio.mean < bmw_analysis.portfolio.mean
    assert changed.portfolio.choice != bmw_analysis.portfolio.choice
    assert settings(changed)["case_profile"]["industry_id"] == "automotive"
    with zipfile.ZipFile(io.BytesIO(bundle(changed))) as pack:
        exported = pack.read("memo.md").decode()
        assert exported == memo(changed)
        assert "BMW Group" in exported
        assert "DHL Supply Chain" not in exported
        assert "Allianz" not in exported
        assert "line-workflow deployments" in exported
        assert json.loads(pack.read("settings.json"))["case"] == "bmw_group"
        for name, frame in tables(changed).items():
            assert pack.read(f"{name}.csv") == frame.to_csv(index=False).encode()


def test_committee_memo_labels_funded_choices_and_downside(bmw_analysis):
    document = memo(bmw_analysis)
    for initiative in bmw_analysis.case.initiatives:
        if bmw_analysis.portfolio.choice[initiative.id]:
            assert f"| {initiative.name} | fund |" in document
    assert "| Scenario | Status | Expected NPV | P10 NPV | Funded |" in document
    assert "| All benefits -30% |" in document
    assert "scheduled by Q5" in document


@pytest.mark.parametrize(
    ("filename", "path", "value", "message"),
    [
        ("profile.yaml", ("governance", "profile_id"), "workplace_v1", "manufacturing operations"),
        ("profile.yaml", ("governance", "domains"), ["workplace"], "automotive governance domains"),
        ("profile.yaml", ("kpis", 1, "denominator"), "", "kpi.denominator"),
        ("profile.yaml", ("kpis", 0, "unit"), "machine_hours", "KPI unit"),
        ("profile.yaml", ("views", "portfolio"), ["unsupported"], "unsupported chart"),
        ("evidence.yaml", ("claims", 0, "source_ids"), ["UNKNOWN"], "unknown source"),
        ("case.yaml", ("model", "machine_hour_capacity"), 100, "unsupported"),
    ],
)
def test_bmw_rejects_invalid_configuration(tmp_path, filename, path, value, message):
    for name in ("case.yaml", "initiatives.yaml", "profile.yaml", "evidence.yaml"):
        shutil.copy2(BMW / name, tmp_path / name)
    raw = yaml.safe_load((tmp_path / filename).read_text())
    target = raw
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    (tmp_path / filename).write_text(yaml.safe_dump(raw, sort_keys=False))
    with pytest.raises(CaseError, match=message):
        load_case(tmp_path)


def test_three_case_switch_resets_current_assumptions_actuals_reviews_and_saved_state():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    for case_name, expected_discount in (("dhl_supply_chain", 0.09), ("allianz", 0.10), ("bmw_group", 0.10), ("dhl_supply_chain", 0.09)):
        app.selectbox(key="case_selector").set_value(str(ROOT / "cases" / case_name)).run()
        assert not app.exception
        assert app.session_state.active_config["discount"] == expected_discount
        for page in ("Portfolio", "Scenario Lab", "Delivery Plan", "Decision Brief"):
            app.radio[0].set_value(page).run()
            assert not app.exception, (case_name, page)
            if page == "Portfolio":
                assert app.selectbox(key=f"candidate_inspect_{case_name}").value in {
                    i.id for i in load_case(ROOT / "cases" / case_name).initiatives
                }
        app.session_state["benefits_actuals"] = b"old actuals"
        app.session_state["review_name"] = "old reviewer"
        app.session_state["saved_state"] = {"old": True}
        app.session_state["overrides"] = {"old": {"uses_ai": True}}
        app.session_state["input_discount"] = 31
        next_case = {"dhl_supply_chain": "allianz", "allianz": "bmw_group", "bmw_group": "dhl_supply_chain"}[case_name]
        app.selectbox(key="case_selector").set_value(str(ROOT / "cases" / next_case)).run()
        assert not app.exception
        for key in ("benefits_actuals", "review_name", "saved_run"):
            assert key not in app.session_state or app.session_state[key] is None
        assert app.session_state.saved_state is None
        assert app.session_state.overrides == {}


def test_three_case_metadata_and_economics_are_distinct():
    cases = [load_case(ROOT / "cases" / name) for name in ("dhl_supply_chain", "allianz", "bmw_group")]
    assert len({c.id for c in cases}) == 3
    assert len({c.profile.deployment_unit["plural"] for c in cases}) == 3
    assert len({c.profile.accent["primary"] for c in cases}) == 3
    assert len({tuple(c.budget_by_year) for c in cases}) == 3
