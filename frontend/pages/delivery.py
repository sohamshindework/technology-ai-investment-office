"""One delivery workflow: quarterly rollout, governance checkpoints and benefits."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from frontend.components import chart, eur, table
from frontend.pages import benefits, governance
from frontend.theme import TOKENS


def render(v):
    rollout, review, tracking = st.tabs(["Rollout", "Governance", "Benefits"])
    with rollout:
        render_rollout(v)
    with review:
        governance.render(v)
    with tracking:
        benefits.render(v)


def render_rollout(v):
    a, c, p = v.analysis, v.c, v.p
    st.subheader("Implementation plan")
    if a.spill:
        st.error("Some selected deployments fall outside the rollout deadline. Revise the plan before proceeding.")
    else:
        last_q = max((r.quarter for r in a.roadmap if r.sites), default=0)
        st.success(
            f"All {sum(p.funded.values())} planned deployments are scheduled by Q{last_q}, within the {c.rollout_years * 12}-month deadline."
        )
    st.write(
        "The plan phases each investment quarterly. These dates determine capital spending, operating costs and planned benefits."
    )
    road = v.t["roadmap"]
    if road.empty:
        st.info("No deployment activities are required for the current portfolio.")
        return
    road = road.assign(Initiative=road.initiative_id.map(v.names))
    ids = list(dict.fromkeys(road.initiative_id))
    labels = {iid: f"{n + 1:02}" for n, iid in enumerate(ids)}
    road["Investment"] = road.initiative_id.map(labels)
    road["Activity"] = road.activity.map(
        {"gate": "Review gate", "programme": "Programme team", "deploy": v.deployment_unit["singular"].capitalize()}
    ).fillna(v.deployment_unit["singular"].capitalize())
    fig = px.scatter(
        road,
        x="quarter",
        y="Investment",
        color="Activity",
        size=road.sites.clip(lower=2),
        size_max=14,
        custom_data=["Initiative", "Activity", "sites", "cumulative_sites", "fte_used"],
        color_discrete_map={
            "Review gate": TOKENS["warning"],
            "Programme team": "#496E83",
            v.deployment_unit["singular"].capitalize(): v.accent,
        },
        title=f"{c.rollout_years * 12}-month rollout schedule",
    )
    fig.update_traces(
        hovertemplate="%{customdata[0]}<br>Q%{x}: %{customdata[1]}<br>%{customdata[2]} deployments · %{customdata[3]} cumulative<br>%{customdata[4]:.2f} FTE-years<extra></extra>"
    )
    fig.update_xaxes(
        range=[0.5, c.rollout_years * 4 + 0.5],
        tickmode="array",
        tickvals=list(range(1, c.rollout_years * 4 + 1)),
        ticktext=[str(n) for n in range(1, c.rollout_years * 4 + 1)],
        tickangle=0,
        title="Quarter",
    )
    fig.update_yaxes(type="category", categoryorder="array", categoryarray=list(reversed(list(labels.values()))))
    chart(fig, max(290, 70 * len(ids) + 130))
    st.caption(
        "Investment key · circle size indicates deployments. Review and programme-team markers have a minimum display size and do not imply deployments."
    )
    for iid in ids:
        st.write(f"**{labels[iid]}** · {v.names[iid]}")
    q = (
        road.groupby("quarter")
        .agg({"fte_used": "sum", "sites": "sum"})
        .reindex(range(1, c.rollout_years * 4 + 1), fill_value=0)
        .rename_axis("quarter")
        .reset_index()
    )
    q["fte_capacity"] = q.quarter.map(lambda n: c.fte_capacity_by_year[(n - 1) // 4] / 4)
    q["site_limit"] = c.max_sites_per_quarter
    cols = st.columns(2, gap="large")
    for col, field, limit, title, unit in [
        (cols[0], "sites", "site_limit", "Quarterly deployment capacity", "Deployments"),
        (cols[1], "fte_used", "fte_capacity", "Quarterly implementation effort", "FTE-years"),
    ]:
        with col:
            fig = go.Figure()
            fig.add_bar(x=q.quarter, y=q[field], name="Required", marker_color=v.accent)
            fig.add_scatter(
                x=q.quarter, y=q[limit], name="Limit", mode="lines", line=dict(color=TOKENS["warning"], dash="dash")
            )
            fig.update_layout(title=title, yaxis_title=unit)
            fig.update_xaxes(title="Quarter", dtick=2)
            fig.update_yaxes(rangemode="tozero")
            chart(fig, 310)
    st.subheader("Prerequisites and review points")
    rows = []
    for i in c.initiatives:
        if i.id not in p.funded:
            continue
        for d in i.requires:
            rows.append(
                {
                    "Investment": i.name,
                    "Prerequisite": v.names[d.initiative],
                    "Requirement": (
                        f"Earlier-quarter coverage; {d.baseline_sites} existing {v.deployment_unit['coverage_noun']}"
                        if d.baseline_sites
                        else "Enabling coverage must complete in an earlier quarter"
                    )
                    if d.mode == "sites"
                    else "Enabling investment in an earlier quarter",
                }
            )
        if i.pilot_gate:
            st.write(f"**Pilot checkpoint · {i.name}**")
            st.write(
                "Pilot evidence is "
                + ("recorded in the case assumptions" if i.pilot_gate.get("approved") else "awaiting approval")
                + "; confirm it remains applicable before deployment."
            )
    if rows:
        table(pd.DataFrame(rows))
    else:
        st.write("No inter-investment prerequisites are defined for the selected portfolio.")
    st.write("Before launch, confirm pilot evidence, intended use and any required compliance or workforce review.")
    st.caption(
        "Implementation risks include review delays, prerequisite availability and benefit realization. The scenario tests explore adverse timing, costs, staffing and adoption."
    )
    st.subheader("Planned operating benefits")
    cash = v.t["quarterly_cash_flows"].groupby("quarter", as_index=False).benefit_EUR_k.sum()
    fig = px.line(
        cash.assign(**{"Benefits (€m)": cash.benefit_EUR_k / 1000}),
        x="quarter",
        y="Benefits (€m)",
        labels={"quarter": "Quarter"},
        title="Benefits after deployment and ramp-up",
    )
    fig.update_yaxes(rangemode="tozero")
    chart(fig, 300)
    st.caption(
        f"Illustrative gross benefits over {c.horizon_years} years: {eur(cash.benefit_EUR_k.sum())}. Benefits begin after deployment and the assumed time-to-value."
    )
    with st.expander("Quarterly resources and full schedule"):
        table(
            q.rename(
                columns={
                    "quarter": "Quarter",
                    "fte_used": "Required FTE-years",
                    "sites": "Deployments",
                    "fte_capacity": "FTE-years limit",
                    "site_limit": "Deployment limit",
                }
            )
        )
        table(
            road.drop(columns=["initiative_id", "Investment", "Activity"]).rename(
                columns={
                    "quarter": "Quarter",
                    "activity": "Activity",
                    "sites": "Deployments",
                    "cumulative_sites": "Cumulative deployments",
                    "fte_used": "FTE-years",
                }
            )
        )
