"""Shared typography, charts, tables and business-facing presentation helpers."""

from __future__ import annotations

import base64
import hashlib
import html
import math
import textwrap
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from invest_engine.reporting import bundle, tables

from .theme import CHART_COLORS, TOKENS, css_variables

ROOT = Path(__file__).resolve().parents[1]


@st.cache_data
def styles(accent=None):
    faces = []
    for family, weights in (("Inter", "100 900"), ("Manrope", "200 800")):
        data = base64.b64encode((ROOT / "assets/fonts" / f"{family}.woff").read_bytes()).decode()
        faces.append(
            f"@font-face{{font-family:'{family}';font-style:normal;font-weight:{weights};"
            f"font-display:swap;src:url(data:font/woff;base64,{data}) format('woff');}}"
        )
    return "".join(faces) + css_variables(accent) + (ROOT / "assets/style.css").read_text()


def analysis_key(analysis):
    """Reviews and saved-state feedback identify the complete current report, including actuals."""
    return hashlib.sha256(bundle(analysis)).hexdigest()


def eur(value, precision=1):
    if value is None or not math.isfinite(value):
        return "Unavailable"
    sign = "−" if value < 0 else ""
    return f"{sign}€{abs(value) / 1000:,.{precision}f}m"


def delta_text(value, comparison):
    # Streamlit's semantic delta parser recognizes an ASCII minus sign.
    sign = "-" if value < 0 else "+"
    return f"{sign}{eur(abs(value))} vs {comparison}"


def wrap(value, width=30):
    return "<br>".join(textwrap.wrap(html.escape(str(value)), width))


def status_label(status):
    return {"OPTIMAL": "Recommended portfolio", "FEASIBLE": "Feasible portfolio"}.get(
        status, "No feasible recommendation"
    )


def chart(fig, height=340, *, key=None):
    fig.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", size=13, color=TOKENS["body"]),
        margin=dict(l=12, r=45, t=55 if fig.layout.title.text else 16, b=55),
        title=dict(font=dict(family="Manrope, sans-serif", size=17, color=TOKENS["primary"]), x=0),
        legend_title_text="",
        legend=dict(orientation="h", y=-0.25, x=0),
        hoverlabel=dict(bgcolor="white", font=dict(family="Inter", size=13), bordercolor=TOKENS["border"]),
        colorway=CHART_COLORS,
        bargap=0.35,
    )
    fig.update_xaxes(showgrid=False, zerolinecolor=TOKENS["border"], automargin=True)
    fig.update_yaxes(gridcolor=TOKENS["border"], zerolinecolor=TOKENS["border"], automargin=True)
    if any(trace.type == "histogram" for trace in fig.data):
        fig.update_yaxes(title_text="Modeled outcomes", rangemode="tozero")
        fig.update_layout(bargap=0.04)
    st.plotly_chart(fig, width="stretch", key=key, config={"displayModeBar": False, "responsive": True})


def table(frame, **kwargs):
    """Format a presentation copy without rounding the source or exported data."""
    config = {}
    for column in frame.columns:
        if column in {"Initiative", "Investment initiative", "Investment", "Prerequisite"}:
            config[column] = st.column_config.TextColumn(column, width="large")
        elif pd.api.types.is_numeric_dtype(frame[column]):
            fmt = "%.2f" if any(s in column for s in ("€", "FTE", "Ratio", "Share")) else None
            config[column] = st.column_config.NumberColumn(column, format=fmt)
    config.update(kwargs.pop("column_config", {}))
    st.dataframe(frame.copy(), column_config=config, hide_index=True, width="stretch", **kwargs)


def allocation_list(rows):
    content = "".join(
        f'<div class="allocation-row"><span>{html.escape(str(label))}</span><strong>{html.escape(str(value))}</strong></div>'
        for label, value in rows
    )
    st.markdown(f'<div class="compact-allocation">{content}</div>', unsafe_allow_html=True)


@dataclass
class View:
    analysis: object
    reference: object | None = None
    previous: dict | None = None

    def __post_init__(self):
        self.c = self.analysis.case
        self.accent = self.c.profile.accent["primary"] if self.c.profile else TOKENS["accent"]
        self.deployment_unit = self.c.profile.deployment_unit if self.c.profile else {"singular": "site deployment", "plural": "site deployments", "definition": "one initiative at one site", "coverage_noun": "sites"}
        self.p = self.analysis.portfolio
        self.t = tables(self.analysis)
        self.names = {i.id: i.name for i in self.c.initiatives}
        self.funded = self.t["portfolio"].query("sites > 0").copy()


def rationale(v, initiative):
    i, p = initiative, v.p
    screening = v.analysis.screenings[i.id]
    if screening.excluded:
        return "Not eligible: resolve governance questions before investment."
    if i.id not in p.funded:
        if i.pilot_gate and not i.pilot_gate.get("approved"):
            return "Pilot evidence and approval required before rollout."
        return "Deferred under current value, dependency and delivery constraints; compare rollout alternatives below."
    dependencies = [
        d
        for j in v.c.initiatives
        if j.id in p.funded
        for d in j.requires
        if d.initiative == i.id
    ]
    downstream = sum(any(d.initiative == i.id for d in j.requires) for j in v.c.initiatives if j.id in p.funded)
    if downstream:
        detail = (
            "Existing coverage and new rollout are assessed together."
            if any(d.baseline_sites for d in dependencies)
            else "The enabling rollout must complete before dependent deployments."
        )
        return f"{downstream} selected {'initiative references' if downstream == 1 else 'initiatives reference'} this prerequisite. {detail}"
    return "Selected within the current capital and delivery limits."


def recommendation(v, *, compact=False):
    p, c = v.p, v.c
    count = len(p.funded)
    heading = (
        f"Fund {count} {'initiative type' if count == 1 else 'initiative types'}. Sequence {sum(p.funded.values()):,} {'deployment' if sum(p.funded.values()) == 1 else 'deployments'}."
        if count
        else "Hold investment under the current assumptions."
    )
    st.markdown(
        '<div class="recommendation"><p class="eyebrow">Recommended portfolio</p>'
        f"<h2>{heading}</h2><p>"
        + (
            f"Commit {eur(p.capex_by_year.sum())} over {c.rollout_years} years for an expected NPV of {eur(p.mean)} "
            f"over {c.horizon_years} years. The recommendation accounts for enabling investments, uncertainty and delivery capacity."
            if count
            else "No investment is selected. Review value assumptions, eligibility and delivery limits in Scenario Lab."
        )
        + "</p></div>",
        unsafe_allow_html=True,
    )
    if not compact:
        financial_summary(v)


def financial_summary(v):
    p, c = v.p, v.c
    count = len(p.funded)
    cols = st.columns([1.2, 1.2, 1])
    cols[0].metric(
        "Expected investment value (NPV)",
        eur(p.mean),
        delta_text(p.mean - v.analysis.baseline.mean, "ranked list")
        if v.analysis.baseline
        else "Ranked comparison unavailable",
    )
    cols[1].metric(
        "Capital required",
        eur(p.capex_by_year.sum()),
        f"of {eur(sum(c.budget_by_year))} envelope",
        delta_color="off",
        delta_arrow="off",
    )
    cols[2].metric(
        "Scheduled deployments",
        f"{sum(r.sites for r in v.analysis.roadmap):,}",
        f"across {count} {'initiative type' if count == 1 else 'initiative types'}",
        delta_color="off",
        delta_arrow="off",
    )


def investment_table(v):
    rows = [
        {
            "Investment": i.name,
            "Deployments": v.p.choice[i.id],
            "Capex (€m)": v.analysis.valuations[i.id][v.p.choice[i.id]].capex_by_year.sum() / 1000,
            "NPV (€m)": v.analysis.valuations[i.id][v.p.choice[i.id]].mean / 1000,
            "Investment rationale": rationale(v, i),
        }
        for i in v.c.initiatives
        if i.id in v.p.funded
    ]
    if rows:
        with st.container(key="investment-summary-table"):
            table(pd.DataFrame(rows))
        allocation_list(
            (row["Investment"], f"{row['Deployments']} {'deployment' if row['Deployments'] == 1 else 'deployments'}")
            for row in rows
        )
    else:
        st.info("No investments are selected under the current assumptions.")


def set_chart_defaults(accent=None):
    px.defaults.color_discrete_sequence = [accent or CHART_COLORS[0], *CHART_COLORS[1:]]
