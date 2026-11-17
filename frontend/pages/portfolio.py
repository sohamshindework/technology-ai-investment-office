"""Recommendation, investment comparison and evidence/assumption inspection."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from frontend.components import (
    allocation_list,
    chart,
    eur,
    financial_summary,
    investment_table,
    rationale,
    recommendation,
    table,
    wrap,
)
from frontend.pages import research
from frontend.theme import TOKENS


def render(v):
    a, c, p = v.analysis, v.c, v.p
    recommendation(v, compact=True)
    st.subheader("Recommended investments")
    st.caption(f"Initiative types are investment categories. Deployment unit: {v.deployment_unit['definition']}")
    investment_table(v)
    financial_summary(v)
    with st.expander("Investment scope and limits"):
        st.write(c.question)
        st.write(
            f"Capital envelope: {eur(sum(c.budget_by_year))} across {c.rollout_years} years. "
            f"Delivery ceiling: {c.max_sites_per_quarter} deployments per quarter. "
            "Quarterly staffing and prior-quarter prerequisites also constrain selection."
        )
    left, right = st.columns([1.5, 1], gap="large")
    with left:
        st.subheader("Contribution to expected value")
        if not v.funded.empty:
            data = v.funded.sort_values("npv_EUR_k").assign(
                value=lambda d: d.npv_EUR_k / 1000, label=lambda d: d.name.map(wrap)
            )
            fig = px.bar(
                data,
                x="value",
                y="label",
                orientation="h",
                custom_data=["name", "sites"],
                labels={"value": "Expected NPV (€m)", "label": ""},
            )
            fig.update_traces(
                text=[eur(n, 2) for n in data.npv_EUR_k],
                texttemplate="%{text}",
                textposition="outside",
                cliponaxis=False,
                hovertemplate="%{customdata[0]}<br>NPV €%{x:.2f}m<br>%{customdata[1]} deployments<extra></extra>",
            )
            fig.update_xaxes(rangemode="tozero")
            with st.container(key="attribution-plot"):
                chart(fig, max(320, len(data) * 85 + 90))
            allocation_list(
                (r["name"], eur(r["npv_EUR_k"], 2))
                for r in v.funded.sort_values("npv_EUR_k", ascending=False).to_dict("records")
            )
            if c.profile and "function_value" in c.profile.views["portfolio"]:
                st.caption("Expected value by business function; amounts are modeled NPV, not measured operational KPI gains.")
                by_function = v.funded.groupby("function", as_index=False).npv_EUR_k.sum()
                by_function["expected_npv_m"] = by_function.npv_EUR_k / 1000
                fig = px.bar(
                    by_function,
                    x="function",
                    y="expected_npv_m",
                    labels={"function": "Business function", "expected_npv_m": "Expected NPV (€m)"},
                    color_discrete_sequence=[v.accent],
                )
                chart(fig, 285)
    with right:
        st.subheader("Value beyond a ranked list")
        if a.baseline:
            fig = go.Figure(
                go.Waterfall(
                    x=["Ranked list", "Portfolio uplift", "Recommended"],
                    measure=["absolute", "relative", "total"],
                    y=[a.baseline.mean / 1000, (p.mean - a.baseline.mean) / 1000, 0],
                    text=[eur(a.baseline.mean), eur(p.mean - a.baseline.mean), eur(p.mean)],
                    textposition="outside",
                    connector=dict(line=dict(color=TOKENS["border"])),
                    increasing=dict(marker=dict(color=v.accent)),
                    decreasing=dict(marker=dict(color=TOKENS["negative"])),
                    totals=dict(marker=dict(color="#496E83")),
                    hovertemplate="%{x}<br>€%{y:.2f}m<extra></extra>",
                )
            )
            fig.update_yaxes(title="Expected NPV (€m)", rangemode="tozero")
            chart(fig, 345)
            st.caption(
                "Both approaches face the same constraints. Portfolio selection evaluates enabling investments together; a ranked list funds candidates sequentially."
            )
        else:
            st.info("The ranked-list comparison has no feasible recommendation under these assumptions.")
    with st.expander("Annual capital and implementation capacity"):
        cols = st.columns(2)
        years = [f"Year {n + 1}" for n in range(c.rollout_years)]
        for col, title, available, used, unit in [
            (
                cols[0],
                "Capital allocation",
                [x / 1000 for x in c.budget_by_year],
                p.capex_by_year[: c.rollout_years] / 1000,
                "Capex (€m)",
            ),
            (cols[1], "Implementation capacity", c.fte_capacity_by_year, p.fte_by_year[: c.rollout_years], "FTE-years"),
        ]:
            with col:
                fig = go.Figure()
                fig.add_bar(x=years, y=available, name="Available", marker_color="#DCEBE6")
                fig.add_bar(x=years, y=used, name="Required", marker_color=v.accent)
                fig.update_layout(title=title, barmode="group", yaxis_title=unit)
                fig.update_yaxes(rangemode="tozero")
                chart(fig, 310)
    st.divider()
    st.subheader("Evaluate the investment candidates")
    st.caption("Compare selected investments with alternatives. Open an initiative to review its case and assumptions.")
    col1, col2, col3 = st.columns([1.5, 1, 1])
    query = col1.text_input("Search initiatives", key="candidate_search")
    functions = col2.multiselect(
        "Business function", sorted(v.t["portfolio"].function.unique()), key="candidate_functions"
    )
    selection = col3.selectbox("Funding decision", ["All", "Funded", "Deferred"], key="candidate_funding")
    view = v.t["portfolio"]
    view = view[view.name.str.contains(query, case=False, regex=False)]
    if functions:
        view = view[view.function.isin(functions)]
    if selection != "All":
        view = view[view.sites.gt(0) if selection == "Funded" else view.sites.eq(0)]
    if view.empty:
        st.info("No initiatives match these filters. Clear the search or choose another function or funding decision.")
        return
    display = view.assign(
        Decision=lambda d: d.sites.map(lambda n: "Fund" if n else "Defer"),
        **{"NPV (€m)": view.npv_EUR_k / 1000, "Capex (€m)": view.capex_EUR_k / 1000},
    )
    table(
        display[["name", "Decision", "sites", "NPV (€m)", "Capex (€m)"]].rename(
            columns={"name": "Initiative", "sites": "Deployments"}
        )
    )
    iid = st.selectbox("Inspect investment", view.id.tolist(), format_func=v.names.get, key=f"candidate_inspect_{c.id}")
    i = c.get(iid)
    st.markdown(f"#### {i.name}")
    st.write(i.description)
    st.write(rationale(v, i))
    st.caption(i.status_label)
    with st.expander("Evidence, prerequisites and pilot approval", expanded=False):
        st.write(i.public_basis or "No published company evidence is linked to this proposed investment.")
        for sid in i.sources:
            src = c.sources[sid]
            st.markdown(f"[{sid}: {src['title']}]({src['url']})")
        for d in i.requires:
            st.write(
                f"Prerequisite: {v.names[d.initiative]}. "
                + (
                    (
                        f"Coverage uses {d.baseline_sites} existing {v.deployment_unit['coverage_noun']} plus deployments completed in earlier quarters."
                        if d.baseline_sites
                        else "Enabling coverage must complete in an earlier quarter."
                    )
                    if d.mode == "sites"
                    else "An enabling rollout must complete in an earlier quarter."
                )
            )
        if not i.requires:
            st.write("No investment prerequisite is specified.")
        st.write(i.assumption_notes or "The cost and benefit assumptions need review by the relevant business owner.")
        if i.pilot_gate:
            gate = i.pilot_gate
            state = "recorded in the case assumptions" if gate.get("approved") else "pending"
            st.warning(
                f"Pilot review {state}. The assumed minimum success rate is "
                f"{gate['min_success_probability']:.0%}. {gate['evidence']}"
            )
    with st.expander("Financial assumptions and rollout alternatives"):
        assumptions = (
            v.t["assumptions"]
            .query("id == @iid")
            .drop(columns=["id", "nature"])
            .rename(
                columns={"input": "Assumption", "low": "Low", "mode": "Most likely", "high": "High", "unit": "Unit"}
            )
        )
        assumptions["Assumption"] = assumptions.Assumption.str.replace("_", " ").str.capitalize()
        table(assumptions)
        opts = (
            v.t["options"]
            .query("id == @iid")
            .drop(columns="id")
            .rename(
                columns={
                    "sites": "Deployments",
                    "npv_EUR_k": "Expected NPV (€k)",
                    "rollout_window_valid": "Fits rollout window",
                    "score_EUR_k": "Risk-adjusted score (€k)",
                    "payback_year": "Payback (years)",
                    "p_loss": "Loss probability",
                    "capex_EUR_k": "Capex (€k)",
                    "breakeven_success": "Break-even success probability",
                }
            )
        )
        table(opts)
        st.caption(
            "Payback uses undiscounted mean cash flows and requires recovery through the remaining horizon. Break-even success is a financial threshold, not evidence of pilot success."
        )
    if c.profile and "manufacturing_kpi_scorecard" in c.profile.views["portfolio"]:
        st.subheader("Manufacturing measures to validate")
        st.caption("Local baselines and benefit attribution remain to be confirmed by production and finance owners.")
        table(pd.DataFrame([
            {"Measure": k["label"], "Unit": {"percent_0_100": "%", "EUR/vehicle": "€/vehicle"}.get(k["unit"], k["unit"]), "Direction": k["direction"], "Owner": k["owner"]}
            for k in c.profile.kpis
        ]))
    if c.profile and {"claims_kpi_scorecard", "service_kpi_scorecard"} & set(c.profile.views["portfolio"]):
        st.subheader("Operating measures to validate")
        st.caption("Claim and contact baselines have not been supplied. Confirm denominators before approving benefits.")
        for view_id, heading, is_service in (
            ("claims_kpi_scorecard", "Claims operations", False),
            ("service_kpi_scorecard", "Customer service", True),
        ):
            if view_id not in c.profile.views["portfolio"]:
                continue
            rows = [
                {"Measure": k["label"], "Unit": {"percent_0_100": "%", "EUR/claim": "€/claim"}.get(k["unit"], k["unit"]), "Direction": k["direction"], "Owner": k["owner"]}
                for k in c.profile.kpis
                if any(c.get(iid).function == "Customer service" for iid in k["initiative_ids"]) == is_service
            ]
            if rows:
                st.markdown(f"**{heading}**")
                table(pd.DataFrame(rows))
    st.divider()
    with st.expander("Research a potential investment"):
        research.render(v)
