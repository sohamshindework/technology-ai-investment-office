"""Explicit what-if assumptions, financial risk and changes in investment choices."""

import pandas as pd
import plotly.express as px
import streamlit as st

from frontend import state
from frontend.components import allocation_list, chart, delta_text, eur, status_label, table, wrap
from frontend.theme import TOKENS


def controls(case):
    st.subheader("Test investment assumptions")
    st.caption("Change an input and select Recalculate portfolio to compare the result. Draft edits do not affect exports.")
    for name, value in st.session_state.active_config.items():
        key = f"input_{name}"
        if key not in st.session_state:
            st.session_state[key] = value * 100 if name == "discount" else value
    with st.form("scenario_assumptions"):
        left, right = st.columns(2, gap="large")
        config = {}
        with left:
            config["budget_scale"] = st.slider(
                "Capital envelope × reference",
                0.5,
                1.5,
                step=0.05,
                key="input_budget_scale",
            )
            config["benefit_factor"] = st.slider(
                "Benefits / adoption × reference",
                0.0,
                1.5,
                step=0.05,
                key="input_benefit_factor",
            )
            config["discount"] = (
                st.number_input(
                    "Annual discount rate (%)",
                    0.0,
                    50.0,
                    step=1.0,
                    key="input_discount",
                )
                / 100
            )
        with right:
            config["extra_delay_months"] = st.slider(
                "Additional deployment delay (months)",
                0,
                24,
                step=3,
                key="input_extra_delay_months",
                help="Starts move in whole quarters within the unchanged rollout deadline. Time-to-value after deployment is unchanged.",
            )
            config["risk"] = st.slider(
                "Downside penalty",
                0.0,
                2.0,
                step=0.1,
                key="input_risk",
                help="Weight applied to expected losses in selection. A higher value favors downside protection.",
            )
            config["n_samples"] = st.select_slider(
                "Risk simulation samples",
                options=sorted({1000, 2000, 4000, 8000, case.n_samples}),
                key="input_n_samples",
                help="Number of possible outcomes used to estimate the range of investment value.",
            )
            config["carryover"] = st.toggle(
                "Carry unspent capital into later years",
                key="input_carryover",
            )
        submitted = st.form_submit_button("Recalculate portfolio", type="primary")
    if submitted:
        state.apply(st.session_state, config)
        st.rerun()
    st.button("Return to reference assumptions", on_click=state.reset, args=(st.session_state, case))
    st.caption(
        "Reset restores the case's financial and governance inputs. Cost and staffing pressures appear in the stress tests below."
    )


def choice_comparison(v, choice, label):
    rows = [
        {
            "Initiative": v.names[i.id],
            label: choice.get(i.id, 0),
            "Current deployments": v.p.choice[i.id],
            "Change": v.p.choice[i.id] - choice.get(i.id, 0),
        }
        for i in v.c.initiatives
    ]
    return pd.DataFrame(rows)


def render(v):
    a, c, p, ref = v.analysis, v.c, v.p, v.reference
    st.divider()
    st.subheader("Recommended portfolio")
    if a.spill:
        st.error("Some selected deployments fall outside the rollout deadline. Review the implementation plan.")
    else:
        st.success(f"All {sum(p.funded.values())} selected deployments fit the current capital and delivery limits.")
    cols = st.columns(3)
    comparison = v.previous or state.summary(ref)
    comparison_label = "previous scenario" if v.previous else "reference scenario"
    cols[0].metric("Expected NPV", eur(p.mean), delta_text(p.mean - comparison["npv"], comparison_label))
    cols[1].metric(
        "Capital required",
        eur(p.capex_by_year.sum()),
        f"of {eur(sum(c.budget_by_year))} envelope",
        delta_color="off",
        delta_arrow="off",
    )
    cols[2].metric(
        "Selected initiative types",
        len(p.funded),
        f"{sum(p.funded.values())} deployments",
        delta_color="off",
        delta_arrow="off",
    )
    changed = state.changes(st.session_state.active_config, ref.case)
    st.write(
        "**Changed assumptions:** "
        + (", ".join(changed) if changed else "Financial reference assumptions unchanged.")
        + (
            f" · {len(st.session_state.overrides)} governance questionnaire(s) edited."
            if st.session_state.overrides
            else ""
        )
    )
    st.caption(f"Reference NPV {eur(ref.portfolio.mean)} · Current NPV {eur(p.mean)}.")
    current_choices = choice_comparison(v, ref.portfolio.choice, "Reference deployments")
    differences = current_choices[current_choices.Change.ne(0)]
    if differences.empty:
        st.info(
            "The selected rollout scales match the reference scenario. Financial value can change while the investment choices remain the same."
        )
    else:
        st.markdown("**Investment choices changed from the reference**")
        table(differences)
    if v.previous:
        previous = choice_comparison(v, v.previous["choice"], "Previous deployments")
        with st.expander("Changes from the previous scenario"):
            table(previous[previous.Change.ne(0)])
            st.caption(
                "Only changed deployment scales are listed. An empty table means the financial assumptions changed without a change in the selected scales."
            )
    left, right = st.columns(2, gap="large")
    with left:
        f = pd.DataFrame(a.frontier)
        fig = px.line(
            f.assign(**{"Capital envelope (€m)": f.budget_total / 1000, "Expected NPV (€m)": f.expected_npv / 1000}),
            x="Capital envelope (€m)",
            y="Expected NPV (€m)",
            markers=True,
            title="Capital and value tradeoff",
        )
        fig.update_yaxes(rangemode="tozero")
        chart(fig)
        st.caption(
            "A flat curve means additional capital does not improve this recommendation under the other constraints. Each point recalculates the portfolio."
        )
    with right:
        fig = px.histogram(
            x=p.npv_samples / 1000,
            nbins=45,
            title="Range of investment outcomes",
            labels={"x": "Portfolio NPV (€m)", "count": "Modeled outcomes"},
        )
        chart(fig)
        st.caption(
            f"P10 {eur(p.pct(10))} · P90 {eur(p.pct(90))} · Negative-NPV probability {p.p_loss:.2%}, based on illustrative assumptions."
        )
    st.subheader("Stress-tested portfolios")
    st.write(
        "Each stress scenario recalculates the selected investments. NPV changes reflect both the assumption and the resulting portfolio."
    )
    s = a.scenarios.copy()
    s["label"] = s.scenario.map(lambda x: wrap(x, 27))
    s["NPV (€m)"] = s.expected_npv / 1000
    s["delta"] = (s.expected_npv - p.mean) / 1000
    fig = px.bar(
        s,
        x="delta",
        y="label",
        orientation="h",
        custom_data=["scenario", "NPV (€m)"],
        labels={"delta": "NPV change vs current (€m)", "label": ""},
    )
    fig.update_traces(
        marker_color=[TOKENS["negative"] if x < 0 else TOKENS["accent"] for x in s.delta],
        hovertemplate="%{customdata[0]}<br>NPV €%{customdata[1]:.2f}m<br>Change €%{x:.2f}m<extra></extra>",
    )
    fig.update_xaxes(zeroline=True, rangemode="tozero")
    with st.container(key="scenario-plot"):
        chart(fig, 530)
    allocation_list((row.scenario, eur(row.expected_npv)) for row in s.itertuples())
    display = s[["scenario", "status", "expected_npv", "p10_npv", "capex", "n_funded"]].copy()
    display["status"] = display.status.map(status_label)
    display = display.rename(
        columns={
            "scenario": "Scenario",
            "status": "Recommendation",
            "expected_npv": "NPV (€k)",
            "p10_npv": "P10 (€k)",
            "capex": "Capex (€k)",
            "n_funded": "Initiative types",
        }
    )
    table(display)
    scenario_names = [s for s in a.scenarios.scenario if s in a.robustness.columns]
    if scenario_names:
        selected = st.selectbox("Inspect a stress scenario", scenario_names)
        table(choice_comparison(v, a.robustness[selected].to_dict(), "Stress-scenario deployments"))
        st.caption(
            "Current deployments refer to the active recommendation; the comparison column shows the selected stress scenario."
        )
    with st.expander("Selection stability and annual cash flows"):
        robustness = a.robustness.reset_index(names="Initiative")
        robustness["Initiative"] = robustness.Initiative.map(v.names)
        table(
            robustness.rename(
                columns={
                    "funded_share": "Share of feasible scenarios funded",
                    "base_sites": "Current deployments",
                    "min_sites": "Minimum deployments",
                    "max_sites": "Maximum deployments",
                    "verdict": "Stability",
                }
            )
        )
        st.caption(
            "Funded in at least 85% of feasible scenarios is called robust. This threshold is not a statistical confidence level."
        )
        cf = v.t["cash_flows"].groupby("year", as_index=False).sum(numeric_only=True)
        table(
            cf.rename(
                columns={
                    "year": "Year",
                    "benefit_EUR_k": "Benefits (€k)",
                    "capex_EUR_k": "Capex (€k)",
                    "opex_EUR_k": "Operating costs (€k)",
                    "net_cash_EUR_k": "Net cash (€k)",
                    "discounted_cash_EUR_k": "Discounted cash (€k)",
                }
            )
        )
        st.caption(
            f"Discounted cash flows total {eur(cf.discounted_cash_EUR_k.sum())}, matching the portfolio NPV of {eur(p.mean)}."
        )
