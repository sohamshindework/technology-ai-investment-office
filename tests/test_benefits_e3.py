"""E3 benefits-realization validation, reconciliation and isolation tests."""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook
from pypdf import PdfReader

from invest_engine import excel_analysis, investment_committee_pdf, load_case
from invest_engine.benefits import (
    fictional_observations,
    follow_up_items,
    import_actuals,
    initiative_summary,
    observation_template,
    portfolio_summary,
    validate_observations,
)
from invest_engine.reporting import tables
from invest_engine.service import analyse

ROOT = Path(__file__).resolve().parents[1]
CASES = ("dhl_supply_chain", "allianz", "bmw_group")


def _analysis(case_id="dhl_supply_chain"):
    return analyse(load_case(ROOT / "cases" / case_id))


def _observations(a, *, quarters=None, amount=100.0, confidence="high"):
    frame = observation_template(a.benefits)
    if quarters is not None:
        frame = frame[frame.quarter.isin(quarters)].copy()
    frame["observed_benefit_EUR_k"] = amount
    frame["source"] = "Reviewed management benefits ledger"
    frame["observation_date"] = frame.reporting_period_end
    frame["confidence"] = confidence
    return frame


@pytest.mark.parametrize("case_id", CASES)
def test_all_cases_have_unavailable_observed_state_without_import(case_id):
    a = _analysis(case_id)
    summary = portfolio_summary(a.benefits)
    assert summary["observed"] is None
    assert summary["coverage"] == 0
    assert "benefits_UNAVAILABLE" in tables(a)
    assert not a.benefits.observed_benefit_EUR_k.notna().any()


def test_partial_observations_missing_periods_and_matched_plan_comparison():
    a = _analysis()
    observations = _observations(a, quarters=[1, 3], amount=75)
    tracked = import_actuals(a.benefits, observations, case=a.case)
    summary = portfolio_summary(tracked, 3)
    assert 0 < summary["coverage"] < 1
    assert summary["observed"] == pytest.approx(len(observations) * 75)
    assert summary["planned"] == pytest.approx(
        tracked.loc[tracked.observed_benefit_EUR_k.notna(), "planned_benefit"].sum()
    )
    detail = initiative_summary(tracked, 3)
    assert detail.missing_periods.str.contains("Q2").all()
    assert any("Complete" in item for item in follow_up_items(tracked, 3))


def test_validation_rejects_duplicates_wrong_company_currency_and_bad_periods():
    a = _analysis("allianz")
    valid = _observations(a, quarters=[1]).head(1)
    with pytest.raises(ValueError, match="duplicate"):
        validate_observations(pd.concat([valid, valid]), a.case)
    with pytest.raises(ValueError, match="company_id"):
        validate_observations(valid.assign(company_id="dhl_supply_chain"), a.case)
    with pytest.raises(ValueError, match="currency"):
        validate_observations(valid.assign(currency="USD"), a.case)
    with pytest.raises(ValueError, match="quarter-end"):
        validate_observations(valid.assign(reporting_period_end="2025-03-30"), a.case)
    two_periods = _observations(a, quarters=[1, 2]).groupby("quarter", as_index=False).head(1)
    misaligned = two_periods.copy()
    misaligned.loc[misaligned.quarter == 2, "reporting_period_end"] = "2025-09-30"
    misaligned.loc[misaligned.quarter == 2, "observation_date"] = "2025-09-30"
    with pytest.raises(ValueError, match="aligned"):
        validate_observations(misaligned, a.case)
    with pytest.raises(ValueError, match="precede"):
        validate_observations(valid.assign(observation_date="2025-03-01"), a.case)


def test_zero_negative_revisions_and_material_deviations_are_explicit():
    a = _analysis("bmw_group")
    base = _observations(a, quarters=[2]).head(1)
    zero = import_actuals(a.benefits, base.assign(observed_benefit_EUR_k=0), case=a.case)
    assert zero.observed_benefit_EUR_k.dropna().iloc[0] == 0
    negative = import_actuals(a.benefits, base.assign(observed_benefit_EUR_k=-25), case=a.case)
    assert negative.observed_benefit_EUR_k.dropna().iloc[0] == -25

    first = import_actuals(a.benefits, base.assign(observed_benefit_EUR_k=10, revision=1), case=a.case)
    revised = import_actuals(a.benefits, base.assign(observed_benefit_EUR_k=250, revision=2), case=a.case)
    assert first.observed_benefit_EUR_k.dropna().iloc[0] == 10
    assert revised.observed_benefit_EUR_k.dropna().iloc[0] == 250
    assert revised.revision.dropna().iloc[0] == 2

    plan_value = float(base.merge(a.benefits, on=["company_id", "initiative_id", "quarter"]).planned_benefit.iloc[0])
    material = import_actuals(
        a.benefits,
        base.assign(observed_benefit_EUR_k=plan_value + max(100, abs(plan_value) * 0.3)),
        case=a.case,
    )
    assert initiative_summary(material).material_deviation.any()


def test_observations_do_not_change_financial_recommendation():
    a = _analysis()
    choice = a.portfolio.choice.copy()
    npv = a.portfolio.mean
    capex = a.portfolio.capex_by_year.copy()
    a.benefits = import_actuals(a.benefits, _observations(a, quarters=[1, 2]), case=a.case)
    assert a.portfolio.choice == choice
    assert a.portfolio.mean == npv
    assert a.portfolio.capex_by_year.tolist() == capex.tolist()


def test_excel_pdf_and_data_pack_reconcile_with_observations():
    a = _analysis("allianz")
    observations = _observations(a, quarters=[1, 2], amount=80, confidence="low")
    a.benefits = import_actuals(a.benefits, observations, case=a.case)
    summary = portfolio_summary(a.benefits)
    assert "benefits_REPORTED" in tables(a)

    xlsx = excel_analysis(a)
    workbook = load_workbook(io.BytesIO(xlsx), data_only=True)
    delivery_values = [cell.value for row in workbook["Delivery Plan"].iter_rows() for cell in row]
    assert "Observed benefits (EUR k)" in delivery_values
    assert any(
        value == pytest.approx(summary["observed"])
        for value in delivery_values
        if isinstance(value, (int, float))
    )

    pdf = investment_committee_pdf(a)
    reader = PdfReader(io.BytesIO(pdf))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Benefits realization" in text
    assert f"EUR {summary['observed'] / 1000:,.1f}m" in text
    assert "multiple causes" in text
    assert excel_analysis(a) == xlsx
    assert investment_committee_pdf(a) == pdf


def test_fictional_example_is_labeled_and_cross_case_rejected():
    dhl = _analysis()
    example = fictional_observations(dhl.benefits)
    tracked = import_actuals(dhl.benefits, example, case=dhl.case)
    assert tracked.is_simulated.dropna().all()
    assert set(initiative_summary(tracked).observation_type) == {"Fictional demonstration"}
    allianz = _analysis("allianz")
    with pytest.raises(ValueError, match="company_id"):
        import_actuals(allianz.benefits, example, case=allianz.case)
