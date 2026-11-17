"""One calculated state for dashboard, CLI and exports. No UI dependencies."""

from __future__ import annotations

import copy
from dataclasses import dataclass

import pandas as pd

from .benefits import track
from .finance import value_case
from .portfolio import Portfolio, frontier, greedy, optimise
from .roadmap import build_roadmap
from .scenarios import stress_test
from .schema import Case, CaseError, Tri, validate

CALCULATION_VERSION = "quarterly-cohorts-v1"


@dataclass
class Analysis:
    case: Case
    valuations: dict
    screenings: dict
    portfolio: Portfolio
    baseline: Portfolio | None
    baseline_error: str
    frontier: list[dict]
    roadmap: list
    spill: dict
    benefits: pd.DataFrame
    scenarios: pd.DataFrame
    robustness: pd.DataFrame
    carryover: bool


def analyse(
    case: Case,
    *,
    budget_scale: float = 1,
    discount: float | None = None,
    risk: float | None = None,
    n_samples: int | None = None,
    carryover: bool = False,
    overrides: dict | None = None,
    benefit_factor: float = 1,
    extra_delay_months: float = 0,
) -> Analysis:
    """Copy inputs, apply settings once, then derive every downstream output."""
    import math

    if not all(math.isfinite(v) and v >= 0 for v in (budget_scale, benefit_factor, extra_delay_months)):
        raise CaseError("budget, benefits and delays must be finite and nonnegative")
    c = copy.deepcopy(case)
    c.path = None  # reports never leak local machine paths
    c.budget_by_year = [v * budget_scale for v in c.budget_by_year]
    if discount is not None:
        c.discount_rate = discount
    if risk is not None:
        c.risk_aversion = risk
    if n_samples is not None:
        c.n_samples = n_samples
    c.deployment_delay_quarters += math.ceil(extra_delay_months / 3)
    for ini in c.initiatives:
        ini.ai_act = (overrides or {}).get(ini.id, ini.ai_act).copy()
        t = ini.benefit_per_site
        ini.benefit_per_site = Tri(t.low * benefit_factor, t.mode * benefit_factor, t.high * benefit_factor)

    validate(c)
    vals, scr = value_case(c)
    opt = optimise(c, vals, scr, carryover=carryover)
    base, error = None, ""
    try:
        base = greedy(c, vals, scr, carryover=carryover)
    except RuntimeError as exc:
        error = str(exc)
    road, spill = build_roadmap(c, opt, vals, scr, quarters=c.rollout_years * 4)
    scenarios, robust = stress_test(c, carryover=carryover, extended=True)
    return Analysis(
        c,
        vals,
        scr,
        opt,
        base,
        error,
        frontier(c, vals, scr, carryover=carryover),
        road,
        spill,
        track(c, opt, vals),
        scenarios,
        robust,
        carryover,
    )
