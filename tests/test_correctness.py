"""Independent analytical and enumerated references, including adversarial boundaries."""

from __future__ import annotations

import copy
import io
import itertools
import json
import zipfile
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from invest_engine import load_case, optimise, screen, value_case, value_initiative
from invest_engine.ai_act import QUESTIONS, SYNTHETIC_FROM, SYNTHETIC_LEGACY_TRANSITION
from invest_engine.benefits import import_actuals, observation_template, track
from invest_engine.finance import OptionResult, breakeven_p_success
from invest_engine.portfolio import greedy, verify_choice
from invest_engine.reporting import bundle, memo, safe_csv, settings, tables
from invest_engine.roadmap import build_roadmap
from invest_engine.schema import CaseError, Dependency, Tri, validate
from invest_engine.service import analyse
from invest_engine.store import Store

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def small():
    c = copy.deepcopy(load_case(ROOT / "cases/dhl_supply_chain"))
    c.id, c.company, c.unit, c.title = "synthetic", "Synthetic Company", "Test", "Synthetic case"
    c.facts, c.sources = [], {}
    c.horizon_years, c.rollout_years, c.n_samples = 3, 1, 100
    c.discount_rate, c.volume_factor = 0.1, Tri(1, 1, 1)
    c.budget_by_year, c.fte_capacity_by_year = [180], [10]
    c.risk_aversion = 0
    c.initiatives = [
        replace(
            c.initiatives[0],
            id=key,
            name=key,
            status="new",
            sources=[],
            public_basis="",
            site_options=[0, 1, 2],
            capex_per_site=Tri(60, 60, 60),
            platform_capex=Tri(0, 0, 0),
            opex_per_site=Tri(10, 10, 10),
            benefit_per_site=Tri(b, b, b),
            months_to_value=Tri(0, 0, 0),
            ramp_years=0,
            p_success=1,
            fail_benefit_share=0,
            fte_per_site=1,
            central_fte=0,
            requires=[],
            ai_act=dict.fromkeys(QUESTIONS, False),
            committed_min_sites=0,
        )
        for key, b in [("A", 80), ("B", 70), ("C", 60)]
    ]
    return c


def test_analytical_cash_flows_and_discounting(small):
    i = small.initiatives[0]
    o = value_initiative(small, i)[1]
    # Deploy at Q1-end. The following 11 quarters each net (80-10)/4.
    assert np.allclose(o.cash_by_quarter, [-60] + [17.5] * 11)
    assert np.allclose(o.cash_by_year, [-7.5, 70, 70])
    expected = -60 / 1.1**0.25 + sum(17.5 / 1.1 ** (q / 4) for q in range(2, 13))
    assert o.mean == pytest.approx(expected)
    assert np.all(o.npv_samples == pytest.approx(expected))
    assert o.payback_year == 2


def test_delay_ramp_and_opex_schedules(small):
    i = replace(small.initiatives[0], months_to_value=Tri(12, 12, 12), ramp_years=1)
    o = value_initiative(small, i)[1]
    assert np.allclose(o.benefit_by_year, [0, 22.5, 77.5])
    assert np.allclose(o.cash_by_year, [-67.5, 12.5, 67.5])
    assert o.payback_year == 3


def test_platform_cost_and_no_investment(small):
    i = replace(small.initiatives[0], platform_capex=Tri(20, 20, 20))
    opts = value_initiative(small, i)
    assert opts[2].capex_by_year.sum() == 140
    assert opts[0].mean == 0
    assert opts[0].payback_year is None


def test_failure_probability_endpoints_and_threshold(small):
    i = replace(small.initiatives[0], fail_benefit_share=0)
    assert value_initiative(small, replace(i, p_success=0))[1].mean < 0
    be = breakeven_p_success(small, i, 1)
    success = value_initiative(small, replace(i, p_success=1))[1].mean
    failure = value_initiative(small, replace(i, p_success=0))[1].mean
    assert be * success + (1 - be) * failure == pytest.approx(0, abs=1e-9)


def test_payback_ignores_zero_flow_before_spend_and_later_relapse():
    o = OptionResult("X", 1, np.zeros(1), np.array([0, 10, 0]), np.zeros(3), np.zeros(3), np.array([0, -10, 20]))
    assert o.payback_year == 3
    o.cash_by_year = np.array([1, 1, -3])
    assert o.payback_year is None


@pytest.mark.parametrize("discount", [-1, -2, float("nan"), float("inf")])
def test_invalid_discount(small, discount):
    small.discount_rate = discount
    with pytest.raises(CaseError):
        value_case(small)


@pytest.mark.parametrize(
    "field,value",
    [
        ("ramp_years", -1),
        ("fte_per_site", -1),
        ("central_fte", float("nan")),
        ("fail_benefit_share", 1.01),
        ("p_success", -0.1),
        ("p_success", float("inf")),
    ],
)
def test_invalid_initiative_inputs(small, field, value):
    setattr(small.initiatives[0], field, value)
    with pytest.raises(CaseError):
        validate(small)


@pytest.mark.parametrize("values", [(2, 1, 3), (0, float("nan"), 1), (0, 1, float("inf"))])
def test_invalid_distributions(values):
    with pytest.raises(CaseError):
        Tri(*values)


def test_invalid_references_cycles_and_duplicates(small):
    small.initiatives[0].requires = [Dependency("UNKNOWN")]
    with pytest.raises(CaseError):
        validate(small)
    small.initiatives[0].requires = [Dependency("B")]
    small.initiatives[1].requires = [Dependency("A")]
    with pytest.raises(CaseError, match="cyclic"):
        validate(small)
    small.initiatives[0].requires = []
    small.initiatives[1].requires = []
    small.initiatives[1].id = "A"
    with pytest.raises(CaseError, match="duplicate"):
        validate(small)


@pytest.mark.parametrize(
    "field,value",
    [
        ("currency_unit", "USD m"),
        ("n_samples", 0),
        ("rollout_years", 0),
        ("seed", -1),
        ("budget_by_year", [-1]),
        ("fte_capacity_by_year", [float("inf")]),
        ("budget_by_year", [1, 2]),
    ],
)
def test_invalid_case_inputs(small, field, value):
    setattr(small, field, value)
    with pytest.raises(CaseError):
        validate(small)


def test_invalid_dates_and_fractional_periods(tmp_path):
    source = ROOT / "cases/dhl_supply_chain"
    c = yaml.safe_load((source / "case.yaml").read_text())
    (tmp_path / "initiatives.yaml").write_text((source / "initiatives.yaml").read_text())
    c["sources"]["S1"]["accessed"] = "yesterday"
    (tmp_path / "case.yaml").write_text(yaml.safe_dump(c))
    with pytest.raises(CaseError):
        load_case(tmp_path)
    c["sources"]["S1"]["accessed"] = "2026-11-14"
    c["model"]["horizon_years"] = 3.5
    (tmp_path / "case.yaml").write_text(yaml.safe_dump(c))
    with pytest.raises(CaseError):
        load_case(tmp_path)


@pytest.mark.parametrize("carryover", [False, True])
def test_solver_matches_exhaustive_reference_with_dependencies_and_mutex(small, carryover):
    small.initiatives[1].requires = [Dependency("A", "sites", 0)]
    small.initiatives[1].exclusive_group = "alternative"
    small.initiatives[2].exclusive_group = "alternative"
    vals, scr = value_case(small)
    best = -np.inf
    for sites in itertools.product([0, 1, 2], repeat=3):
        choice = dict(zip(["A", "B", "C"], sites))
        # Independent feasibility implementation, deliberately not solver helper.
        if sites[1] > sites[0] or (sites[1] and sites[2]):
            continue
        cost = sum(vals[k][v].capex_by_year[0] for k, v in choice.items())
        fte = sum(vals[k][v].fte_by_year[0] for k, v in choice.items())
        if cost > 180 or fte > 10:
            continue
        best = max(best, sum(vals[k][v].mean for k, v in choice.items()))
    p = optimise(small, vals, scr, carryover=carryover)
    assert p.status == "OPTIMAL" and p.relative_gap == 0
    assert p.score == pytest.approx(best)
    verify_choice(small, vals, scr, p.choice, carryover=carryover)
    assert p.choice == optimise(small, vals, scr, carryover=carryover).choice


def test_fractional_capex_does_not_round_into_budget(small):
    small.initiatives = small.initiatives[:1]
    small.initiatives[0].site_options = [0, 1]
    small.budget_by_year = [60]
    small.initiatives[0].capex_per_site = Tri(60.0001, 60.0001, 60.0001)
    vals, scr = value_case(small)
    assert optimise(small, vals, scr).choice["A"] == 0


def test_fractional_fte_does_not_round_into_capacity(small):
    small.fte_capacity_by_year = [4]  # quarter capacity = 1 FTE-year
    small.initiatives = small.initiatives[:1]
    small.initiatives[0].fte_per_site = 1.000001
    vals, scr = value_case(small)
    assert optimise(small, vals, scr).choice["A"] == 0


def test_infeasible_commitments_and_baseline_fail_safely(small):
    small.budget_by_year = [1]
    small.initiatives[0].committed_min_sites = 1
    vals, scr = value_case(small)
    with pytest.raises(RuntimeError, match="INFEASIBLE"):
        optimise(small, vals, scr)
    with pytest.raises(RuntimeError, match="exceeds"):
        greedy(small, vals, scr)


def test_excluded_committed_initiative_is_infeasible(small):
    small.initiatives[0].committed_min_sites = 1
    small.initiatives[0].ai_act = {}
    vals, scr = value_case(small)
    with pytest.raises(RuntimeError):
        optimise(small, vals, scr)


def test_pilot_gate_requires_approval_and_success(small):
    i = small.initiatives[0]
    i.pilot_gate = {"approved": False, "min_success_probability": 0.8}
    vals, scr = value_case(small)
    assert optimise(small, vals, scr).choice["A"] == 0
    i.pilot_gate.update(approved=True, reviewer="Test reviewer", evidence="Synthetic pilot", reviewed_at="2026-11-14")
    vals, scr = value_case(small)
    assert optimise(small, vals, scr).choice["A"] > 0
    i.p_success = 0.7
    vals, scr = value_case(small)
    assert optimise(small, vals, scr).choice["A"] == 0


def test_unknown_governance_and_strict_booleans():
    s = screen({})
    assert s.category == "unknown"
    assert s.excluded and s.unknown_questions and s.review_status == "pending human review"
    with pytest.raises(ValueError):
        screen({"uses_ai": "false"})
    assert SYNTHETIC_FROM == "2026-08-02"
    assert SYNTHETIC_LEGACY_TRANSITION == "2026-12-02"


def test_case_neutral_roadmap_capacity_and_global_site_limit(small):
    small.max_sites_per_quarter = 1
    vals, scr = value_case(small)
    p = optimise(small, vals, scr)
    rows, spill = build_roadmap(small, p, vals, scr)
    for q in range(1, 7):
        assert sum(r.sites for r in rows if r.quarter == q) <= 1
        assert sum(r.fte_used for r in rows if r.quarter == q) <= 2.5 + 1e-9
    assert sum(r.sites for r in rows) + sum(spill.values()) == sum(p.funded.values())


def test_current_settings_reach_scenarios_and_exports(small):
    a = analyse(small, budget_scale=0.5, discount=0.12, benefit_factor=0.8, extra_delay_months=3)
    assert a.case.budget_by_year == [90]
    assert a.scenarios.iloc[0].expected_npv == pytest.approx(a.portfolio.mean)
    assert tables(a)["cash_flows"].discounted_cash_EUR_k.sum() == pytest.approx(a.portfolio.mean)
    assert small.budget_by_year == [180]  # input not mutated
    with zipfile.ZipFile(io.BytesIO(bundle(a))) as z:
        state = json.loads(z.read("settings.json"))
        assert state["discount_rate"] == 0.12 and state["budget_by_year_EUR_k"] == [90]
        assert z.read("memo.md").decode() == memo(a)
        frame = pd.read_csv(z.open("portfolio.csv"))
        assert frame.npv_EUR_k.sum() == pytest.approx(a.portfolio.mean)
    assert len(a.scenarios) == 10


def test_empty_portfolio_exports_and_benefits(small):
    a = analyse(small, budget_scale=0)
    assert not a.portfolio.funded and a.benefits.empty
    assert bundle(a)
    assert "Fund 0" in memo(a)


def test_actuals_csv_validation_and_missing_periods(small):
    vals, scr = value_case(small)
    b = track(small, optimise(small, vals, scr), vals)
    i = b.initiative_id.iloc[0]
    template = observation_template(b)
    actuals = template[(template.initiative_id == i) & (template.quarter == 1)].copy()
    actuals["observed_benefit_EUR_k"] = 10.0
    actuals["source"] = "Synthetic ledger"
    actuals["observation_date"] = actuals.reporting_period_end
    actuals["confidence"] = "high"
    out = import_actuals(b, actuals, case=small)
    assert out.query("initiative_id == @i and quarter == 1").observed_benefit_EUR_k.iloc[0] == 10
    assert out.query("initiative_id == @i and quarter > 1").observed_benefit_EUR_k.isna().all()
    with pytest.raises(ValueError):
        import_actuals(b, pd.concat([actuals, actuals]), case=small)
    with pytest.raises(ValueError):
        import_actuals(b, actuals.assign(is_simulated="yes"), case=small)
    with pytest.raises(ValueError):
        import_actuals(b, actuals.assign(initiative_id="UNKNOWN"), case=small)
    assert import_actuals(b, actuals.assign(observed_benefit_EUR_k=-1), case=small).observed_benefit_EUR_k.min() == -1


def test_snapshot_roundtrip_and_review_boundaries(small, tmp_path):
    a = analyse(small)
    store = Store(tmp_path / "office.sqlite3")
    rid = store.save(a)
    assert store.load(rid) == bundle(a)
    with pytest.raises(KeyError):
        store.load("missing")
    with pytest.raises(ValueError):
        store.review(rid, "A", "", "Evidence", "approve assumptions", "Unknown")
    with pytest.raises(ValueError):
        store.review(rid, "UNKNOWN", "Test", "Evidence", "approve assumptions", "Unknown")
    store.review(rid, "A", "Test reviewer", "Synthetic evidence", "request changes", "Missing legal review")
    assert store.reviews(rid)[0]["reviewer"] == "Test reviewer"
    assert settings(a)["case"] == "synthetic"


def test_csv_formula_injection():
    output = safe_csv(pd.DataFrame({"value": ["=1+1", " +SUM(A1)", "@x", "-cmd", "ordinary", -2]}))
    assert "'=1+1" in output and "' +SUM" in output
    assert "ordinary" in output and "\n-2\n" in output


def test_empty_benefits_import_reports_unknown_ids(small):
    a = analyse(small, budget_scale=0)
    actuals = pd.DataFrame(
        [{
            "company_id": "synthetic", "initiative_id": "UNKNOWN", "quarter": 1,
            "reporting_period_end": "2025-03-31", "observed_benefit_EUR_k": 1, "currency": "EUR",
            "source": "Synthetic ledger", "observation_date": "2025-03-31", "confidence": "high",
            "revision": 1, "is_simulated": True,
        }]
    )
    with pytest.raises(ValueError, match="unknown"):
        import_actuals(a.benefits, actuals, case=small)


def test_review_service_cannot_approve_unknown_screening(small, tmp_path):
    a = analyse(small, overrides={"A": {}})
    store = Store(tmp_path / "office.sqlite3")
    rid = store.save(a)
    with pytest.raises(ValueError, match="cannot be approved"):
        store.review(rid, "A", "Reviewer", "Evidence", "approve assumptions", "Unknown use")
    store.review(rid, "A", "Reviewer", "Missing answers", "request changes", "Unknown use")
    assert store.reviews(rid)[0]["decision"] == "request changes"
