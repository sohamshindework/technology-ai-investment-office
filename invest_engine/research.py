"""Deterministic, citation-first research notes for authorized local documents.

The module intentionally does not call an LLM, fetch remote content, estimate
investment economics or modify a case configuration. Uploaded bytes are parsed
in memory and only structured proposal records are returned to the caller.
"""

from __future__ import annotations

import hashlib
import io
import re
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pypdf import PdfReader

MAX_DOCUMENT_BYTES = 5_000_000
MAX_PDF_PAGES = 200
MAX_EXTRACTED_CHARACTERS = 1_000_000
ALLOWED_SUFFIXES = {".md", ".pdf", ".txt"}


class ResearchError(ValueError):
    """Raised when a research document or review record is unsafe or invalid."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DocumentPage(StrictModel):
    number: int = Field(ge=1)
    text: str = Field(min_length=1)


class ResearchDocument(StrictModel):
    case_id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    title: str = Field(min_length=1)
    publication_date: date | None = None
    source_url: str | None = None
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pages: list[DocumentPage] = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("source_url")
    @classmethod
    def source_url_is_public_http(cls, value):
        if value is not None and not value.startswith(("https://", "http://")):
            raise ValueError("source_url must use http or https")
        return value


class EvidenceReference(StrictModel):
    document_title: str
    publication_date: date | None = None
    source_url: str | None = None
    page: int = Field(ge=1)
    location: str
    passage: str = Field(min_length=1, max_length=700)


class ResearchFinding(StrictModel):
    id: str = Field(pattern=r"^F[0-9]{2}$")
    claim: str = Field(min_length=1)
    theme: str = Field(min_length=1)
    evidence: EvidenceReference
    supported: Literal[True] = True


class DraftInitiative(StrictModel):
    id: str = Field(pattern=r"^P[0-9]{2}$")
    title: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    validation_questions: list[str] = Field(min_length=1)


class ResearchProposal(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    proposal_id: str = Field(pattern=r"^RP-[0-9a-f]{12}$")
    case_id: str
    mode: Literal["deterministic"] = "deterministic"
    document_title: str
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    findings: list[ResearchFinding]
    suggested_initiatives: list[DraftInitiative]
    missing_information: list[str]
    management_questions: list[str]
    warnings: list[str] = Field(default_factory=list)
    review_status: Literal["draft", "accepted_for_validation", "rejected"] = "draft"
    review_note: str | None = None
    approved_for_financial_model: Literal[False] = False

    @model_validator(mode="after")
    def references_are_internal_and_review_is_explicit(self):
        finding_ids = {item.id for item in self.findings}
        for item in self.suggested_initiatives:
            unknown = set(item.evidence_ids) - finding_ids
            if unknown:
                raise ValueError(f"proposal references unknown findings: {sorted(unknown)}")
        if self.review_status != "draft" and not self.review_note:
            raise ValueError("reviewed proposals require a review note")
        return self


INSTRUCTION_PATTERNS = (
    re.compile(r"\bignore (?:all |any )?(?:previous|prior|system|developer) instructions?\b", re.I),
    re.compile(r"\b(?:system|developer|assistant) (?:message|prompt)\b", re.I),
    re.compile(r"\b(?:reveal|print|send|upload|exfiltrate)\b.{0,50}\b(?:secret|credential|token|password|key)\b", re.I),
    re.compile(r"\bdo not follow\b.{0,40}\b(?:policy|instruction|rule)\b", re.I),
)

THEMES = {
    "automation and robotics": ("robot", "robotic", "automation", "automated", "autonomous"),
    "data and integration": ("data platform", "integration", "interoperab", "data layer", "data foundation"),
    "analytics and planning": ("analytics", "forecast", "planning", "scheduling", "digital twin"),
    "AI-enabled operations": ("artificial intelligence", "machine learning", " ai ", "copilot", "agentic"),
    "quality and risk": ("quality", "inspection", "fraud", "anomaly", "risk detection"),
    "maintenance and reliability": ("maintenance", "downtime", "reliability", "equipment availability"),
    "customer and service operations": ("customer service", "contact centre", "call center", "claims", "response time"),
    "governance and controls": ("governance", "human oversight", "audit trail", "compliance", "works council"),
}

PROPOSAL_TITLES = {
    "automation and robotics": "Assess automation expansion",
    "data and integration": "Assess the data and integration foundation",
    "analytics and planning": "Assess operational analytics and planning",
    "AI-enabled operations": "Assess a bounded AI-enabled workflow",
    "quality and risk": "Assess quality and risk-assistance workflows",
    "maintenance and reliability": "Assess maintenance and reliability support",
    "customer and service operations": "Assess customer and service workflow support",
    "governance and controls": "Assess governance and control readiness",
}

MISSING_INFORMATION = [
    "Current operating baseline, denominator and measurement owner",
    "Eligible deployment scope and existing capability coverage",
    "Implementation cost, internal effort and delivery capacity",
    "Incremental benefit logic, attribution method and overlap with other initiatives",
    "Technology, data, security and operational dependencies",
    "Pilot evidence, risk classification and required approvals",
]


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _contains_instruction(value: str) -> bool:
    return any(pattern.search(value) for pattern in INSTRUCTION_PATTERNS)


def _extract_text_pages(raw: bytes) -> list[DocumentPage]:
    if b"\x00" in raw:
        raise ResearchError("Text documents must not contain binary null bytes.")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ResearchError("Text and Markdown documents must use UTF-8 encoding.") from exc
    text = text.strip()
    if not text:
        raise ResearchError("The document contains no readable text.")
    return [DocumentPage(number=1, text=text)]


def _extract_pdf_pages(raw: bytes) -> list[DocumentPage]:
    if not raw.startswith(b"%PDF-"):
        raise ResearchError("The uploaded PDF does not have a valid PDF signature.")
    try:
        reader = PdfReader(io.BytesIO(raw), strict=True)
    except Exception as exc:  # pypdf exposes several parser-specific exception classes
        raise ResearchError("The PDF could not be parsed safely.") from exc
    if reader.is_encrypted:
        raise ResearchError("Encrypted PDFs are not supported.")
    if len(reader.pages) > MAX_PDF_PAGES:
        raise ResearchError(f"PDFs may contain at most {MAX_PDF_PAGES} pages.")
    pages = []
    for number, page in enumerate(reader.pages, start=1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception as exc:
            raise ResearchError(f"Text extraction failed on PDF page {number}.") from exc
        if text:
            pages.append(DocumentPage(number=number, text=text))
    if not pages:
        raise ResearchError("The PDF has no extractable text. Scanned PDFs require prior OCR.")
    return pages


def extract_document(
    *,
    case_id: str,
    filename: str,
    raw: bytes,
    title: str,
    publication_date: date | None = None,
    source_url: str | None = None,
    authorized: bool,
) -> ResearchDocument:
    """Validate and extract an authorized local document without persisting its bytes."""
    if not authorized:
        raise ResearchError("Confirm that the document is authorized for analysis.")
    if not raw:
        raise ResearchError("Choose a document to analyze.")
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ResearchError("Choose a document smaller than 5 MB.")
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name or "/" in filename or "\\" in filename:
        raise ResearchError("The document filename must not contain a local path.")
    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ResearchError("Supported document types are PDF, TXT and Markdown.")
    pages = _extract_pdf_pages(raw) if suffix == ".pdf" else _extract_text_pages(raw)
    if sum(len(page.text) for page in pages) > MAX_EXTRACTED_CHARACTERS:
        raise ResearchError("The extracted document text is too large to analyze safely.")
    warnings = []
    if any(_contains_instruction(page.text) for page in pages):
        warnings.append(
            "Instruction-like text was detected and treated only as untrusted document content; it was not followed."
        )
    return ResearchDocument(
        case_id=case_id,
        filename=safe_name,
        title=title,
        publication_date=publication_date,
        source_url=source_url or None,
        sha256=hashlib.sha256(raw).hexdigest(),
        pages=pages,
        warnings=warnings,
    )


def _sentences(page: DocumentPage):
    for raw in re.split(r"(?<=[.!?])\s+|[\r\n]+", page.text):
        passage = _normalise(raw)
        if 30 <= len(passage) <= 700:
            yield passage


def _theme(passage: str) -> str | None:
    lowered = f" {passage.lower()} "
    scores = {theme: sum(term in lowered for term in terms) for theme, terms in THEMES.items()}
    theme, score = max(scores.items(), key=lambda item: item[1])
    return theme if score else None


def _management_questions(theme: str) -> list[str]:
    return [
        f"Where is {theme} already deployed, and which operating units are genuinely eligible for incremental scope?",
        "What measured baseline and business owner would support an attributable benefit estimate?",
        "Which data, process, workforce, security and governance approvals are required before a pilot or rollout?",
    ]


def analyze_document(document: ResearchDocument, *, max_findings: int = 12) -> ResearchProposal:
    """Extract cited facts and draft validation topics without inventing economics."""
    findings = []
    for page in document.pages:
        for passage in _sentences(page):
            theme = _theme(passage)
            if theme is None or _contains_instruction(passage):
                continue
            findings.append(
                ResearchFinding(
                    id=f"F{len(findings) + 1:02}",
                    claim=passage,
                    theme=theme,
                    evidence=EvidenceReference(
                        document_title=document.title,
                        publication_date=document.publication_date,
                        source_url=document.source_url,
                        page=page.number,
                        location=f"Page {page.number}",
                        passage=passage,
                    ),
                )
            )
            if len(findings) >= max_findings:
                break
        if len(findings) >= max_findings:
            break
    by_theme: dict[str, list[ResearchFinding]] = {}
    for finding in findings:
        by_theme.setdefault(finding.theme, []).append(finding)
    initiatives = []
    for theme, evidence in list(by_theme.items())[:5]:
        initiatives.append(
            DraftInitiative(
                id=f"P{len(initiatives) + 1:02}",
                title=PROPOSAL_TITLES[theme],
                rationale=(
                    f"The document contains evidence relevant to {theme}. Validate the incremental operating gap, "
                    "existing coverage and measurable value before defining an investment candidate."
                ),
                evidence_ids=[item.id for item in evidence],
                validation_questions=_management_questions(theme),
            )
        )
    questions = []
    for initiative in initiatives:
        for question in initiative.validation_questions:
            if question not in questions:
                questions.append(question)
    if not findings:
        questions = [
            "Does this document contain sufficiently specific operational evidence for an investment discussion?",
            "Which approved source should be reviewed next to establish the existing capability and operating gap?",
        ]
    warnings = list(document.warnings)
    if not findings:
        warnings.append("No supported technology-investment finding was located in the supplied text.")
    identity = f"{document.case_id}:{document.sha256}:{'|'.join(item.claim for item in findings)}"
    return ResearchProposal(
        proposal_id=f"RP-{hashlib.sha256(identity.encode()).hexdigest()[:12]}",
        case_id=document.case_id,
        document_title=document.title,
        document_sha256=document.sha256,
        findings=findings,
        suggested_initiatives=initiatives,
        missing_information=deepcopy(MISSING_INFORMATION),
        management_questions=questions,
        warnings=warnings,
    )


def verify_finding(document: ResearchDocument, finding: ResearchFinding) -> bool:
    """Verify that the cited passage appears on the cited page of the same document."""
    if finding.evidence.document_title != document.title:
        return False
    page = next((page for page in document.pages if page.number == finding.evidence.page), None)
    return page is not None and _normalise(finding.evidence.passage) in _normalise(page.text)


def review_proposal(
    proposal: ResearchProposal, *, decision: Literal["accepted_for_validation", "rejected"], note: str
) -> ResearchProposal:
    """Record an explicit analyst decision without admitting an initiative to the financial model."""
    if not note.strip():
        raise ResearchError("Add a review note before recording the decision.")
    values = proposal.model_dump()
    values.update(review_status=decision, review_note=note.strip())
    return ResearchProposal.model_validate(values)


def evaluate_reference_set(path: str | Path) -> dict[str, float | int]:
    """Run the reviewed deterministic evaluation set and return transparent metrics."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    total_findings = 0
    supported_findings = 0
    expected_total = 0
    expected_found = 0
    injection_cases = 0
    injection_blocked = 0
    structured_valid = 0
    for item in raw["documents"]:
        document = extract_document(
            case_id=item["case_id"],
            filename=item["filename"],
            raw=item["text"].encode(),
            title=item["title"],
            publication_date=date.fromisoformat(item["publication_date"]),
            source_url=item.get("source_url"),
            authorized=True,
        )
        proposal = analyze_document(document)
        ResearchProposal.model_validate_json(proposal.model_dump_json())
        structured_valid += 1
        total_findings += len(proposal.findings)
        supported_findings += sum(verify_finding(document, finding) for finding in proposal.findings)
        passages = " ".join(finding.evidence.passage.lower() for finding in proposal.findings)
        for expected in item.get("expected_passages", []):
            expected_total += 1
            expected_found += expected.lower() in passages
        if item.get("contains_injection"):
            injection_cases += 1
            unsafe = any(_contains_instruction(finding.claim) for finding in proposal.findings)
            injection_blocked += not unsafe and bool(document.warnings)
        accepted = review_proposal(proposal, decision="accepted_for_validation", note="Reviewed reference record")
        rejected = review_proposal(proposal, decision="rejected", note="Rejected reference record")
        if accepted.review_status != "accepted_for_validation" or rejected.review_status != "rejected":
            raise AssertionError("review state evaluation failed")
    count = len(raw["documents"])
    return {
        "documents": count,
        "findings": total_findings,
        "citation_correctness": supported_findings / total_findings if total_findings else 1.0,
        "unsupported_claim_rate": 1 - supported_findings / total_findings if total_findings else 0.0,
        "extraction_completeness": expected_found / expected_total if expected_total else 1.0,
        "structured_output_validity": structured_valid / count if count else 1.0,
        "review_behavior": 1.0,
        "prompt_injection_block_rate": injection_blocked / injection_cases if injection_cases else 1.0,
    }
