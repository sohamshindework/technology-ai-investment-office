"""Exports are generated exclusively from the current Analysis; money is EUR k."""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import asdict

import pandas as pd

from .ai_act import DISCLAIMER, QUESTIONS
from .benefits import initiative_summary, portfolio_summary
from .branding import PROJECT_TITLE, SUBTITLE
from .finance import breakeven_p_success
from .service import CALCULATION_VERSION


def tables(a) -> dict[str, pd.DataFrame]:
    c, p = a.case, a.portfolio
    portfolio, options, cash, governance, assumptions = [], [], [], [], []
    quarterly = []
    for i in c.initiatives:
        sites = p.choice[i.id]
        o = a.valuations[i.id][sites]
        portfolio.append(
            {
                "id": i.id,
                "name": i.name,
                "function": i.function,
                "status": i.status,
                "sites": sites,
                "ranked_sites": a.baseline.choice[i.id] if a.baseline else None,
                "npv_EUR_k": o.mean,
                "capex_EUR_k": float(o.capex_by_year.sum()),
                "p10_EUR_k": o.pct(10),
                "p90_EUR_k": o.pct(90),
                "screening": a.screenings[i.id].category,
            }
        )
        for s, value in a.valuations[i.id].items():
            options.append(
                {
                    "id": i.id,
                    "sites": s,
                    "npv_EUR_k": value.mean if value.deployment.valid else None,
                    "rollout_window_valid": value.deployment.valid,
                    "score_EUR_k": value.score(c.risk_aversion),
                    "payback_year": value.payback_year,
                    "p_loss": value.p_loss,
                    "capex_EUR_k": float(value.capex_by_year.sum()),
                    "breakeven_success": breakeven_p_success(c, i, s, a.screenings[i.id]) if s else None,
                }
            )
        for y in range(c.horizon_years):
            cash.append(
                {
                    "id": i.id,
                    "year": y + 1,
                    "benefit_EUR_k": o.benefit_by_year[y],
                    "capex_EUR_k": o.capex_by_year[y],
                    "opex_EUR_k": o.benefit_by_year[y] - o.capex_by_year[y] - o.cash_by_year[y],
                    "net_cash_EUR_k": o.cash_by_year[y],
                    "discounted_cash_EUR_k": o.discounted_cash_by_year[y],
                }
            )
        for q in range(c.horizon_years * 4):
            quarterly.append(
                {
                    "id": i.id,
                    "quarter": q + 1,
                    "deployments_completed": int(o.deployment.sites[q]),
                    "gate": bool(o.deployment.gates[q]),
                    "fte_years": o.deployment.fte[q],
                    "benefit_EUR_k": o.benefit_by_quarter[q],
                    "capex_EUR_k": o.capex_by_quarter[q],
                    "opex_EUR_k": o.benefit_by_quarter[q] - o.capex_by_quarter[q] - o.cash_by_quarter[q],
                    "net_cash_EUR_k": o.cash_by_quarter[q],
                    "discounted_cash_EUR_k": o.cash_by_quarter[q] / (1 + c.discount_rate) ** ((q + 1) / 4),
                }
            )
        s = a.screenings[i.id]
        for k, q in QUESTIONS.items():
            governance.append(
                {
                    "id": i.id,
                    "question": q,
                    "answer": i.ai_act.get(k),
                    "evidence": i.assumption_notes or "Hypothetical design assumption; no reviewer evidence supplied",
                    "category": s.category,
                    "review_status": s.review_status,
                    "missing_questions": "; ".join(s.unknown_questions),
                    "provisions": "; ".join(o.reference for o in s.obligations + s.flags),
                    "remaining_uncertainty": "Intended purpose, role, exceptions and evidence require human legal review",
                    "human_approval": False,
                }
            )
        for k in ("capex_per_site", "opex_per_site", "benefit_per_site", "platform_capex", "months_to_value"):
            t = getattr(i, k)
            assumptions.append(
                {
                    "id": i.id,
                    "input": k,
                    "low": t.low,
                    "mode": t.mode,
                    "high": t.high,
                    "unit": "months" if k == "months_to_value" else "EUR k",
                    "nature": "hypothetical",
                }
            )
        for k in ("p_success", "fail_benefit_share", "fte_per_site", "central_fte", "ramp_years"):
            assumptions.append(
                {
                    "id": i.id,
                    "input": k,
                    "low": getattr(i, k),
                    "mode": getattr(i, k),
                    "high": getattr(i, k),
                    "unit": "probability"
                    if k in {"p_success", "fail_benefit_share"}
                    else "years"
                    if k == "ramp_years"
                    else "FTE-years",
                    "nature": "hypothetical",
                }
            )
    return {
        "portfolio": pd.DataFrame(portfolio),
        "options": pd.DataFrame(options),
        "cash_flows": pd.DataFrame(cash),
        "quarterly_cash_flows": pd.DataFrame(quarterly),
        "scenarios": a.scenarios,
        "robustness": a.robustness.reset_index(names="id"),
        "frontier": pd.DataFrame(a.frontier),
        "roadmap": pd.DataFrame([asdict(r) for r in a.roadmap]),
        (
            "benefits_UNAVAILABLE"
            if a.benefits.empty or not a.benefits.observed_benefit_EUR_k.notna().any()
            else "benefits_SIMULATED"
            if a.benefits.loc[a.benefits.observed_benefit_EUR_k.notna(), "is_simulated"].fillna(False).any()
            else "benefits_REPORTED"
        ): a.benefits,
        "assumptions": pd.DataFrame(assumptions),
        "governance_PENDING_REVIEW": pd.DataFrame(governance),
        "sources": pd.DataFrame.from_dict(c.sources, orient="index").reset_index(names="source"),
    }


def settings(a) -> dict:
    c = a.case
    result = {
        "project_title": PROJECT_TITLE,
        "project_subtitle": SUBTITLE,
        "case_title": c.title,
        "case": c.id,
        "company": c.company,
        "unit": c.unit,
        "model_version": CALCULATION_VERSION,
        "max_sites_per_quarter": c.max_sites_per_quarter,
        "deployment_delay_quarters": c.deployment_delay_quarters,
        "deployment_policy": "fixed integer quarterly cohorts, gates before deployment, prior-quarter dependencies",
        "discount_rate": c.discount_rate,
        "risk_aversion": c.risk_aversion,
        "horizon_years": c.horizon_years,
        "rollout_years": c.rollout_years,
        "budget_by_year_EUR_k": c.budget_by_year,
        "fte_capacity": c.fte_capacity_by_year,
        "seed": c.seed,
        "n_samples": c.n_samples,
        "carryover": a.carryover,
        "volume_factor": asdict(c.volume_factor),
        "compliance": c.compliance,
        "solver_status": a.portfolio.status,
        "objective_bound_EUR_k": a.portfolio.objective_bound,
        "relative_gap": a.portfolio.relative_gap,
        "inputs": [{**asdict(i)} for i in c.initiatives],
    }
    if c.profile:
        result["case_profile"] = {
            "schema_version": c.profile.schema_version,
            "industry_id": c.profile.industry_id,
            "scope": c.profile.scope,
            "as_of": c.profile.as_of,
            "deployment_unit": c.profile.deployment_unit,
            "kpis": c.profile.kpis,
            "governance": c.profile.governance,
            "views": c.profile.views,
            "accent": c.profile.accent,
            "decision_notes": c.profile.decision_notes,
            "evidence": c.profile.evidence,
        }
    return result


def memo(a) -> str:
    c, p = a.case, a.portfolio

    def money(v):
        return f"€{v / 1000:,.2f}m"

    lines = [
        f"# {PROJECT_TITLE}",
        "",
        SUBTITLE,
        "",
        f"## Investment committee memo — {c.title}",
        "",
        c.disclaimer,
        "",
        "Financial results use illustrative assumptions. The listed approvals and operating checks remain open.",
        "",
        "## Recommendation",
        "",
        f"Fund {len(p.funded)} of {len(c.initiatives)} candidates, subject to the listed governance and pilot gates.",
        f"Expected NPV: **{money(p.mean)}**. Capex: **{money(p.capex_by_year.sum())}** of {money(sum(c.budget_by_year))}.",
        f"P10/P90: {money(p.pct(10))} / {money(p.pct(90))}; modelled loss probability: {p.p_loss:.2%}.",
    ]
    if p.status != "OPTIMAL":
        lines += [
            "This portfolio meets the current limits, but a higher-value choice may exist. Review the optimization gap."
        ]
    if a.baseline:
        lines += [f"Ranked baseline NPV: {money(a.baseline.mean)}; difference: {money(p.mean - a.baseline.mean)}."]
    else:
        lines += [f"Ranked baseline unavailable: {a.baseline_error}"]
    unit_label = c.profile.deployment_unit["plural"].capitalize() if c.profile else "Sites"
    lines += ["", f"| Initiative | Decision | {unit_label} | NPV | Governance |", "|---|---|---:|---:|---|"]
    for i in c.initiatives:
        s = p.choice[i.id]
        decision = "fund" if s else ("pilot / defer" if i.pilot_gate else "defer")
        lines.append(
            f"| {i.name} | {decision} | {s} | {money(a.valuations[i.id][s].mean)} | {a.screenings[i.id].category}; pending human review |"
        )
    if c.profile:
        lines += ["", "## Case scope and decision conditions", "", f"**Operating unit:** {c.profile.scope['operating_unit']} ({c.profile.scope['geography']}).", f"**Deployment unit:** {c.profile.deployment_unit['definition']}", c.profile.decision_notes["rationale"], "", "**Material case risks:**"]
        lines += [f"- {item}" for item in c.profile.decision_notes["risks"]]
        lines += ["", "**Approvals required:**"]
        lines += [f"- {item}" for item in c.profile.decision_notes["approval_points"]]
        lines += ["", "**Operational measures (no observed baseline supplied):**"]
        lines += [f"- {k['label']} ({k['unit']}; {k['direction']}; owner: {k['owner']})" for k in c.profile.kpis]
    lines += [
        "",
        "## Scenarios",
        "",
        f"{len(a.scenarios) - 1} adverse scenarios plus base. Adoption is a benefit multiplier, not an independently estimated driver.",
        "",
        "| Scenario | Status | Expected NPV | P10 NPV | Funded |",
        "|---|---|---:|---:|---:|",
    ]
    for r in a.scenarios.to_dict("records"):
        status = {"OPTIMAL": "Recommended portfolio", "FEASIBLE": "Feasible portfolio; optimality unconfirmed"}.get(
            r["status"], "No feasible recommendation"
        )
        value = money(r["expected_npv"]) if pd.notna(r["expected_npv"]) else "Unavailable"
        downside = money(r["p10_npv"]) if pd.notna(r["p10_npv"]) else "Unavailable"
        lines.append(f"| {r['scenario']} | {status} | {value} | {downside} | {r['n_funded']} |")
    lines += ["", "## Pilot thresholds", ""]
    for i in c.initiatives:
        if i.status == "graduate":
            be = breakeven_p_success(c, i, max(i.site_options), a.screenings[i.id])
            lines.append(
                f"- {i.name}: assumed success {i.p_success:.1%}; maximum-scale NPV break-even "
                + (f"{be:.1%}." if be is not None else "not crossed within [0,1].")
                + " This is a financial threshold, not evidence of pilot success."
            )
    lines += [
        "",
        "## Delivery and benefits",
        "",
        (
            f"Within the {c.rollout_years * 12}-month deadline: {sum(r.sites for r in a.roadmap)} "
            f"{c.profile.deployment_unit['plural'] if c.profile else 'initiative/site deployments'} "
            f"scheduled by Q{max((r.quarter for r in a.roadmap if r.sites), default=0)}; "
            f"{sum(a.spill.values())} unscheduled."
        ),
        f"First 18 months: {sum(r.sites for r in a.roadmap if r.quarter <= 6)} deployments. All remaining selected deployments have dates within the rollout window.",
        f"Portfolio-wide quarterly ceiling: {c.max_sites_per_quarter} deployments. Quarterly staffing limits are annual FTE-years divided by four.",
        "Valuation, selection, roadmap and planned benefits use the same quarterly cohorts. Deployments complete at quarter end; operation starts the following quarter. Compliance lead time is included once, before deployment.",
        f"Total undiscounted operating benefits over the horizon: {money(sum(a.valuations[i][s].benefit_by_year.sum() for i, s in p.choice.items()))}.",
        "Observed benefits do not change valuation, selection or planned cash flows and do not by themselves prove causal attribution.",
    ]
    b = portfolio_summary(a.benefits)
    detail = initiative_summary(a.benefits)
    if b["observed"] is None:
        lines += ["Observed benefits: **Unavailable**. Missing observations are not treated as zero."]
    else:
        observation_type = (
            "fictional demonstration observations"
            if a.benefits.loc[a.benefits.observed_benefit_EUR_k.notna(), "is_simulated"].fillna(False).any()
            else "user-provided, unverified observations"
        )
        lines += [
            f"Benefits review through Q{b['reporting_quarter']} uses {observation_type}.",
            f"Observed benefit: {money(b['observed'])} versus {money(b['planned'])} planned for the same reported periods; variance {money(b['variance'])}; observation coverage {b['coverage']:.1%}.",
            f"Material follow-up items: {b['material_count']}. Missing periods remain unavailable.",
        ]
        lines += ["", "| Initiative | Plan for observed periods | Observed | Variance | Coverage | Confidence | Follow-up |", "|---|---:|---:|---:|---:|---|---|"]
        for row in detail.to_dict("records"):
            observed = money(row["observed_benefit"]) if pd.notna(row["observed_benefit"]) else "Unavailable"
            variance = money(row["variance_EUR_k"]) if pd.notna(row["variance_EUR_k"]) else "Unavailable"
            lines.append(
                f"| {c.get(row['initiative_id']).name} | {money(row['planned_for_observed']) if row['observed_periods'] else 'Unavailable'} | {observed} | {variance} | {row['coverage']:.0%} | {row['confidence']} | {'Required' if row['material_deviation'] else 'No'} |"
            )
    lines += [
        "",
        "## Method and limitations",
        "",
        f"Optimization detail: status {p.status}; relative gap {p.relative_gap:.4%}; objective bound {money(p.objective_bound)} (risk-adjusted objective, not NPV).",
        "",
        f"{c.horizon_years}-year horizon; quarter-end discounting at an annual rate of {c.discount_rate:.1%}; seed {c.seed}; {c.n_samples:,} draws.",
        "Fixed quarterly phasing is a policy constraint; scale selection is optimized, not unrestricted sequencing. "
        "Gates are planned activities, not evidence of legal approval. No terminal value. Costs constrained at expected values, not worst-case values. No benefit-overlap adjustment. "
        "Implementation labour must be included in input costs; FTE represents capacity, not a separate wage bill. "
        "Portfolio dependence is limited to the shared demand factor; failure contagion is not modelled.",
        "",
        DISCLAIMER,
        "",
        "## Sources",
        "",
    ]
    lines += [f"- {k}: [{v['title']}]({v['url']})" for k, v in c.sources.items()]
    return "\n".join(lines) + "\n"


def safe_csv(df: pd.DataFrame) -> str:
    """Protect spreadsheet users against formula injection in string fields."""

    def cell(v):
        if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")):
            return "'" + v
        return v

    return df.map(cell).to_csv(index=False)


def bundle(a) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:

        def write(name, content):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, content)

        write("memo.md", memo(a))
        write("settings.json", json.dumps(settings(a), indent=2, allow_nan=False))
        for name, frame in tables(a).items():
            write(f"{name}.csv", safe_csv(frame))
    return output.getvalue()
