"""Governance questionnaire and local review audit trail, preserved from the existing app."""

import pandas as pd
import streamlit as st

from frontend.components import ROOT, analysis_key
from invest_engine.ai_act import LEGAL_SOURCES, QUESTIONS
from invest_engine.reporting import safe_csv
from invest_engine.store import Store


def render(v):
    a, c, names = v.analysis, v.c, v.names
    state_key = analysis_key(a)
    st.subheader("Governance review")
    st.write("Review the intended use and applicable controls for each investment.")
    st.caption(
        "This preliminary screening covers selected EU AI Act triggers. It does not replace sector, privacy or legal review; product-route classification requires both Art. 6(1) conditions."
    )
    if c.profile and c.profile.industry_id == "insurance":
        st.warning("Insurance review remains open for claims fairness, human decision authority, privacy, model risk and ICT resilience.")
        with st.expander("Insurance approval checkpoints"):
            for item in c.profile.governance["approval_points"]:
                st.write(f"- {item}")
    if c.profile and c.profile.industry_id == "automotive":
        st.warning("Manufacturing review remains open for machine safety, quality, workforce safeguards and industrial cybersecurity.")
        with st.expander("Manufacturing approval checkpoints"):
            for item in c.profile.governance["approval_points"]:
                st.write(f"- {item}")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Initiative": names[i],
                    "Screening": s.category,
                    "Excluded": s.excluded,
                    "Unknown answers": len(s.unknown_questions),
                    "Compliance (€k)": s.compliance_capex,
                    "Delay (months)": s.delay_months,
                    "Review": s.review_status,
                }
                for i, s in a.screenings.items()
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    iid = st.selectbox("Initiative to review", list(names), format_func=names.get, key="review_initiative")
    current = c.get(iid).ai_act
    with st.form("questionnaire"):
        answers = {
            k: st.selectbox(
                q,
                [None, False, True],
                index=[None, False, True].index(current.get(k)),
                format_func=lambda v: "Unknown" if v is None else "Yes" if v else "No",
                key=f"question_{iid}_{k}",
            )
            for k, q in QUESTIONS.items()
        }
        if st.form_submit_button("Apply design assumptions and recalculate"):
            st.session_state.previous_scenario = st.session_state.last_summary
            st.session_state.overrides[iid] = answers
            st.rerun()
    s = a.screenings[iid]
    st.markdown(f"**Initial classification:** {s.category}")
    for reason in s.rationale:
        st.write(reason)
    st.dataframe(
        pd.DataFrame(
            [
                {"Obligation": o.text, "Provision": o.reference, "Applies from": o.applies_from}
                for o in s.obligations + s.flags
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    with st.expander("Record human review"):
        st.caption(
            "Reviews are saved locally with the current assumptions. A recorded review is not a legal determination or deployment authorization; reviewer identity is self-reported."
        )
        with st.form("review"):
            reviewer = st.text_input("Reviewer name", key="review_name")
            evidence = st.text_area(
                "Evidence and reasoning",
                key="review_evidence",
                help="Include the intended purpose, design evidence, provision and source references.",
            )
            uncertainty = st.text_area("Remaining uncertainty and follow-up", key="review_uncertainty")
            decision = st.selectbox(
                "Review decision", ["request changes", "approve assumptions", "reject"], key="review_decision"
            )
            submitted = st.form_submit_button("Save review record")
        store = Store(ROOT / "data/office.sqlite3")
        if submitted:
            try:
                if not reviewer.strip() or not evidence.strip() or not uncertainty.strip():
                    raise ValueError("Reviewer, evidence and uncertainty are required.")
                if decision == "approve assumptions" and (s.unknown_questions or s.excluded):
                    raise ValueError("Incomplete or excluded screening cannot be approved.")
                run_id = st.session_state.get("review_runs", {}).get(state_key)
                if not run_id:
                    run_id = store.save(a)
                    st.session_state.setdefault("review_runs", {})[state_key] = run_id
                store.review(run_id, iid, reviewer, evidence, decision, uncertainty)
                st.success("Review saved with the current investment assumptions.")
            except ValueError as exc:
                st.error(str(exc))
        run_id = st.session_state.get("review_runs", {}).get(state_key)
        if run_id:
            records = pd.DataFrame(store.reviews(run_id))
            st.dataframe(records, hide_index=True, width="stretch")
            st.download_button("Download review audit trail", safe_csv(records), "review_audit.csv", "text/csv")
    with st.expander("Legal references · checked 14 November 2026"):
        for label, url in LEGAL_SOURCES.items():
            st.markdown(f"[{label}]({url})")
        st.caption(
            "Article 50(2) generally applies from 2 August 2026. The 2 December 2026 transition is limited to qualifying systems marketed before 2 August 2026. Confirm applicability and later amendments with counsel."
        )
