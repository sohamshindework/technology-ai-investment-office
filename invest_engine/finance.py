"""Seeded Monte Carlo on the same quarterly cohorts used by optimization/roadmap.

Capex is paid at deployment completion; platform/compliance costs at programme start.
Opex/benefits begin the following quarter. Benefits use midpoint ramp maturity after
intrinsic months-to-value. Compliance delay is a pre-deployment gate, not counted twice.
Cash is discounted at quarter end; annual arrays are exact sums for display/export.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass

import numpy as np

from .ai_act import Screening, screen
from .deployment import DeploymentPlan, annual_totals, deployment_starts, make_plan
from .schema import Case, Initiative, Tri


@dataclass
class OptionResult:
    initiative_id: str
    sites: int
    npv_samples: np.ndarray  # shape (n,)
    capex_by_year: np.ndarray  # expected EUR k per year, shape (H,)
    fte_by_year: np.ndarray  # FTE-years per year, shape (H,)
    benefit_by_year: np.ndarray  # expected EUR k per year, shape (H,)
    cash_by_year: np.ndarray  # expected net cash flow per year, shape (H,)

    deployment: DeploymentPlan | None = None
    capex_by_quarter: np.ndarray | None = None
    benefit_by_quarter: np.ndarray | None = None
    cash_by_quarter: np.ndarray | None = None
    discounted_cash_by_year: np.ndarray | None = None

    @property
    def mean(self) -> float:
        return float(self.npv_samples.mean())

    def pct(self, q: float) -> float:
        return float(np.percentile(self.npv_samples, q))

    @property
    def p_loss(self) -> float:
        return float((self.npv_samples < 0).mean())

    @property
    def payback_year(self) -> int | None:
        cum = np.cumsum(self.cash_by_year)
        invested = np.cumsum(self.capex_by_year) > 0
        # Recovery must persist through the horizon; ignore zero-flow pre-investment years.
        sustained = np.minimum.accumulate(cum[::-1])[::-1] >= 0
        hits = np.nonzero((cum >= 0) & invested & sustained)[0]
        if self.sites == 0 or len(hits) == 0:
            return None
        return int(hits[0]) + 1

    @property
    def expected_loss(self) -> float:
        """E[max(0, -NPV)]: average value destroyed in the draws where the initiative loses money."""
        return float(np.maximum(0.0, -self.npv_samples).mean())

    def score(self, risk_aversion: float) -> float:
        """Risk-adjusted value = expected NPV - risk_aversion x expected loss.
        Penalises real downside only, so it does not punish wide-but-positive outcomes and
        stays additive across initiatives (portfolio risk is reported separately from the
        summed draws)."""
        return self.mean - risk_aversion * self.expected_loss


def _tri(rng: np.random.Generator, t: Tri, n: int) -> np.ndarray:
    if t.low == t.high:
        return np.full(n, t.low, dtype=float)
    return rng.triangular(t.low, t.mode, t.high, n)


def _rng(case: Case, key: str) -> np.random.Generator:
    return np.random.default_rng([case.seed, zlib.crc32(key.encode())])


def volume_draws(case: Case) -> np.ndarray:
    return _tri(_rng(case, "__volume__"), case.volume_factor, case.n_samples)


def rollout_schedule(sites: int, rollout_years: int, horizon: int) -> np.ndarray:
    """Legacy integer split helper; valuation now uses deployment.make_plan quarters."""
    if type(sites) is not int or sites < 0 or not 1 <= rollout_years <= horizon:
        raise ValueError("invalid sites or rollout periods")
    sched = np.zeros(horizon)
    if sites == 0:
        return sched
    base, rem = divmod(sites, rollout_years)
    for y in range(rollout_years):
        sched[y] = base + (1 if y < rem else 0)
    return sched


def value_initiative(
    case: Case, ini: Initiative, screening: Screening | None = None, *, starts: dict[str, int] | None = None
) -> dict[int, OptionResult]:
    screening = screening or screen(ini.ai_act, case.compliance)
    n, H = case.n_samples, case.horizon_years
    Q = H * 4
    rng = _rng(case, ini.id)
    capex_ps = _tri(rng, ini.capex_per_site, n)
    opex_ps = _tri(rng, ini.opex_per_site, n)
    ben_ps = _tri(rng, ini.benefit_per_site, n)
    platform = _tri(rng, ini.platform_capex, n)
    delay = _tri(rng, ini.months_to_value, n) / 12.0
    success = rng.random(n) < ini.p_success
    vol = volume_draws(case)
    ben_mult = np.where(success, 1.0, ini.fail_benefit_share) * vol

    disc = (1 + case.discount_rate) ** -(np.arange(1, Q + 1) / 4)
    results: dict[int, OptionResult] = {}
    for sites in ini.site_options:
        plan = make_plan(case, ini, sites, screening, starts)
        capex, ben = np.zeros((n, Q)), np.zeros((n, Q))
        if sites and plan.valid:
            capex = np.outer(capex_ps, plan.sites)
            first = int(np.flatnonzero((plan.sites > 0) | plan.gates)[0])
            capex[:, first] += platform + screening.compliance_capex
            for t in np.flatnonzero(plan.sites):
                for q in range(t + 1, Q):
                    maturity = (q - t - 0.5) / 4 - delay
                    frac = (
                        (maturity >= 0).astype(float)
                        if ini.ramp_years == 0
                        else np.clip(maturity / ini.ramp_years, 0, 1)
                    )
                    ben[:, q] += plan.sites[t] * ben_ps / 4 * frac
        ben *= ben_mult[:, None]
        # Quarter t deployments complete at t-end; they operate from t+1.
        operating = np.r_[0, np.cumsum(plan.sites)[:-1]]
        opex = np.outer(opex_ps / 4, operating)
        cash = ben - opex - capex
        expected_cash = cash.mean(axis=0)
        results[sites] = OptionResult(
            initiative_id=ini.id,
            sites=sites,
            npv_samples=cash @ disc,
            capex_by_year=annual_totals(capex.mean(axis=0)),
            fte_by_year=annual_totals(plan.fte),
            benefit_by_year=annual_totals(ben.mean(axis=0)),
            cash_by_year=annual_totals(expected_cash),
            deployment=plan,
            capex_by_quarter=capex.mean(axis=0),
            benefit_by_quarter=ben.mean(axis=0),
            cash_by_quarter=expected_cash,
            discounted_cash_by_year=annual_totals(expected_cash * disc),
        )
    return results


def value_case(case: Case, answers_override: dict[str, dict[str, bool]] | None = None):
    """Screen and value every initiative. Returns (valuations, screenings)."""
    from .schema import validate

    validate(case)
    valuations, screenings = {}, {}
    for ini in case.initiatives:
        answers = (answers_override or {}).get(ini.id, ini.ai_act)
        screenings[ini.id] = screen(answers, case.compliance)
    starts = deployment_starts(case, screenings)
    for ini in case.initiatives:
        valuations[ini.id] = value_initiative(case, ini, screenings[ini.id], starts=starts)
    return valuations, screenings


def breakeven_p_success(case: Case, ini: Initiative, sites: int, screening: Screening | None = None) -> float | None:
    """Success probability at which expected NPV is zero for a rollout level.
    Mean NPV is linear in p: mean = p * NPV|success + (1 - p) * NPV|underdelivery.
    Returns None if the initiative is positive even when it under-delivers, or negative even
    when it succeeds."""
    from dataclasses import replace

    s_val = value_initiative(case, replace(ini, p_success=1.0), screening)[sites].mean
    f_val = value_initiative(case, replace(ini, p_success=0.0), screening)[sites].mean
    if f_val >= 0 or s_val <= 0:
        return None
    return -f_val / (s_val - f_val)
