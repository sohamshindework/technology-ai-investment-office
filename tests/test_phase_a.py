"""Independent business-model audit and cross-case configuration/state boundaries."""

import copy
import io
import json
import zipfile
from pathlib import Path

import pytest
import yaml
from streamlit.testing.v1 import AppTest

from frontend import state
from frontend.components import View, rationale
from invest_engine import load_case
from invest_engine.ai_act import screen
from invest_engine.schema import CaseError, validate
from invest_engine.service import analyse
from scripts.validate_case import audit

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def dhl_analysis():
    return analyse(load_case(ROOT / "cases/dhl_supply_chain"))


@pytest.mark.parametrize("case_id", ["dhl_supply_chain", "synthetic"])
def test_independent_cash_flows_and_complete_enumeration(case_id, dhl_analysis):
    analysis = dhl_analysis if case_id == "dhl_supply_chain" else analyse(load_case(ROOT / "cases" / case_id))
    results = audit(analysis)
    assert results["independent_enumeration"]["feasible_portfolios"] > 0
    assert results["independent_enumeration"]["choice"] == analysis.portfolio.choice
    assert results["max_sample_error_EUR_k"] < 1e-7


def test_audit_does_not_claim_optimality_after_truncation():
    analysis = analyse(load_case(ROOT / "cases/synthetic"))
    with pytest.raises(RuntimeError, match="no optimality claim"):
        audit(analysis, max_nodes=1)


def test_audit_detects_a_corrupted_cash_flow(dhl_analysis):
    corrupted = copy.deepcopy(dhl_analysis)
    iid, sites = next(iter(corrupted.portfolio.funded.items()))
    corrupted.valuations[iid][sites].cash_by_quarter[0] += 1
    with pytest.raises(AssertionError):
        audit(corrupted)


def write_case(tmp_path, raw):
    (tmp_path / "case.yaml").write_text((ROOT / "cases/dhl_supply_chain/case.yaml").read_text())
    (tmp_path / "initiatives.yaml").write_text(yaml.safe_dump(raw))
    return tmp_path


@pytest.mark.parametrize("value", [1.9, True, "20"])
def test_yaml_commitment_must_not_be_silently_coerced(tmp_path, value):
    raw = yaml.safe_load((ROOT / "cases/dhl_supply_chain/initiatives.yaml").read_text())
    raw["initiatives"][0]["site_options"].append(1)
    raw["initiatives"][0]["committed_min_sites"] = value
    with pytest.raises(CaseError, match="committed_min_sites must be an integer"):
        load_case(write_case(tmp_path, raw))


@pytest.mark.parametrize("value", [1.0, True])
def test_programmatic_commitment_requires_a_genuine_integer(value, dhl_analysis):
    c = copy.deepcopy(dhl_analysis.case)
    c.initiatives[0].site_options = sorted(set(c.initiatives[0].site_options + [1]))
    c.initiatives[0].committed_min_sites = value
    with pytest.raises(CaseError, match="committed_min_sites must be an integer"):
        validate(c)


def test_unsupported_governance_key_is_rejected_on_load(tmp_path):
    raw = yaml.safe_load((ROOT / "cases/dhl_supply_chain/initiatives.yaml").read_text())
    raw["initiatives"][0]["ai_act"]["unsupported_sector_use"] = True
    with pytest.raises(CaseError, match="unsupported governance questions"):
        load_case(write_case(tmp_path, raw))


def test_unsupported_governance_key_is_rejected_by_screening(dhl_analysis):
    answers = {**dhl_analysis.case.initiatives[0].ai_act, "unsupported_sector_use": True}
    with pytest.raises(ValueError, match="unsupported governance questions"):
        screen(answers, dhl_analysis.case.compliance)


class Session(dict):
    """Small mapping with the same attribute syntax used by Streamlit state."""

    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


def test_case_switch_clears_colliding_ids_actuals_reviews_and_drafts(dhl_analysis):
    first = dhl_analysis.case
    second = copy.deepcopy(first)
    second.id, second.company, second.discount_rate = "synthetic", "Synthetic Company", 0.13
    session = Session(navigation="Decision Brief")
    state.initialize(session, "case_a", first)
    session.update(
        input_discount=99,
        question_INT_LAYER_uses_ai=True,
        review_name="Previous reviewer",
        review_runs={"old": "record"},
        benefits_actuals=b"previous data",
        benefits_import_error="old error",
        candidate_search="old search",
        research_proposal_json="old research proposal",
        overrides={"INT_LAYER": {"uses_ai": True}},
        previous_scenario={"choice": {"INT_LAYER": 70}},
        last_summary={"npv": 1},
        saved_state="old",
        saved_run="old-run-id",
    )
    session.active_config["discount"] = 0.49
    state.initialize(session, "case_b", second)
    assert session.active_config == state.defaults(second)
    assert session.overrides == {}
    assert session.previous_scenario is session.last_summary is session.saved_state is None
    assert "saved_run" not in session
    assert not any(
        key.startswith(("input_", "question_", "review_", "benefits_", "candidate_", "research_"))
        for key in session
    )
    assert session.navigation == "Decision Brief"
    assert first.discount_rate != session.active_config["discount"]


def test_sources_must_resolve_within_the_current_case(dhl_analysis):
    second = copy.deepcopy(dhl_analysis.case)
    second.id = "synthetic"
    second.sources = {}
    second.facts = []
    with pytest.raises(CaseError, match="not listed in case.yaml sources"):
        validate(second)


def test_enabler_rationale_does_not_claim_incremental_causality(dhl_analysis):
    v = View(dhl_analysis)
    assert dhl_analysis.portfolio.choice["AMR_PICK"] <= dhl_analysis.case.get("AMR_PICK").requires[0].baseline_sites
    text = rationale(v, dhl_analysis.case.get("INT_LAYER"))
    assert "reference this prerequisite" in text
    assert "Existing coverage" in text
    assert "Enables 2" not in text


def test_real_case_switch_excludes_previous_actuals_from_export(monkeypatch, dhl_analysis):
    from frontend.pages import brief
    from invest_engine.benefits import observation_template

    packs = []
    original = brief.bundle

    def capture(a):
        packs.append(original(a))
        return packs[-1]

    monkeypatch.setattr(brief, "bundle", capture)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45).run()
    raw = observation_template(dhl_analysis.benefits)
    raw["observed_benefit_EUR_k"] = 123.0
    raw["source"] = "Synthetic DHL test ledger"
    raw["observation_date"] = raw.reporting_period_end
    raw["confidence"] = "high"
    raw["is_simulated"] = False
    app.session_state["benefits_actuals"] = raw.to_csv(index=False).encode()
    app.session_state["review_name"] = "Previous reviewer"
    app.radio[0].set_value("Decision Brief").run()
    assert not app.exception
    with zipfile.ZipFile(io.BytesIO(packs[-1])) as pack:
        assert "benefits_REPORTED.csv" in pack.namelist()
    app.selectbox(key="case_selector").set_value(str(ROOT / "cases/allianz")).run()
    assert not app.exception
    assert "benefits_actuals" not in app.session_state
    assert "review_name" not in app.session_state
    with zipfile.ZipFile(io.BytesIO(packs[-1])) as pack:
        assert json.loads(pack.read("settings.json"))["case"] == "allianz"
        assert "benefits_REPORTED.csv" not in pack.namelist()
        assert "DHL Supply Chain" not in pack.read("memo.md").decode()
