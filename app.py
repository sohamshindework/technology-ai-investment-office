"""Technology investment workflows. Run: streamlit run app.py."""

from __future__ import annotations

import html
import json
from pathlib import Path

import streamlit as st

from frontend import state
from frontend.components import View, set_chart_defaults, styles
from frontend.pages import benefits, brief, delivery, portfolio, scenario
from invest_engine import load_case
from invest_engine.branding import DASHBOARD_DESCRIPTION, DASHBOARD_TITLE, PAGES, PROJECT_TITLE, SUBTITLE
from invest_engine.case_config import admitted_cases, case_fingerprint
from invest_engine.service import CALCULATION_VERSION, analyse

ROOT = Path(__file__).resolve().parent
CASES = admitted_cases(ROOT)
st.set_page_config(page_title=PROJECT_TITLE, layout="wide")


@st.cache_data(show_spinner="Updating the portfolio and implementation plan…")
def run(folder, fingerprint, config_json):
    return analyse(load_case(folder), **json.loads(config_json))


st.sidebar.markdown(
    f'<div class="brand">{html.escape(PROJECT_TITLE)}<span class="brand-sub">{html.escape(SUBTITLE)}</span></div>',
    unsafe_allow_html=True,
)
folder = st.sidebar.selectbox(
    "Case study", [str(p) for p in CASES], format_func=lambda p: load_case(p).company, key="case_selector"
)
case = load_case(folder)
fingerprint = case_fingerprint(folder, CALCULATION_VERSION)
state.initialize(st.session_state, f"{folder}:{fingerprint}", case)
accent = case.profile.accent["primary"] if case.profile else None
st.markdown(f"<style>{styles(accent)}</style>", unsafe_allow_html=True)
set_chart_defaults(accent)
st.sidebar.caption(case.title)
page = st.sidebar.radio("Workspace", PAGES, key="navigation", label_visibility="collapsed")
changed = state.changes(st.session_state.active_config, case)
st.sidebar.divider()
st.sidebar.markdown("**Active scenario**")
st.sidebar.caption(
    "Reference assumptions"
    if not changed and not st.session_state.overrides
    else ", ".join(changed + (["Governance design"] if st.session_state.overrides else []))
)
st.sidebar.caption("Current selections and exports use these assumptions.")
st.markdown(
    f'<div class="workspace-top"><span>{html.escape(case.title)}</span>'
    '<span class="case-kind">Illustrative case study</span></div>',
    unsafe_allow_html=True,
)
st.title(DASHBOARD_TITLE if page == PAGES[0] else page)
descriptions = {
    PAGES[0]: DASHBOARD_DESCRIPTION,
    PAGES[1]: "Adjust assumptions and compare investment outcomes.",
    PAGES[2]: "Review rollout timing, capacity and key prerequisites.",
    PAGES[3]: "Review the proposed decision, financial rationale and key considerations.",
}
st.markdown(f'<p class="page-deck">{descriptions[page]}</p>', unsafe_allow_html=True)
if page == PAGES[1]:
    scenario.controls(case)
config = {**st.session_state.active_config, "overrides": st.session_state.overrides}
try:
    a = run(folder, fingerprint, json.dumps(config, sort_keys=True))
except (ValueError, RuntimeError, KeyError) as exc:
    st.session_state.last_summary = None
    st.error("No investment recommendation is available for these assumptions.")
    st.info(
        "Review the capital envelope, delivery limits, commitments and governance answers, or return to the reference assumptions."
    )
    st.button("Restore reference assumptions", on_click=state.reset, args=(st.session_state, case))
    with st.expander("What prevented a recommendation"):
        st.write(str(exc))
    st.stop()
if a.portfolio.status != "OPTIMAL":
    st.warning(
        "This portfolio fits the current limits, but a higher-value choice may exist. Review optimization details in Decision Brief."
    )
reference = None
if page == PAGES[1]:
    reference = run(folder, fingerprint, json.dumps({**state.defaults(case), "overrides": {}}, sort_keys=True))
benefits.apply_import(a)
v = View(a, reference, st.session_state.previous_scenario)
st.session_state.last_summary = state.summary(a)

{PAGES[0]: portfolio.render, PAGES[1]: scenario.render, PAGES[2]: delivery.render, PAGES[3]: brief.render}[page](v)
st.divider()
st.markdown(
    f'<footer class="product-footer"><span>{html.escape(PROJECT_TITLE)}</span>'
    '<span>Developed by Soham Shinde. '
    '<a href="mailto:sohamshindework@gmail.com" aria-label="Email Soham Shinde">'
    '<span class="contact-icon" aria-hidden="true">✉</span>sohamshindework@gmail.com</a></span></footer>',
    unsafe_allow_html=True,
)
