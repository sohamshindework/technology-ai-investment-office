"""Independent quarterly cash-flow and exhaustive portfolio audit; not used by the UI.

Run with a case folder. Reference calculations deliberately do not call production
finance/deployment/constraint helpers. Enumeration proves optimality only if the
node limit is not exceeded, under the existing fixed-phasing policy.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from invest_engine import load_case
from invest_engine.reporting import tables
from invest_engine.service import analyse


@dataclass
class Reference:
    counts: np.ndarray
    gates: np.ndarray
    fte: np.ndarray
    capex: np.ndarray
    benefits: np.ndarray
    cash: np.ndarray
    npv: np.ndarray
    valid: bool


def reference_option(c, i, sites, screenings):
    """Independent seeded reference using case assumptions and screening outputs."""
    q_count, deadline, n = c.horizon_years * 4, c.rollout_years * 4, c.n_samples
    counts = np.zeros(q_count, dtype=int)
    gates = np.zeros(q_count, dtype=bool)
    effort = np.zeros(q_count)
    capex, benefits, cash = (np.zeros((n, q_count)) for _ in range(3))
    if not sites:
        return Reference(counts, gates, effort, capex, benefits, cash, np.zeros(n), True)

    def lead(iid):
        s = screenings[iid]
        return max(int(s.go_live_gate), math.ceil(s.delay_months / 3))

    def first(iid):
        start = c.deployment_delay_quarters + lead(iid)
        for dep in c.get(iid).requires:
            if dep.mode == "any" or dep.baseline_sites == 0:
                start = max(start, first(dep.initiative) + 1)
        return start

    start = first(i.id)
    if start >= deadline:
        return Reference(counts, gates, effort, capex, benefits, cash, np.zeros(n), False)
    slots = deadline - start
    for q in range(start, deadline):
        counts[q] = sites // slots + int(q - start < sites % slots)
    gates[start - lead(i.id) : start] = True
    end = max(q for q, count in enumerate(counts) if count)
    for q in range(q_count):
        effort[q] = counts[q] * i.fte_per_site + (i.central_fte / 4 if start - lead(i.id) <= q <= end else 0)
    rng = np.random.default_rng([c.seed, zlib.crc32(i.id.encode())])

    def draw(distribution, generator=rng):
        if distribution.low == distribution.high:
            return np.repeat(float(distribution.low), n)
        return generator.triangular(distribution.low, distribution.mode, distribution.high, n)

    site_capex, annual_opex, annual_benefit = draw(i.capex_per_site), draw(i.opex_per_site), draw(i.benefit_per_site)
    platform, months_to_value = draw(i.platform_capex), draw(i.months_to_value)
    succeeds = rng.random(n) < i.p_success
    volume = draw(c.volume_factor, np.random.default_rng([c.seed, zlib.crc32(b"__volume__")]))
    realized_share = np.where(succeeds, 1.0, i.fail_benefit_share) * volume
    first_payment = min(q for q in range(q_count) if gates[q] or counts[q])
    for q in range(q_count):
        capex[:, q] = counts[q] * site_capex
        if q == first_payment:
            capex[:, q] += platform + screenings[i.id].compliance_capex
        mature_units = np.zeros(n)
        for completion in range(q):
            age = (q - completion - 0.5) / 4 - months_to_value / 12
            fraction = (
                (age >= 0).astype(float) if i.ramp_years == 0 else np.minimum(1, np.maximum(0, age / i.ramp_years))
            )
            mature_units += counts[completion] * fraction
        benefits[:, q] = annual_benefit / 4 * mature_units * realized_share
        cash[:, q] = benefits[:, q] - annual_opex / 4 * int(counts[:q].sum()) - capex[:, q]
    npv = np.zeros(n)
    for q in range(q_count):
        npv += cash[:, q] / (1 + c.discount_rate) ** ((q + 1) / 4)
    return Reference(counts, gates, effort, capex, benefits, cash, npv, True)


def exhaustive(c, refs, screenings, *, carryover=False, max_nodes=2_000_000):
    """Enumerate feasible scales in dependency order, with monotone resource pruning."""
    ordered, visited = [], set()

    def visit(i):
        if i.id in visited:
            return
        for d in i.requires:
            visit(c.get(d.initiative))
        ordered.append(i)
        visited.add(i.id)

    for i in c.initiatives:
        visit(i)
    options = {}
    q_count = c.rollout_years * 4
    for i in ordered:
        gate = i.pilot_gate
        blocked = screenings[i.id].excluded or bool(
            gate and (not gate.get("approved") or i.p_success < gate["min_success_probability"])
        )
        options[i.id] = [
            s for s in i.site_options if s >= i.committed_min_sites and (not blocked or s == 0) and refs[i.id, s].valid
        ]
    best_score, best_choice, feasible, nodes = -math.inf, None, 0, 0
    budgets = np.array(c.budget_by_year)
    if carryover:
        budgets = budgets.cumsum()
    fte_limit = np.repeat(np.array(c.fte_capacity_by_year) / 4, 4)
    choice = {}
    stats = {}
    for (iid, s), r in refs.items():
        capex = r.capex.mean(axis=0).reshape(-1, 4).sum(axis=1)[: c.rollout_years]
        score = r.npv.mean() - c.risk_aversion * np.maximum(0, -r.npv).mean()
        stats[iid, s] = (capex, int(round(score * 1000)))

    def search(k, sites, fte, spending, score, groups):
        nonlocal nodes, feasible, best_score, best_choice
        nodes += 1
        if nodes > max_nodes:
            raise RuntimeError(f"Enumeration exceeded {max_nodes} nodes; no optimality claim is available")
        if k == len(ordered):
            feasible += 1
            if score > best_score:
                best_score, best_choice = score, choice.copy()
            return
        i = ordered[k]
        for s in options[i.id]:
            r = refs[i.id, s]
            if s and i.exclusive_group and i.exclusive_group in groups:
                continue
            next_sites, next_fte = sites + r.counts[:q_count], fte + r.fte[:q_count]
            next_spending = spending + stats[i.id, s][0]
            if np.any(next_sites > c.max_sites_per_quarter) or np.any(next_fte > fte_limit + 1e-8):
                continue
            if np.any((next_spending.cumsum() if carryover else next_spending) > budgets + 1e-8):
                continue
            valid = True
            for d in i.requires:
                prior = np.r_[0, refs[d.initiative, choice[d.initiative]].counts[: q_count - 1].cumsum()]
                current = r.counts[:q_count].cumsum()
                if d.mode == "sites" and np.any(current > d.baseline_sites + prior):
                    valid = False
                if d.mode == "any" and np.any((current > 0) & (prior == 0)):
                    valid = False
            if valid:
                choice[i.id] = s
                search(
                    k + 1,
                    next_sites,
                    next_fte,
                    next_spending,
                    score + stats[i.id, s][1],
                    groups | ({i.exclusive_group} if s and i.exclusive_group else set()),
                )

    search(0, np.zeros(q_count), np.zeros(q_count), np.zeros(c.rollout_years), 0, set())
    return {"nodes": nodes, "feasible_portfolios": feasible, "best_integer_score": best_score, "choice": best_choice}


def audit(a, *, max_nodes=2_000_000):
    c, p = a.case, a.portfolio
    refs = {}
    max_sample_error = 0.0
    for i in c.initiatives:
        for s in i.site_options:
            r = reference_option(c, i, s, a.screenings)
            refs[i.id, s] = r
            o = a.valuations[i.id][s]
            assert r.valid == o.deployment.valid
            if not r.valid:
                continue
            np.testing.assert_array_equal(r.counts, o.deployment.sites)
            np.testing.assert_array_equal(r.gates, o.deployment.gates)
            np.testing.assert_allclose(r.fte, o.deployment.fte, rtol=0, atol=1e-10)
            for actual, expected in [
                (o.capex_by_quarter, r.capex.mean(axis=0)),
                (o.benefit_by_quarter, r.benefits.mean(axis=0)),
                (o.cash_by_quarter, r.cash.mean(axis=0)),
                (o.npv_samples, r.npv),
            ]:
                np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-7)
            discount = (1 + c.discount_rate) ** -(np.arange(1, c.horizon_years * 4 + 1) / 4)
            for actual, expected in [
                (o.capex_by_year, r.capex.mean(axis=0).reshape(-1, 4).sum(axis=1)),
                (o.benefit_by_year, r.benefits.mean(axis=0).reshape(-1, 4).sum(axis=1)),
                (o.cash_by_year, r.cash.mean(axis=0).reshape(-1, 4).sum(axis=1)),
                (o.discounted_cash_by_year, (r.cash.mean(axis=0) * discount).reshape(-1, 4).sum(axis=1)),
                (o.fte_by_year, r.fte.reshape(-1, 4).sum(axis=1)),
            ]:
                np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-7)
            max_sample_error = max(max_sample_error, float(abs(o.npv_samples - r.npv).max()))
    enum = exhaustive(c, refs, a.screenings, carryover=a.carryover, max_nodes=max_nodes)
    expected_score = sum(int(round(a.valuations[i][s].score(c.risk_aversion) * 1000)) for i, s in p.choice.items())
    assert enum["best_integer_score"] == expected_score
    chosen = [refs[i, s] for i, s in p.choice.items()]
    reference_samples = sum((r.npv for r in chosen), start=np.zeros(c.n_samples))
    np.testing.assert_allclose(reference_samples, p.npv_samples, rtol=1e-12, atol=1e-7)
    exported = tables(a)
    for name in ["cash_flows", "quarterly_cash_flows"]:
        np.testing.assert_allclose(exported[name].discounted_cash_EUR_k.sum(), p.mean, rtol=1e-12)
    counts = sum((r.counts for r in chosen), start=np.zeros(c.horizon_years * 4, dtype=int))
    effort = sum((r.fte for r in chosen), start=np.zeros(c.horizon_years * 4))
    np.testing.assert_allclose(
        p.capex_by_year, sum((r.capex.mean(axis=0).reshape(-1, 4).sum(axis=1) for r in chosen)), rtol=1e-12, atol=1e-7
    )
    np.testing.assert_allclose(p.fte_by_year, effort.reshape(-1, 4).sum(axis=1), rtol=0, atol=1e-10)
    expected_rows = {
        (iid, q + 1)
        for iid, sites in p.funded.items()
        for q in range(c.rollout_years * 4)
        if refs[iid, sites].counts[q] or refs[iid, sites].gates[q] or refs[iid, sites].fte[q]
    }
    assert len(a.roadmap) == len({(row.initiative_id, row.quarter) for row in a.roadmap})
    assert expected_rows == {(row.initiative_id, row.quarter) for row in a.roadmap}
    for row in a.roadmap:
        r = refs[row.initiative_id, p.choice[row.initiative_id]]
        assert row.sites == r.counts[row.quarter - 1]
        assert row.cumulative_sites == r.counts[: row.quarter].sum()
        np.testing.assert_allclose(row.fte_used, r.fte[row.quarter - 1], rtol=0, atol=1e-10)
    for iid, sites in p.funded.items():
        planned = a.benefits[a.benefits.initiative_id == iid].sort_values("quarter")
        indices = planned.quarter.to_numpy(dtype=int) - 1
        np.testing.assert_allclose(
            planned.planned_benefit, refs[iid, sites].benefits.mean(axis=0)[indices], rtol=1e-12, atol=1e-7
        )
    assert sum(row.sites for row in a.roadmap) == sum(p.funded.values())
    for q in range(c.rollout_years * 4):
        rows = [row for row in a.roadmap if row.quarter == q + 1]
        assert sum(row.sites for row in rows) == counts[q]
        np.testing.assert_allclose(sum(row.fte_used for row in rows), effort[q], rtol=0, atol=1e-10)
    return {
        "case": c.id,
        "npv_EUR_k": p.mean,
        "capex_EUR_k": float(p.capex_by_year.sum()),
        "benefits_EUR_k": float(sum(r.benefits.mean(axis=0).sum() for r in chosen)),
        "opex_EUR_k": float(sum((r.benefits - r.capex - r.cash).mean(axis=0).sum() for r in chosen)),
        "selected": p.funded,
        "quarterly_deployments": counts[: c.rollout_years * 4].tolist(),
        "quarterly_FTE_years": effort[: c.rollout_years * 4].tolist(),
        "max_sample_error_EUR_k": max_sample_error,
        "independent_enumeration": enum,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_folder")
    parser.add_argument("--max-nodes", type=int, default=2_000_000)
    args = parser.parse_args()
    print(json.dumps(audit(analyse(load_case(args.case_folder)), max_nodes=args.max_nodes), indent=2, allow_nan=False))
