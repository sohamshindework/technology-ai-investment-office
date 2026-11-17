from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from invest_engine import (
    build_roadmap,
    greedy,
    load_case,
    optimise,
    screen,
    track,
    value_case,
)
from invest_engine.ai_act import ANNEX_III_FROM
from invest_engine.finance import (
    breakeven_p_success,
    rollout_schedule,
    value_initiative,
)
from invest_engine.schema import CaseError

ROOT = Path(__file__).resolve().parents[1]
CASES = [p for p in (ROOT / "cases").iterdir() if (p / "case.yaml").exists()]


@pytest.fixture(scope="module")
def dhl():
    case = load_case(ROOT / "cases" / "dhl_supply_chain")
    case.n_samples = 1500
    vals, scr = value_case(case)
    return case, vals, scr


# ---------- case files ----------
@pytest.mark.parametrize("folder", CASES, ids=lambda p: p.name)
def test_every_case_loads_and_cites_known_sources(folder):
    case = load_case(folder)
    assert case.initiatives
    for ini in case.initiatives:
        assert set(ini.sources) <= set(case.sources)


def test_bad_source_is_rejected(tmp_path):
    src = ROOT / "cases" / "dhl_supply_chain"
    (tmp_path / "case.yaml").write_text((src / "case.yaml").read_text())
    import yaml

    data = yaml.safe_load((src / "initiatives.yaml").read_text())
    data["initiatives"][0]["sources"] = ["S99"]
    (tmp_path / "initiatives.yaml").write_text(yaml.safe_dump(data))
    with pytest.raises(CaseError):
        load_case(tmp_path)


def test_public_status_is_labelled(dhl):
    case, _, _ = dhl
    for ini in case.initiatives:
        if ini.status in {"scale", "graduate"}:
            assert ini.sources, f"{ini.id} claims a public basis without a source"


# ---------- finance ----------
def test_rollout_schedule_sums_to_sites():
    assert rollout_schedule(10, 3, 8).sum() == 10
    assert list(rollout_schedule(10, 3, 8)[:3]) == [4, 3, 3]
    assert rollout_schedule(0, 3, 8).sum() == 0


def test_zero_sites_is_zero_value(dhl):
    _, vals, _ = dhl
    for opts in vals.values():
        assert opts[0].mean == 0 and opts[0].capex_by_year.sum() == 0


def test_more_sites_more_capex(dhl):
    case, vals, _ = dhl
    for ini in case.initiatives:
        caps = [vals[ini.id][s].capex_by_year.sum() for s in ini.site_options]
        assert caps == sorted(caps)


def test_valuation_is_reproducible(dhl):
    case, vals, scr = dhl
    ini = case.get("AMR_PICK")
    again = value_initiative(case, ini, scr["AMR_PICK"])
    assert np.allclose(again[20].npv_samples, vals["AMR_PICK"][20].npv_samples)


def test_success_probability_raises_value(dhl):
    case, _, scr = dhl
    ini = case.get("ADAPTIVE_ROBOTICS")
    lo = value_initiative(case, replace(ini, p_success=0.3), scr[ini.id])[6].mean
    hi = value_initiative(case, replace(ini, p_success=0.9), scr[ini.id])[6].mean
    assert hi > lo


def test_breakeven_probability_is_between_0_and_1(dhl):
    case, _, scr = dhl
    p = breakeven_p_success(case, case.get("ADAPTIVE_ROBOTICS"), 6, scr["ADAPTIVE_ROBOTICS"])
    assert p is None or 0 < p < 1


# ---------- portfolio ----------
def test_optimiser_respects_budget_capacity_and_dependencies(dhl):
    case, vals, scr = dhl
    p = optimise(case, vals, scr)
    for y, b in enumerate(case.budget_by_year):
        assert p.capex_by_year[y] <= b + 1  # integer rounding tolerance (EUR k)
        assert p.fte_by_year[y] <= case.fte_capacity_by_year[y] + 0.05
    for ini in case.initiatives:
        for d in ini.requires:
            if d.mode == "sites":
                assert p.choice[ini.id] <= d.baseline_sites + p.choice[d.initiative]
            elif p.choice[ini.id] > 0:
                assert p.choice[d.initiative] > 0


def test_optimiser_at_least_as_good_as_greedy(dhl):
    case, vals, scr = dhl
    assert optimise(case, vals, scr).score >= greedy(case, vals, scr).score - 1


def test_greedy_respects_budget(dhl):
    case, vals, scr = dhl
    g = greedy(case, vals, scr)
    for y, b in enumerate(case.budget_by_year):
        assert g.capex_by_year[y] <= b + 1


def test_prohibited_initiative_is_never_funded(dhl):
    case, vals, scr = dhl
    scr = dict(scr)
    scr["LABOUR_FORECAST"] = screen({"uses_ai": True, "emotion_recognition_workplace": True})
    p = optimise(case, vals, scr)
    assert p.choice["LABOUR_FORECAST"] == 0


def test_roadmap_respects_quarterly_capacity_and_gates(dhl):
    case, vals, scr = dhl
    p = optimise(case, vals, scr)
    rows, spill = build_roadmap(case, p, vals, scr)
    for r in rows:
        if r.activity == "gate":
            later = [x for x in rows if x.initiative_id == r.initiative_id and x.activity == "deploy"]
            assert all(x.quarter > r.quarter for x in later)
    deployed = {}
    for r in rows:
        deployed[r.initiative_id] = deployed.get(r.initiative_id, 0) + r.sites
    for iid, sites in p.funded.items():
        assert deployed.get(iid, 0) + spill.get(iid, 0) == sites


def test_benefit_tracker_marks_rag(dhl):
    case, vals, scr = dhl
    df = track(case, optimise(case, vals, scr), vals)
    assert set(df["observation_status"].unique()) == {"missing"}
    assert df["observed_benefit_EUR_k"].isna().all()


# ---------- AI Act screening ----------
def test_emotion_recognition_is_prohibited():
    s = screen({"uses_ai": True, "emotion_recognition_workplace": True})
    assert s.category == "prohibited" and s.excluded


def test_individual_task_allocation_is_high_risk_from_dec_2027():
    s = screen({"uses_ai": True, "allocates_tasks_individual_behaviour": True})
    assert s.category == "high-risk (Annex III)"
    assert any(o.applies_from == ANNEX_III_FROM for o in s.obligations)
    assert any("26(7)" in o.reference for o in s.obligations)
    assert s.compliance_capex > 0 and s.go_live_gate


def test_zone_based_allocation_is_not_high_risk():
    s = screen(
        {"uses_ai": True, "allocates_tasks_individual_behaviour": False, "capable_of_monitoring_employees": True}
    )
    assert s.category == "minimal"
    assert any("BetrVG" in f.reference for f in s.flags)


def test_chatbot_needs_transparency():
    s = screen({"uses_ai": True, "interacts_with_people": True})
    assert s.category == "transparency"
    assert any("50(1)" in o.reference for o in s.obligations)


def test_no_ai_no_ai_act():
    assert screen({"uses_ai": False}).category == "not AI"


def test_redesign_to_individual_allocation_costs_value(dhl):
    case, vals, scr = dhl
    ini = case.get("AI_ORCH")
    risky = dict(ini.ai_act, allocates_tasks_individual_behaviour=True)
    s_hr = screen(risky, case.compliance)
    v_hr = value_initiative(case, ini, s_hr)
    assert v_hr[25].mean < vals["AI_ORCH"][25].mean


def test_carryover_never_worse_and_cumulative_budget_holds(dhl):
    case, vals, scr = dhl
    strict = optimise(case, vals, scr)
    flex = optimise(case, vals, scr, carryover=True)
    assert flex.score >= strict.score - 1
    assert np.all(np.cumsum(flex.capex_by_year[:3]) <= np.cumsum(case.budget_by_year) + 3)


def test_library_refs_exist():
    import yaml

    lib = {e["id"] for e in yaml.safe_load((ROOT / "library" / "initiatives.yaml").read_text())["initiatives"]}
    assert len(lib) >= 40
    for folder in CASES:
        for ini in load_case(folder).initiatives:
            assert not ini.library_ref or ini.library_ref in lib, ini.library_ref


def test_stress_test_runs_and_classifies(dhl):
    from invest_engine.scenarios import stress_test

    case, _, _ = dhl
    summary, rob = stress_test(case)
    assert len(summary) == 8
    assert set(rob["verdict"]) <= {"robust", "swing", "never"}
