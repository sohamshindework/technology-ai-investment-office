"""One deterministic quarterly rollout policy shared by selection and valuation.

Options spread integer cohorts evenly across available deployment quarters, earlier
quarters taking the remainder. The optimizer chooses scales, not arbitrary dates.
Deployments complete at quarter end; operation starts the following quarter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .ai_act import Screening, screen
from .schema import Case, Initiative


@dataclass
class DeploymentPlan:
    sites: np.ndarray
    gates: np.ndarray
    fte: np.ndarray  # FTE-years consumed in each quarter
    valid: bool = True


def gate_quarters(screening: Screening) -> int:
    """Compliance lead time is spent before deployment, exactly once."""
    return max(int(screening.go_live_gate), math.ceil(screening.delay_months / 3))


def deployment_starts(case: Case, screenings: dict[str, Screening] | None = None) -> dict[str, int]:
    """Zero-based first deployment quarter; prerequisites need a prior-quarter cohort."""
    screenings = screenings or {}
    starts: dict[str, int] = {}

    def visit(iid):
        if iid in starts:
            return starts[iid]
        ini = case.get(iid)
        s = screenings.get(iid) or screen(ini.ai_act, case.compliance)
        start = case.deployment_delay_quarters + gate_quarters(s)
        for dep in ini.requires:
            if dep.mode == "any" or dep.baseline_sites == 0:
                start = max(start, visit(dep.initiative) + 1)
        starts[iid] = start
        return start

    for ini in case.initiatives:
        visit(ini.id)
    return starts


def make_plan(
    case: Case, ini: Initiative, sites: int, screening: Screening, starts: dict[str, int] | None = None
) -> DeploymentPlan:
    Q, deadline = case.horizon_years * 4, case.rollout_years * 4
    counts, gates, fte = np.zeros(Q, dtype=int), np.zeros(Q, dtype=bool), np.zeros(Q)
    if sites == 0:
        return DeploymentPlan(counts, gates, fte)
    starts = starts or deployment_starts(case, {ini.id: screening})
    start = starts[ini.id]
    if start >= deadline:
        return DeploymentPlan(counts, gates, fte, valid=False)
    base, remainder = divmod(sites, deadline - start)
    counts[start:deadline] = base
    counts[start : start + remainder] += 1
    lead = gate_quarters(screening)
    gates[start - lead : start] = True
    last = int(np.flatnonzero(counts)[-1])
    fte[start - lead : last + 1] = ini.central_fte / 4
    fte += counts * ini.fte_per_site
    return DeploymentPlan(counts, gates, fte)


def annual_totals(quarterly: np.ndarray) -> np.ndarray:
    """Aggregate the last axis, preserving optional leading sample dimensions."""
    return quarterly.reshape(*quarterly.shape[:-1], -1, 4).sum(axis=-1)
