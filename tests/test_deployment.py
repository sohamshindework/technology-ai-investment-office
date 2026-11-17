"""Quarterly feasibility and independent cash-flow/dependency regression references."""

from __future__ import annotations

import copy
import itertools
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from invest_engine import build_roadmap, load_case, optimise, value_case, value_initiative
from invest_engine.benefits import track
from invest_engine.portfolio import greedy, verify_choice
from invest_engine.reporting import memo, settings, tables
from invest_engine.schema import CaseError, Dependency, Tri, validate
from invest_engine.service import analyse

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def simple():
    c = load_case(ROOT / "cases/synthetic")
    c.n_samples = 32
    c.max_sites_per_quarter = 8
    return c


def test_integer_cohorts_and_completion_convention(simple):
    i = simple.initiatives[0]
    i.site_options = [0, 5]
    o = value_initiative(simple, i)[5]
    assert o.deployment.sites.tolist() == [2, 1, 1, 1] + [0] * 8
    # At Q1-end, two deployments complete; operation begins Q2.
    assert o.benefit_by_quarter[0] == 0
    assert o.benefit_by_quarter[1] == 40
    assert o.capex_by_quarter[:4].tolist() == [120, 60, 60, 60]
    assert np.allclose(o.cash_by_year, o.cash_by_quarter.reshape(3, 4).sum(axis=1))


def test_intrinsic_benefit_delay_and_quarterly_discounting(simple):
    i = simple.initiatives[0]
    i.months_to_value = Tri(3, 3, 3)
    o = value_initiative(simple, i)[1]
    reference = [-60, -2.5] + [17.5] * 10
    expected = sum(cash / 1.1 ** ((q + 1) / 4) for q, cash in enumerate(reference))
    assert np.allclose(o.cash_by_quarter, reference)
    assert o.mean == pytest.approx(expected)
    assert o.discounted_cash_by_year.sum() == pytest.approx(expected)


def test_compliance_lead_is_a_gate_and_not_counted_twice(simple):
    i = simple.initiatives[0]
    i.ai_act.update(allocates_tasks_individual_behaviour=True)
    simple.compliance = {"high_risk_delay_months": 6, "high_risk_capex": 0}
    i.central_fte = 4
    values, _ = value_case(simple)
    o = values[i.id][1]
    assert o.deployment.gates[:4].tolist() == [True, True, False, False]
    assert o.deployment.sites[:4].tolist() == [0, 0, 1, 0]
    assert o.deployment.fte[:4].tolist() == [1, 1, 2, 0]
    assert np.allclose(o.cash_by_quarter, [0, 0, -60] + [17.5] * 9)
    assert o.benefit_by_quarter[3] == 20  # not delayed again by another six months


def test_final_coverage_is_insufficient_without_quarterly_coverage(simple):
    a, b = simple.initiatives[:2]
    simple.initiatives = [a, b]
    simple.budget_by_year = [10000]
    simple.fte_capacity_by_year = [100]
    a.site_options, a.committed_min_sites = [0, 1], 1
    a.ai_act["safety_component_regulated_product"] = True
    simple.compliance = {"product_route_capex": 0}
    b.site_options, b.committed_min_sites = [0, 2], 2
    b.requires = [Dependency(a.id, "sites", 1)]
    values, screenings = value_case(simple)
    assert 2 <= 1 + 1  # final coverage would have passed the old model
    with pytest.raises(RuntimeError, match="quarterly dependency"):
        verify_choice(simple, values, screenings, {a.id: 1, b.id: 2})
    with pytest.raises(RuntimeError, match="INFEASIBLE"):
        optimise(simple, values, screenings)


def test_any_dependency_requires_preceding_quarter(simple):
    a, b = simple.initiatives[:2]
    simple.initiatives = [a, b]
    b.requires = [Dependency(a.id)]
    values, screenings = value_case(simple)
    p = optimise(simple, values, screenings)
    rows, _ = build_roadmap(simple, p, values, screenings)
    first_a = min(r.quarter for r in rows if r.initiative_id == a.id and r.sites)
    first_b = min(r.quarter for r in rows if r.initiative_id == b.id and r.sites)
    assert first_b > first_a


def test_global_deployment_capacity_can_make_annual_feasible_commitments_infeasible(simple):
    simple.initiatives = simple.initiatives[:2]
    simple.max_sites_per_quarter = 1
    simple.budget_by_year = [1000]
    simple.fte_capacity_by_year = [100]
    for i in simple.initiatives:
        i.site_options, i.committed_min_sites = [0, 2], 2
    values, screenings = value_case(simple)
    with pytest.raises(RuntimeError, match="INFEASIBLE"):
        optimise(simple, values, screenings)
    with pytest.raises(RuntimeError, match="quarterly deployment"):
        greedy(simple, values, screenings)


def test_quarterly_fte_includes_central_effort(simple):
    simple.initiatives = simple.initiatives[:1]
    simple.fte_capacity_by_year = [4]  # one FTE-year per quarter
    simple.initiatives[0].central_fte = 0.04  # 0.01 plus site effort 1 exceeds Q1
    values, screenings = value_case(simple)
    assert optimise(simple, values, screenings).funded == {}


@pytest.mark.parametrize("carryover", [False, True])
def test_small_quarterly_model_matches_exhaustive_enumeration(simple, carryover):
    simple.max_sites_per_quarter = 1
    simple.initiatives[1].requires = [Dependency("A", "sites", 0)]
    simple.initiatives[1].exclusive_group = "alternatives"
    simple.initiatives[2].exclusive_group = "alternatives"
    values, screenings = value_case(simple)
    best = -np.inf
    for sites in itertools.product([0, 1, 2], repeat=3):
        if sites[1] and sites[2]:
            continue
        options = [values[i.id][s] for i, s in zip(simple.initiatives, sites)]
        # Deliberately independent from verify_choice and solver construction.
        if sum(o.capex_by_year[0] for o in options) > 180:
            continue
        if any(sum(o.deployment.sites[q] for o in options) > 1 for q in range(4)):
            continue
        if any(sum(o.deployment.fte[q] for o in options) > 2.5 for q in range(4)):
            continue
        if any(sum(options[1].deployment.sites[: q + 1]) > sum(options[0].deployment.sites[:q]) for q in range(4)):
            continue
        best = max(best, sum(o.mean for o in options))
    p = optimise(simple, values, screenings, carryover=carryover)
    assert p.status == "OPTIMAL" and p.relative_gap == 0
    assert p.score == pytest.approx(best)


def test_timing_changes_revalue_cost_benefit_and_selection(simple):
    a = analyse(simple)
    delayed = analyse(simple, extra_delay_months=3)
    assert delayed.case.deployment_delay_quarters == 1
    old, new = a.valuations["A"][1], delayed.valuations["A"][1]
    assert old.capex_by_quarter[0] == 60 and new.capex_by_quarter[0] == 0
    assert new.capex_by_quarter[1] == 60
    assert new.benefit_by_quarter[1] == 0
    assert old.mean != new.mean
    assert delayed.scenarios.iloc[0].expected_npv == pytest.approx(delayed.portfolio.mean)
    assert simple.deployment_delay_quarters == 0  # input is not mutated


def test_exhausted_rollout_window_never_creates_free_investments(simple):
    simple.deployment_delay_quarters = 4
    values, screenings = value_case(simple)
    p = optimise(simple, values, screenings)
    assert not p.funded
    assert not values["A"][1].deployment.valid
    simple.initiatives[0].committed_min_sites = 1
    with pytest.raises(RuntimeError, match="INFEASIBLE"):
        optimise(simple, values, screenings)


@pytest.mark.parametrize("delay", [-1, 0.5, True])
def test_invalid_deployment_delay(simple, delay):
    simple.deployment_delay_quarters = delay
    with pytest.raises(CaseError):
        validate(simple)


def test_changing_capacity_invalidates_a_stale_portfolio(simple):
    values, screenings = value_case(simple)
    p = optimise(simple, values, screenings)
    simple.max_sites_per_quarter = 1
    with pytest.raises(RuntimeError, match="quarterly deployment"):
        build_roadmap(simple, p, values, screenings)


def test_dhl_schedule_valuation_tracking_exports_and_division_scope():
    a = analyse(load_case(ROOT / "cases/dhl_supply_chain"))
    c, p = a.case, a.portfolio
    assert c.company == "DHL Supply Chain"
    assert sum(c.budget_by_year) == 60000
    assert a.spill == {}
    first_six, remaining = build_roadmap(c, p, a.valuations, a.screenings)
    assert first_six == [r for r in a.roadmap if r.quarter <= 6]
    assert sum(remaining.values()) + sum(r.sites for r in first_six) == sum(p.funded.values())
    assert sum(r.sites for r in a.roadmap) == sum(p.funded.values()) <= 96
    for q in range(12):
        rows = [r for r in a.roadmap if r.quarter == q + 1]
        assert sum(r.sites for r in rows) <= 8
        assert sum(r.fte_used for r in rows) <= c.fte_capacity_by_year[q // 4] / 4 + 1e-9
        for iid, sites in p.funded.items():
            option = a.valuations[iid][sites]
            assert sum(r.sites for r in rows if r.initiative_id == iid) == option.deployment.sites[q]
            for d in c.get(iid).requires:
                previous = a.valuations[d.initiative][p.choice[d.initiative]].deployment.sites[:q].sum()
                if d.mode == "sites":
                    assert option.deployment.sites[: q + 1].sum() <= d.baseline_sites + previous
    t = tables(a)
    assert t["cash_flows"].discounted_cash_EUR_k.sum() == pytest.approx(p.mean)
    assert t["quarterly_cash_flows"].discounted_cash_EUR_k.sum() == pytest.approx(p.mean)
    b = track(c, p, a.valuations, quarters_elapsed=32)
    for iid, sites in p.funded.items():
        assert b[b.initiative_id == iid].planned_benefit.tolist() == pytest.approx(
            a.valuations[iid][sites].benefit_by_quarter
        )
    assert memo(a).startswith("# Technology & AI Investment Strategy\n")
    assert "## Investment committee memo — DHL Supply Chain — Logistics & Automation" in memo(a)
    assert "same quarterly cohorts" in memo(a).lower()
    assert settings(a)["max_sites_per_quarter"] == 8
    assert settings(a)["company"] == c.company
    # Renaming scope metadata alone cannot alter the underlying economics.
    renamed = copy.deepcopy(c)
    renamed.company = "Alternate presentation label"
    values, _ = value_case(renamed)
    assert sum(values[i][s].mean for i, s in p.choice.items()) == pytest.approx(p.mean)
    assert not pd.DataFrame(a.roadmap).empty
