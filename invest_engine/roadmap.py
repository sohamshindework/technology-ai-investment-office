"""Project the selected, valued quarterly plan; never reschedule it independently."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .portfolio import Portfolio, verify_choice
from .schema import Case


@dataclass
class RoadmapRow:
    initiative_id: str
    quarter: int
    activity: str  # gate | deploy | programme
    sites: int
    cumulative_sites: int
    fte_used: float = 0.0


def build_roadmap(case: Case, portfolio: Portfolio, valuations, screenings, quarters: int = 6):
    """Default 18-month window; spill is already scheduled in later model quarters."""
    if type(quarters) is not int or quarters < 1:
        raise ValueError("quarters must be a positive integer")
    verify_choice(case, valuations, screenings, portfolio.choice, portfolio.budget_scale, portfolio.carryover)
    rows, spill = [], {}
    for iid, sites in portfolio.funded.items():
        plan = valuations[iid][sites].deployment
        cumulative = np.cumsum(plan.sites)
        for q in range(min(quarters, len(plan.sites))):
            if not (plan.sites[q] or plan.gates[q] or plan.fte[q]):
                continue
            activity = "deploy" if plan.sites[q] else "gate" if plan.gates[q] else "programme"
            rows.append(RoadmapRow(iid, q + 1, activity, int(plan.sites[q]), int(cumulative[q]), float(plan.fte[q])))
        remaining = sites - int(plan.sites[:quarters].sum())
        if remaining:
            spill[iid] = remaining
    return sorted(rows, key=lambda r: (r.quarter, r.initiative_id)), spill
