"""Stress tests: re-optimise under adverse assumptions and report which choices are robust.

The default scenarios are company-agnostic. A recommendation is 'robust' when an
initiative is funded in (almost) every scenario, and a 'swing' choice otherwise.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import replace

import pandas as pd

from .finance import value_case
from .portfolio import optimise
from .schema import Case, Tri


def _scale(t: Tri, f: float) -> Tri:
    return Tri(t.low * f, t.mode * f, t.high * f)


def _map(case: Case, fn: Callable) -> Case:
    c = copy.deepcopy(case)
    c.initiatives = [fn(i) for i in c.initiatives]
    return c


def default_scenarios(extended: bool = False) -> dict[str, Callable[[Case], Case]]:
    def disc(c):
        c = copy.deepcopy(c)
        c.discount_rate += 0.03
        return c

    def cap(c):
        c = copy.deepcopy(c)
        c.fte_capacity_by_year = [x * 2 / 3 for x in c.fte_capacity_by_year]
        return c

    def vol(c):
        c = copy.deepcopy(c)
        v = c.volume_factor
        c.volume_factor = Tri(max(0, v.low - 0.15), max(0, v.mode - 0.1), max(0, v.high - 0.1))
        return c

    scenarios = {
        "Base case": lambda c: copy.deepcopy(c),
        "All benefits -30%": lambda c: _map(c, lambda i: replace(i, benefit_per_site=_scale(i.benefit_per_site, 0.7))),
        "New-initiative benefits -50%": lambda c: _map(
            c, lambda i: replace(i, benefit_per_site=_scale(i.benefit_per_site, 0.5)) if i.status == "new" else i
        ),
        "All capex +30%": lambda c: _map(
            c,
            lambda i: replace(
                i, capex_per_site=_scale(i.capex_per_site, 1.3), platform_capex=_scale(i.platform_capex, 1.3)
            ),
        ),
        "Pilots less likely to succeed (-0.15)": lambda c: _map(
            c, lambda i: replace(i, p_success=max(0.05, i.p_success - 0.15)) if i.status == "graduate" else i
        ),
        "Discount rate +3 pp": disc,
        "Implementation team -1/3": cap,
        "Volume downside": vol,
    }

    if extended:
        scenarios["Adoption -20%"] = lambda c: _map(
            c, lambda i: replace(i, benefit_per_site=_scale(i.benefit_per_site, 0.8))
        )

        def delayed(c):
            c = copy.deepcopy(c)
            c.deployment_delay_quarters += 2
            return c

        scenarios["Delivery delayed 6 months"] = delayed
    return scenarios


def stress_test(case: Case, carryover: bool = False, extended: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (scenario summary, robustness by initiative)."""
    summary, choices = [], {}
    for name, make in default_scenarios(extended).items():
        c = make(case)
        vals, scr = value_case(c)
        try:
            p = optimise(c, vals, scr, carryover=carryover, time_limit_s=5.0)
        except RuntimeError as exc:
            summary.append(
                {
                    "scenario": name,
                    "status": str(exc),
                    "expected_npv": float("nan"),
                    "p10_npv": float("nan"),
                    "n_funded": None,
                    "capex": float("nan"),
                }
            )
            continue
        summary.append(
            {
                "scenario": name,
                "status": p.status,
                "expected_npv": p.mean,
                "p10_npv": p.pct(10),
                "n_funded": len(p.funded),
                "capex": float(p.capex_by_year.sum()),
            }
        )
        choices[name] = p.choice
    ch = pd.DataFrame(choices)
    rob = pd.DataFrame(
        {
            "base_sites": ch["Base case"],
            "funded_share": (ch > 0).mean(axis=1),
            "min_sites": ch.min(axis=1),
            "max_sites": ch.max(axis=1),
        }
    )
    rob["verdict"] = rob["funded_share"].map(lambda s: "robust" if s >= 0.85 else "never" if s == 0 else "swing")
    return pd.DataFrame(summary), rob.join(ch)
