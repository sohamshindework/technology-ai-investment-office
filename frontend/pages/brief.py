"""Management review with current recommendations, risk, evidence and supported exports."""

import pandas as pd
import streamlit as st

from frontend.components import ROOT, analysis_key, eur, investment_table, recommendation, table
from invest_engine.benefits import initiative_summary, portfolio_summary
from invest_engine.documents import excel_analysis, investment_committee_pdf
from invest_engine.reporting import bundle, memo, safe_csv
from invest_engine.store import Store

EXPORT_LABELS = {
    "portfolio": "Investment portfolio",
    "options": "Rollout alternatives",
    "cash_flows": "Annual cash flows",
    "quarterly_cash_flows": "Quarterly cash flows",
    "scenarios": "Stress scenarios",
    "robustness": "Selection stability",
    "frontier": "Capital and value tradeoff",
    "roadmap": "Quarterly delivery schedule",
    "benefits_SIMULATED": "Benefits tracking · includes simulated values",
    "benefits_REPORTED": "Benefits tracking · user-supplied actuals",
    "benefits_UNAVAILABLE": "Benefits tracking · observations unavailable",
    "assumptions": "Financial assumptions",
    "governance_PENDING_REVIEW": "Governance questionnaire · pending review",
    "sources": "Source register",
}


def render(v):
    a, c, p = v.analysis, v.c, v.p
    recommendation(v, compact=True)
    st.subheader("Recommended investments")
    investment_table(v)
    left, right = st.columns([1.3, 1], gap="large")
    with left:
        st.markdown("#### Investment value and risk")
        st.write(
            f"Expected NPV of **{eur(p.mean, 2)}** for **{eur(p.capex_by_year.sum(), 2)}** in capital. "
            f"The model estimates **{eur(p.pct(10), 2)} / {eur(p.pct(90), 2)}** at the 10th / 90th percentiles, "
            f"with a **{p.p_loss:.2%}** probability of negative NPV under the assumed distributions."
        )
        if a.baseline:
            st.write(
                f"The same-constraint ranked list produces {eur(a.baseline.mean, 2)} NPV; the recommended portfolio adds {eur(p.mean - a.baseline.mean, 2)}."
            )
        last_q = max((r.quarter for r in a.roadmap if r.sites), default=0)
        st.write(
            f"All {sum(p.funded.values())} selected deployments are scheduled by Q{last_q}, within the {c.rollout_years * 12}-month deadline. "
            f"Expected undiscounted operating benefits total {eur(sum(a.valuations[i][n].benefit_by_year.sum() for i, n in p.choice.items()), 2)} over {c.horizon_years} years."
        )
    with right:
        st.markdown("#### Decision required")
        st.write(
            "1. Validate the investment assumptions and chosen rollout scales.\n2. Confirm delivery ownership, prerequisites and staffing.\n3. Complete pilot, legal and workforce reviews before deployment.\n4. Agree benefit owners and evidence for tracking actuals."
        )
    st.subheader("Benefits realization")
    realized = portfolio_summary(a.benefits)
    if realized["observed"] is None:
        st.info("Observed benefits are unavailable. Missing observations are not treated as zero.")
    else:
        observed_type = (
            "Fictional demonstration observations"
            if a.benefits.loc[a.benefits.observed_benefit_EUR_k.notna(), "is_simulated"].fillna(False).any()
            else "User-provided, unverified observations"
        )
        st.write(
            f"Through Q{realized['reporting_quarter']}, **{eur(realized['observed'], 2)}** was observed against "
            f"**{eur(realized['planned'], 2)}** planned for the same reported periods, a variance of "
            f"**{eur(realized['variance'], 2)}**. Observation coverage is **{realized['coverage']:.0%}**."
        )
        st.caption(
            f"{observed_type}. Observed changes do not by themselves establish causal attribution and do not change the optimized portfolio."
        )
        if realized["material_count"]:
            st.warning(f"{realized['material_count']} initiative-level material deviation(s) require follow-up.")
        with st.expander("Benefits realization detail"):
            detail = initiative_summary(a.benefits).assign(
                Initiative=lambda frame: frame.initiative_id.map(v.names)
            )
            table(
                detail[
                    [
                        "Initiative", "planned_for_observed", "observed_benefit", "variance_EUR_k",
                        "variance_percent", "coverage", "confidence", "material_deviation",
                    ]
                ].rename(
                    columns={
                        "planned_for_observed": "Plan for observed periods (€k)",
                        "observed_benefit": "Observed benefits (€k)",
                        "variance_EUR_k": "Variance (€k)",
                        "variance_percent": "Variance (%)",
                        "coverage": "Coverage",
                        "confidence": "Confidence",
                        "material_deviation": "Material follow-up",
                    }
                )
            )
    st.subheader("Key considerations")
    table(
        pd.DataFrame(
            [
                {
                    "Assumption": "Capital envelope",
                    "Current basis": f"{eur(sum(c.budget_by_year))} across {c.rollout_years} years",
                },
                {
                    "Assumption": "Valuation",
                    "Current basis": f"{c.horizon_years} years · {c.discount_rate:.1%} annual discount rate · no terminal value",
                },
                {
                    "Assumption": "Implementation capacity",
                    "Current basis": " / ".join(f"{n:g}" for n in c.fte_capacity_by_year) + " FTE-years by year",
                },
                {
                    "Assumption": "Deployment limit",
                    "Current basis": f"{c.max_sites_per_quarter} {v.deployment_unit['plural']} per quarter",
                },
                {
                    "Assumption": "Timing policy",
                    "Current basis": "Fixed quarterly phasing; investment scales selected, arbitrary dates not optimized",
                },
            ]
        )
    )
    st.write(
        "**Financial uncertainty:** costs, benefits and probabilities are illustrative. Capital limits use expected costs, and benefits may overlap. The model excludes taxes, working capital and failure contagion. Demonstration benefit data is not observed performance."
    )
    st.write(
        "**Required reviews:** confirm intended use, legal duties, pilot evidence and outstanding questions in Delivery Plan before any investment decision."
    )
    if c.profile:
        st.markdown("#### Case-specific considerations")
        st.write(c.profile.decision_notes["rationale"])
        for item in c.profile.decision_notes["risks"]:
            st.write(f"- {item}")
        st.markdown("**Approvals to obtain**")
        for item in c.profile.decision_notes["approval_points"]:
            st.write(f"- {item}")
    with st.expander("Investment alternatives and evidence"):
        alternatives = v.t["portfolio"][["name", "sites", "ranked_sites", "npv_EUR_k"]].rename(
            columns={
                "name": "Initiative",
                "sites": "Selected deployments",
                "ranked_sites": "Ranked-list deployments",
                "npv_EUR_k": "Selected NPV (€k)",
            }
        )
        table(alternatives)
        st.caption(
            "Zero selected value means no rollout is funded; it does not mean that every alternative has zero value. Inspect rollout options in Portfolio."
        )
        if c.facts:
            table(pd.DataFrame(c.facts))
        for sid, src in c.sources.items():
            st.markdown(
                f"[{sid} · {src['title']}]({src['url']}) — {src.get('publisher', '')}, accessed {src.get('accessed', '')}"
            )
    st.divider()
    st.subheader("Download the current investment analysis")
    st.write(
        "The memo and committee pack use the active scenario, selected investments and quarterly plan shown in this application."
    )
    documents = st.columns(2)
    documents[0].download_button(
        "Download Excel Analysis",
        excel_analysis(a),
        f"{c.id}_investment_analysis.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )
    documents[1].download_button(
        "Download Investment Committee Report",
        investment_committee_pdf(a),
        f"{c.id}_investment_committee_report.pdf",
        "application/pdf",
        type="primary",
    )
    cols = st.columns(2)
    cols[0].download_button(
        "Download committee pack · ZIP", bundle(a), f"{c.id}_committee_pack.zip", "application/zip", type="primary"
    )
    cols[1].download_button("Download investment memo · Markdown", memo(a), f"{c.id}_memo.md", "text/markdown")
    st.caption("Available formats: Excel, PDF, Markdown, CSV, JSON and ZIP. All files reflect the active scenario.")
    with st.expander("Inspect and download supporting tables"):
        selected = st.selectbox("Analysis table", list(v.t), format_func=EXPORT_LABELS.get)
        table(v.t[selected])
        st.download_button("Download selected table · CSV", safe_csv(v.t[selected]), f"{selected}.csv", "text/csv")
    with st.expander("Full investment memo"):
        st.markdown(memo(a))
    with st.expander("Save a local analysis record"):
        st.caption("Retain a reproducible copy of this recommendation and its assumptions on this computer.")
        state_key = analysis_key(a)
        if st.button("Save current analysis"):
            st.session_state.saved_run = Store(ROOT / "data/office.sqlite3").save(a)
            st.session_state.saved_state = state_key
        if st.session_state.get("saved_state") == state_key:
            st.success("The current investment analysis is saved locally.")
    with st.expander("Methods and limitations"):
        st.write(c.disclaimer)
        st.write(
            f"Financial outcomes use {c.n_samples:,} seeded Monte Carlo draws and quarterly discounting. "
            "Costs occur at programme start or deployment completion; recurring costs and benefits begin in subsequent quarters. "
            "Compliance lead time precedes deployment once. Quarter-by-quarter dependencies and resources are enforced before recommendation."
        )
        st.write(
            "The risk-adjusted selection objective penalizes the sum of investment expected losses. The ranked comparison uses the same constraints. Optimality is conditional on discrete rollout options and fixed phasing, not unrestricted sequencing."
        )
        st.caption(
            f"Optimization status: {p.status} · Objective bound: {eur(p.objective_bound, 2)} · "
            f"Relative gap: {p.relative_gap:.4%}. The bound refers to the risk-adjusted objective, not expected NPV."
        )
