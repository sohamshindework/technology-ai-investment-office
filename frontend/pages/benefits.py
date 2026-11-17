"""Planned benefits, validated observations and management follow-up."""

import io

import pandas as pd
import plotly.express as px
import streamlit as st

from frontend.components import chart, eur, table
from invest_engine.benefits import (
    MATERIAL_VARIANCE_EUR_K,
    MATERIAL_VARIANCE_PERCENT,
    fictional_observations,
    follow_up_items,
    import_actuals,
    initiative_summary,
    observation_template,
    portfolio_summary,
    validate_observations,
)
from invest_engine.reporting import safe_csv


def capture_upload(plan, case, key):
    upload = st.session_state.get(key)
    if upload is None:
        return
    try:
        if upload.size > 2_000_000:
            raise ValueError("Choose a CSV smaller than 2 MB.")
        raw = upload.getvalue()
        observations = pd.read_csv(io.BytesIO(raw))
        validated = validate_observations(observations, case, max_quarter=max(int(plan.quarter.max()), 6))
        import_actuals(plan, validated, case=case)
        st.session_state.benefits_actuals = validated.to_csv(index=False).encode()
        st.session_state.benefits_import_error = None
    except (ValueError, TypeError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        st.session_state.benefits_import_error = str(exc)


def clear_import():
    st.session_state.pop("benefits_actuals", None)
    st.session_state.benefits_import_error = None
    st.session_state.benefits_upload_revision = st.session_state.get("benefits_upload_revision", 0) + 1


def load_fictional(plan):
    st.session_state.benefits_actuals = fictional_observations(plan).to_csv(index=False).encode()
    st.session_state.benefits_import_error = None
    st.session_state.benefits_upload_revision = st.session_state.get("benefits_upload_revision", 0) + 1


def apply_import(analysis):
    raw = st.session_state.get("benefits_actuals")
    if raw is not None:
        observations = pd.read_csv(io.BytesIO(raw))
        analysis.benefits = import_actuals(analysis.benefits, observations, case=analysis.case)


def render(v):
    st.subheader("Benefits realization")
    st.write(
        "Compare observed benefits with the matching quarterly plan. Observations support management review; they do not change the investment recommendation or prove causal attribution."
    )
    b = v.analysis.benefits.copy()
    if b.empty:
        st.info("No selected investments have benefits to track. Review the portfolio or change the assumptions.")
        if st.session_state.get("benefits_actuals") is not None:
            st.caption("Previously imported observations remain in this session and will be reapplied if investments are selected again.")
            st.button("Clear observations", on_click=clear_import)
        return

    controls = st.columns([1.1, 1, 1])
    cutoff = controls[0].select_slider(
        "Reporting period",
        options=list(range(1, int(b.quarter.max()) + 1)),
        value=int(b.quarter.max()),
        format_func=lambda value: f"Through Q{value}",
        key=f"benefits_period_{v.c.id}",
    )
    controls[1].download_button(
        "Download observation template",
        safe_csv(observation_template(b)),
        f"{v.c.id}_benefits_observation_template.csv",
        "text/csv",
    )
    controls[2].button("Load fictional example", on_click=load_fictional, args=(b,))

    key = f"benefits_upload_{st.session_state.get('benefits_upload_revision', 0)}"
    st.file_uploader(
        "Import benefit observations · CSV",
        type=["csv"],
        key=key,
        help=(
            "Use the downloadable template. Required fields identify company, initiative, reporting quarter, "
            "period end, observed benefit in EUR thousands, source, observation date, confidence, revision and "
            "whether the data is fictional. Maximum 2 MB; data remains in this browser session."
        ),
        on_change=capture_upload,
        args=(b, v.c, key),
    )
    if st.session_state.get("benefits_import_error"):
        st.error(f"The observation file could not be imported: {st.session_state.benefits_import_error}")
        st.info("Correct the file and upload it again. The last accepted observations remain active.")

    has_observations = b.observed_benefit_EUR_k.notna().any()
    if has_observations:
        simulated = bool(b.loc[b.observed_benefit_EUR_k.notna(), "is_simulated"].fillna(False).any())
        if simulated:
            st.warning("Fictional demonstration observations are active. They are not company performance data.")
        else:
            st.info("User-provided observations are active and have not been independently verified.")
        st.button("Clear observations", on_click=clear_import)
    else:
        st.info("Observed benefits are unavailable. Import a validated file or load the clearly labeled fictional example.")

    summary = portfolio_summary(b, cutoff)
    cols = st.columns(4)
    cols[0].metric("Planned for reported periods", eur(summary["planned"]) if summary["observed"] is not None else "Unavailable")
    cols[1].metric("Observed benefits", eur(summary["observed"]) if summary["observed"] is not None else "Unavailable")
    cols[2].metric("Variance", eur(summary["variance"]) if summary["variance"] is not None else "Unavailable")
    cols[3].metric("Observation coverage", f"{summary['coverage']:.0%}")
    st.caption(
        "The comparison includes only periods with an observation. Missing periods are excluded, not treated as zero. "
        f"Material deviation requires at least {MATERIAL_VARIANCE_PERCENT:.0%} and €{MATERIAL_VARIANCE_EUR_K:,.0f}k absolute variance; a zero plan uses the absolute threshold."
    )

    chart_data = b[b.quarter <= cutoff].copy()
    chart_data["Planned for observed periods"] = chart_data.planned_benefit.where(
        chart_data.observed_benefit_EUR_k.notna()
    )
    quarterly = (
        chart_data.groupby("quarter", as_index=False)
        .agg(
            **{
                "Planned for observed periods": ("Planned for observed periods", lambda values: values.sum(min_count=1)),
                "Observed benefits": ("observed_benefit_EUR_k", lambda values: values.sum(min_count=1)),
            }
        )
        .rename(columns={"quarter": "Quarter"})
    )
    quarterly[["Planned for observed periods", "Observed benefits"]] /= 1000
    fig = px.bar(
        quarterly,
        x="Quarter",
        y=["Planned for observed periods", "Observed benefits"],
        barmode="group",
        title="Quarterly planned and observed benefits",
        labels={"value": "Benefits (€m)", "variable": ""},
    )
    fig.update_yaxes(rangemode="tozero")
    chart(fig)

    detail = initiative_summary(b, cutoff).assign(
        Initiative=lambda frame: frame.initiative_id.map(v.names),
        **{"Material follow-up": lambda frame: frame.material_deviation.map({True: "Required", False: "No"})},
    )
    display = detail[
        [
            "Initiative", "planned_for_observed", "observed_benefit", "variance_EUR_k", "variance_percent",
            "coverage", "missing_periods", "confidence", "Material follow-up", "observation_type",
        ]
    ].rename(
        columns={
            "planned_for_observed": "Plan for observed periods (€k)",
            "observed_benefit": "Observed benefits (€k)",
            "variance_EUR_k": "Variance (€k)",
            "variance_percent": "Variance (%)",
            "coverage": "Coverage",
            "missing_periods": "Missing periods",
            "confidence": "Confidence",
            "observation_type": "Observation type",
        }
    )
    table(display)
    st.caption(
        "Observed changes may have multiple causes. Validate the source, baseline, benefit definition and attribution evidence before making a follow-up decision."
    )

    items = follow_up_items(b, cutoff)
    st.markdown("#### Follow-up questions")
    if items:
        for item in items:
            st.write(f"- {item}")
    else:
        st.write("No material variance, missing-period or low-confidence follow-up is identified for this reporting period.")

    with st.expander("Observation detail and validation rules"):
        table(
            b[b.quarter <= cutoff].drop(columns=["example_observed_benefit"], errors="ignore").rename(
                columns={
                    "company_id": "Company ID",
                    "initiative_id": "Initiative ID",
                    "quarter": "Quarter",
                    "planned_benefit": "Planned benefit (€k)",
                    "observed_benefit_EUR_k": "Observed benefit (€k)",
                    "variance_EUR_k": "Variance (€k)",
                    "variance_percent": "Variance (%)",
                    "reporting_period_end": "Reporting period end",
                    "observation_date": "Observation date",
                    "source": "Source",
                    "confidence": "Confidence",
                    "revision": "Revision",
                    "observation_status": "Status",
                    "is_simulated": "Fictional",
                }
            )
        )
        st.write(
            "Imports must match the active company and a registered initiative. Quarter values must align with calendar quarter-end dates. Currency must be EUR. Sources, observation dates, confidence and positive revision numbers are required. Duplicate company/initiative/quarter rows are rejected. Zero and negative observations are retained as reported values."
        )
    st.download_button("Download benefits review · CSV", safe_csv(b), "benefits_realization.csv", "text/csv")
