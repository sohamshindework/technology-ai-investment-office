"""Session-isolated, deterministic investment research workflow."""

from __future__ import annotations

from datetime import date

import streamlit as st

from invest_engine.research import (
    ResearchError,
    ResearchProposal,
    analyze_document,
    extract_document,
    review_proposal,
)


def _source_label(case, source_id):
    return "Authorized local document" if source_id == "upload" else f"{source_id} · {case.sources[source_id]['title']}"


def _proposal():
    raw = st.session_state.get("research_proposal_json")
    return ResearchProposal.model_validate_json(raw) if raw else None


def _analyze(case, upload, source_id, title, publication_date, source_url, authorized):
    st.session_state.pop("research_review_message", None)
    try:
        if upload is None:
            raise ResearchError("Choose an authorized PDF, TXT or Markdown document.")
        document = extract_document(
            case_id=case.id,
            filename=upload.name,
            raw=upload.getvalue(),
            title=title,
            publication_date=publication_date,
            source_url=source_url,
            authorized=authorized,
        )
        proposal = analyze_document(document)
        st.session_state.research_proposal_json = proposal.model_dump_json()
        st.session_state.research_document_summary = {
            "filename": document.filename,
            "sha256": document.sha256,
            "pages": len(document.pages),
            "source_id": None if source_id == "upload" else source_id,
        }
        st.session_state.research_error = None
    except (ResearchError, ValueError) as exc:
        st.session_state.research_error = str(exc)


def _record_review(decision, note):
    try:
        proposal = _proposal()
        if proposal is None:
            raise ResearchError("Analyze a document before recording a review.")
        reviewed = review_proposal(proposal, decision=decision, note=note)
        st.session_state.research_proposal_json = reviewed.model_dump_json()
        st.session_state.research_error = None
        st.session_state.research_review_message = (
            "Accepted as a research note for management validation. It has not been added to the financial model."
            if decision == "accepted_for_validation"
            else "Rejected research proposal recorded. It has not been added to the financial model."
        )
    except (ResearchError, ValueError) as exc:
        st.session_state.research_error = str(exc)


def render(v):
    case = v.c
    st.markdown("#### Investment research assistant")
    st.write(
        "Review an authorized report, extract source-linked facts and prepare questions for management validation. "
        "This deterministic workflow does not call a paid model or create financial assumptions."
    )
    source_ids = ["upload", *case.sources]
    source_id = st.selectbox(
        "Source context",
        source_ids,
        format_func=lambda value: _source_label(case, value),
        key=f"research_source_{case.id}",
        help="An approved source supplies its registered title and URL. You must still upload an authorized local copy.",
    )
    source = case.sources.get(source_id, {})
    if source:
        title = source["title"]
        source_url = source["url"]
        st.text_input("Document title", title, disabled=True)
        st.text_input("Source URL", source_url, disabled=True)
    else:
        title = st.text_input("Document title", key=f"research_title_{case.id}")
        source_url = st.text_input("Source URL · optional", key=f"research_url_{case.id}")
    publication_date = st.date_input(
        "Publication date · optional",
        value=None,
        max_value=date.today(),
        key=f"research_date_{case.id}",
    )
    upload = st.file_uploader(
        "Authorized report · PDF, TXT or Markdown",
        type=["pdf", "txt", "md"],
        key=f"research_upload_{case.id}",
        help="Maximum 5 MB and 200 PDF pages. Files are processed in the current application session and are not saved by the application.",
    )
    authorized = st.checkbox(
        "I confirm that this document is authorized for analysis.", key=f"research_authorized_{case.id}"
    )
    st.button(
        "Analyze document",
        type="primary",
        on_click=_analyze,
        args=(case, upload, source_id, title, publication_date, source_url, authorized),
        disabled=upload is None or not title.strip(),
    )
    if st.session_state.get("research_error"):
        st.error(f"The research document could not be analyzed: {st.session_state.research_error}")
    proposal = _proposal()
    if proposal is None or proposal.case_id != case.id:
        st.info("No research proposal is active for this case. Uploaded documents never alter the recommended portfolio.")
        return
    for warning in proposal.warnings:
        st.warning(warning)
    summary = st.session_state.get("research_document_summary", {})
    st.caption(
        f"Proposal {proposal.proposal_id} · {summary.get('pages', 0)} extracted page(s) · "
        f"document fingerprint {proposal.document_sha256[:12]}…"
    )
    st.markdown("**Supported findings**")
    if not proposal.findings:
        st.info("No supported technology-investment finding was located. Try a more relevant approved source.")
    for finding in proposal.findings:
        st.write(f"**{finding.id} · {finding.theme}** — {finding.claim}")
        citation = f"{finding.evidence.document_title} · {finding.evidence.location}"
        if finding.evidence.publication_date:
            citation += f" · {finding.evidence.publication_date.isoformat()}"
        if finding.evidence.source_url:
            citation = f"[{citation}]({finding.evidence.source_url})"
        st.caption(citation)
        st.caption(f'Supporting passage: “{finding.evidence.passage}”')
    if proposal.suggested_initiatives:
        st.markdown("**Draft validation topics**")
        for item in proposal.suggested_initiatives:
            st.write(f"**{item.title}**")
            st.write(item.rationale)
            st.caption(f"Evidence: {', '.join(item.evidence_ids)}")
    st.markdown("**Missing business information**")
    for item in proposal.missing_information:
        st.write(f"- {item}")
    st.markdown("**Questions for management validation**")
    for item in proposal.management_questions:
        st.write(f"- {item}")
    st.divider()
    st.markdown("**Analyst review**")
    decision_label = st.radio(
        "Decision",
        ["Accept for management validation", "Reject proposal"],
        horizontal=True,
        key=f"research_decision_{case.id}",
    )
    decision = "accepted_for_validation" if decision_label.startswith("Accept") else "rejected"
    note = st.text_area(
        "Review note",
        key=f"research_review_note_{case.id}",
        help="Record why the evidence is sufficient for further validation or why the draft is rejected.",
    )
    st.button("Record research review", on_click=_record_review, args=(decision, note))
    if st.session_state.get("research_review_message"):
        st.success(st.session_state.research_review_message)
    st.caption(
        "Research acceptance does not approve funding or add an initiative to optimization. Costs, benefits and rollout assumptions require a separate reviewed case change."
    )
    st.download_button(
        "Download research proposal · JSON",
        proposal.model_dump_json(indent=2),
        file_name=f"{case.id}-{proposal.proposal_id.lower()}.json",
        mime="application/json",
    )
