"""Portfolio selection with OR-Tools CP-SAT, plus a greedy 'spreadsheet ranking' baseline.

Decision: for every initiative choose exactly one rollout level (0 = do not fund).
Constraints: annual capex, annual/quarterly FTE, quarterly deployment capacity, temporal dependencies,
committed minimum rollouts, AI Act exclusions.
Objective: maximise the sum of risk-adjusted values (mean NPV minus a penalty on the
downside tail), all in EUR k.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from ortools.sat.python import cp_model

from .ai_act import Screening
from .finance import OptionResult
from .schema import Case

SCALE_MONEY = 1000000  # precision EUR 0.001
SCALE_OBJECTIVE = 1000  # objective precision EUR 1
SCALE_FTE = 1000000  # FTE-years are scaled to integers for CP-SAT


@dataclass
class Portfolio:
    method: str
    status: str
    choice: dict[str, int]  # initiative id -> sites
    score: float
    npv_samples: np.ndarray
    capex_by_year: np.ndarray
    fte_by_year: np.ndarray
    budget_by_year: list[float]
    fte_capacity_by_year: list[float]

    objective_bound: float | None = None
    relative_gap: float | None = None
    budget_scale: float = 1.0
    carryover: bool = False

    @property
    def mean(self) -> float:
        return float(self.npv_samples.mean())

    def pct(self, q: float) -> float:
        return float(np.percentile(self.npv_samples, q))

    @property
    def p_loss(self) -> float:
        return float((self.npv_samples < 0).mean())

    @property
    def funded(self) -> dict[str, int]:
        return {k: v for k, v in self.choice.items() if v > 0}


def _aggregate(case, valuations, choice, method, status, risk):
    n, H = case.n_samples, case.horizon_years
    samples, capex, fte, score = np.zeros(n), np.zeros(H), np.zeros(H), 0.0
    for iid, sites in choice.items():
        o: OptionResult = valuations[iid][sites]
        samples = samples + o.npv_samples
        capex += o.capex_by_year
        fte += o.fte_by_year
        score += o.score(risk)
    return Portfolio(
        method, status, choice, score, samples, capex, fte, list(case.budget_by_year), list(case.fte_capacity_by_year)
    )


def _allowed(case: Case, screenings: dict[str, Screening], iid: str) -> list[int]:
    ini = case.get(iid)
    if screenings[iid].excluded:
        return [0] if ini.committed_min_sites == 0 else []
    gate = ini.pilot_gate
    if gate and (not gate.get("approved") or ini.p_success < gate["min_success_probability"]):
        return [0] if ini.committed_min_sites == 0 else []
    return [s for s in ini.site_options if s >= ini.committed_min_sites]


def optimise(
    case: Case,
    valuations,
    screenings,
    budget_scale: float = 1.0,
    risk_aversion: float | None = None,
    time_limit_s: float = 10.0,
    carryover: bool = False,
) -> Portfolio:
    """carryover=True lets unspent capex roll into later years (cumulative budget constraint)."""
    from .schema import validate

    validate(case)
    if not math.isfinite(budget_scale) or budget_scale < 0 or time_limit_s <= 0:
        raise ValueError("invalid budget scale or time limit")
    risk = case.risk_aversion if risk_aversion is None else risk_aversion
    if not math.isfinite(risk) or risk < 0:
        raise ValueError("risk aversion must be finite and nonnegative")
    budgets = [b * budget_scale for b in case.budget_by_year]
    m = cp_model.CpModel()
    x: dict[tuple[str, int], cp_model.IntVar] = {}
    for ini in case.initiatives:
        opts = _allowed(case, screenings, ini.id)
        for s in ini.site_options:
            v = m.NewBoolVar(f"x_{ini.id}_{s}")
            if s not in opts or not valuations[ini.id][s].deployment.valid:
                m.Add(v == 0)
            x[ini.id, s] = v
        m.AddExactlyOne(x[ini.id, s] for s in ini.site_options)

    def sites_expr(iid):
        return sum(s * x[iid, s] for s in case.get(iid).site_options)

    def funded_expr(iid):
        return sum(x[iid, s] for s in case.get(iid).site_options if s > 0)

    for y, budget in enumerate(budgets):
        years = range(y + 1) if carryover else [y]
        m.Add(
            sum(
                math.ceil(sum(valuations[i][s].capex_by_year[t] for t in years) * SCALE_MONEY - 1e-7) * x[i, s]
                for (i, s) in x
            )
            <= math.floor(sum(budgets[t] for t in years) * SCALE_MONEY + 1e-7)
        )
        cap = case.fte_capacity_by_year[y]
        m.Add(
            sum(math.ceil(valuations[i][s].fte_by_year[y] * SCALE_FTE - 1e-7) * x[i, s] for (i, s) in x)
            <= math.floor(cap * SCALE_FTE + 1e-7)
        )

    for ini in case.initiatives:
        for dep in ini.requires:
            if dep.mode == "any":
                m.Add(funded_expr(ini.id) <= funded_expr(dep.initiative))
            else:
                m.Add(sites_expr(ini.id) <= dep.baseline_sites + sites_expr(dep.initiative))

    # The same quarterly cohorts value cash flows and consume deployment resources.
    for q in range(case.rollout_years * 4):
        m.Add(sum(int(valuations[i][s].deployment.sites[q]) * x[i, s] for i, s in x) <= case.max_sites_per_quarter)
        m.Add(
            sum(math.ceil(valuations[i][s].deployment.fte[q] * SCALE_FTE - 1e-7) * x[i, s] for i, s in x)
            <= math.floor(case.fte_capacity_by_year[q // 4] / 4 * SCALE_FTE + 1e-7)
        )
        for ini in case.initiatives:
            for dep in ini.requires:
                if dep.mode == "sites":
                    m.Add(
                        sum(
                            int(valuations[ini.id][s].deployment.sites[: q + 1].sum()) * x[ini.id, s]
                            for s in ini.site_options
                        )
                        <= dep.baseline_sites
                        + sum(
                            int(valuations[dep.initiative][s].deployment.sites[:q].sum()) * x[dep.initiative, s]
                            for s in case.get(dep.initiative).site_options
                        )
                    )
                else:
                    m.Add(
                        sum(
                            int(valuations[ini.id][s].deployment.sites[: q + 1].sum() > 0) * x[ini.id, s]
                            for s in ini.site_options
                        )
                        <= sum(
                            int(valuations[dep.initiative][s].deployment.sites[:q].sum() > 0) * x[dep.initiative, s]
                            for s in case.get(dep.initiative).site_options
                        )
                    )

    groups = {i.exclusive_group for i in case.initiatives if i.exclusive_group}
    for group in groups:
        m.Add(sum(funded_expr(i.id) for i in case.initiatives if i.exclusive_group == group) <= 1)

    m.Maximize(sum(int(round(valuations[i][s].score(risk) * SCALE_OBJECTIVE)) * x[i, s] for (i, s) in x))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = case.seed
    st = solver.Solve(m)
    status = solver.StatusName(st)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"No feasible portfolio ({status}). Check committed rollouts against budget/capacity.")
    choice = {ini.id: next(s for s in ini.site_options if solver.Value(x[ini.id, s])) for ini in case.initiatives}
    verify_choice(case, valuations, screenings, choice, budget_scale, carryover)
    p = _aggregate(case, valuations, choice, "optimiser (CP-SAT)", status, risk)
    p.budget_by_year = budgets
    p.budget_scale, p.carryover = budget_scale, carryover
    p.objective_bound = solver.BestObjectiveBound() / SCALE_OBJECTIVE
    p.relative_gap = max(
        0.0, (solver.BestObjectiveBound() - solver.ObjectiveValue()) / max(1.0, abs(solver.ObjectiveValue()))
    )
    return p


def greedy(
    case: Case,
    valuations,
    screenings,
    budget_scale: float = 1.0,
    risk_aversion: float | None = None,
    carryover: bool = False,
) -> Portfolio:
    """Rank at maximum configured scale; insert the largest quarterly-feasible scale.

    This simple benchmark does not package enablers or change option phasing.
    """
    risk = case.risk_aversion if risk_aversion is None else risk_aversion
    choice = {ini.id: ini.committed_min_sites for ini in case.initiatives}
    verify_choice(case, valuations, screenings, choice, budget_scale, carryover)

    def ratio(iid):
        top = valuations[iid][max(case.get(iid).site_options)]
        return top.score(risk) / max(top.capex_by_year.sum(), 1.0)

    for iid in sorted(choice, key=ratio, reverse=True):
        current = valuations[iid][choice[iid]]
        for sites in sorted(_allowed(case, screenings, iid), reverse=True):
            if sites <= choice[iid]:
                break
            if valuations[iid][sites].score(risk) <= current.score(risk):
                continue
            candidate = {**choice, iid: sites}
            try:
                verify_choice(case, valuations, screenings, candidate, budget_scale, carryover)
            except RuntimeError:
                continue
            choice = candidate
            break
    verify_choice(case, valuations, screenings, choice, budget_scale, carryover)
    p = _aggregate(case, valuations, choice, "greedy ranking (baseline)", "HEURISTIC", risk)
    p.budget_by_year = list(np.array(case.budget_by_year) * budget_scale)
    p.budget_scale, p.carryover = budget_scale, carryover
    return p


def frontier(
    case: Case,
    valuations,
    screenings,
    scales=(0.5, 0.75, 1.0, 1.25, 1.5),
    risk_aversion: float | None = None,
    carryover: bool = False,
) -> list[dict]:
    rows = []
    for sc in scales:
        try:
            p = optimise(
                case,
                valuations,
                screenings,
                budget_scale=sc,
                risk_aversion=risk_aversion,
                time_limit_s=5.0,
                carryover=carryover,
            )
            rows.append(
                {
                    "budget_scale": sc,
                    "budget_total": sum(case.budget_by_year) * sc,
                    "expected_npv": p.mean,
                    "p10_npv": p.pct(10),
                    "p90_npv": p.pct(90),
                    "capex_total": float(p.capex_by_year.sum()),
                    "n_funded": len(p.funded),
                }
            )
        except RuntimeError:
            rows.append(
                {
                    "budget_scale": sc,
                    "budget_total": sum(case.budget_by_year) * sc,
                    "expected_npv": float("nan"),
                    "p10_npv": float("nan"),
                    "p90_npv": float("nan"),
                    "capex_total": float("nan"),
                    "n_funded": 0,
                }
            )
    return rows


def verify_choice(case, valuations, screenings, choice, budget_scale=1.0, carryover=False):
    """Independent float check; also used by exhaustive enumeration in tests."""
    if set(choice) != {i.id for i in case.initiatives}:
        raise RuntimeError("portfolio must contain every initiative")
    groups = set()
    Y = len(case.budget_by_year)
    capex, fte = np.zeros(Y), np.zeros(Y)
    for ini in case.initiatives:
        sites = choice[ini.id]
        if sites not in _allowed(case, screenings, ini.id):
            raise RuntimeError(f"{ini.id}: rollout violates an exclusion or commitment")
        if sites and ini.exclusive_group:
            if ini.exclusive_group in groups:
                raise RuntimeError("mutually exclusive alternatives funded")
            groups.add(ini.exclusive_group)
        for d in ini.requires:
            if (d.mode == "any" and sites and not choice[d.initiative]) or (
                d.mode == "sites" and sites > d.baseline_sites + choice[d.initiative]
            ):
                raise RuntimeError(f"{ini.id}: unmet dependency")
        o = valuations[ini.id][sites]
        if np.any(o.capex_by_year[Y:] > 1e-9) or np.any(o.fte_by_year[Y:] > 1e-9):
            raise RuntimeError("investment beyond resource schedule")
        capex += o.capex_by_year[:Y]
        fte += o.fte_by_year[:Y]
    budgets = np.array(case.budget_by_year) * budget_scale
    if carryover:
        capex, budgets = np.cumsum(capex), np.cumsum(budgets)
    if np.any(capex > budgets + 1e-8) or np.any(fte > np.array(case.fte_capacity_by_year) + 1e-8):
        raise RuntimeError("portfolio exceeds budget or staffing capacity")

    Q = case.rollout_years * 4
    cohorts, effort = np.zeros(Q), np.zeros(Q)
    for ini in case.initiatives:
        option = valuations[ini.id][choice[ini.id]]
        plan = option.deployment
        if plan is None or not plan.valid or int(plan.sites.sum()) != choice[ini.id]:
            raise RuntimeError(f"{ini.id}: missing or incomplete deployment plan")
        if plan.sites[Q:].any() or (plan.fte[Q:] > 1e-9).any():
            raise RuntimeError("deployment beyond rollout deadline")
        if not np.allclose(plan.fte.reshape(-1, 4).sum(axis=1), option.fte_by_year, atol=1e-9, rtol=0):
            raise RuntimeError("quarterly and annual resource schedules disagree")
        cohorts += plan.sites[:Q]
        effort += plan.fte[:Q]
        for dep in ini.requires:
            prior = np.r_[0, np.cumsum(valuations[dep.initiative][choice[dep.initiative]].deployment.sites[: Q - 1])]
            deployed = np.cumsum(plan.sites[:Q])
            if dep.mode == "sites" and np.any(deployed > dep.baseline_sites + prior):
                raise RuntimeError(f"{ini.id}: quarterly dependency coverage violated")
            if dep.mode == "any" and np.any((deployed > 0) & (prior == 0)):
                raise RuntimeError(f"{ini.id}: prerequisite must deploy in a preceding quarter")
    if np.any(cohorts > case.max_sites_per_quarter):
        raise RuntimeError("portfolio exceeds quarterly deployment capacity")
    if np.any(effort > np.repeat(np.array(case.fte_capacity_by_year) / 4, 4) + 1e-8):
        raise RuntimeError("portfolio exceeds quarterly staffing capacity")
