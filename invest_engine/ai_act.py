"""EU AI Act screening questionnaire (screening aid, not a legal determination).

Dates reflect Regulation (EU) 2024/1689 as amended by the Digital Omnibus on AI,
Regulation (EU) 2026/1744 (in force 27 July 2026):
  - Art. 5 prohibitions apply since 2 Feb 2025
  - Art. 50 applies from 2 Aug 2026; 2 Dec 2026 is a legacy-system transition
  - Annex III (stand-alone) high-risk obligations apply from 2 Dec 2027
  - Annex I (product-embedded) high-risk obligations apply from 2 Aug 2028
German co-determination (BetrVG s. 87(1) no. 6) and GDPR flags are added because
they gate workplace technology in Germany regardless of the AI Act category.
"""

from __future__ import annotations

from dataclasses import dataclass, field

DISCLAIMER = (
    "Preliminary regulatory screening only. Not a legal compliance determination. Screening aid only. It structures questions and points to the relevant provisions; "
    "it is not a legal determination. Classification depends on the system's intended "
    "purpose and design, and must be confirmed by legal/compliance review."
)

# Question key -> (question text shown to the user)
QUESTIONS: dict[str, str] = {
    "uses_ai": "Does the solution use an AI system (machine-learning or logic/knowledge-based inference)?",
    "emotion_recognition_workplace": "Does it infer emotions of people at the workplace (e.g., from face, voice)?",
    "biometric_categorisation_sensitive": "Does it categorise people by biometric data to infer sensitive traits?",
    "recruitment_selection": "Is it used to recruit, filter applications or evaluate candidates?",
    "allocates_tasks_individual_behaviour": "Does it allocate tasks to individual workers based on their behaviour, traits or characteristics?",
    "monitors_evaluates_workers": "Does it monitor or evaluate the performance or behaviour of individual workers?",
    "decisions_on_work_terms": "Does it make or inform decisions on promotion, termination or terms of work?",
    "safety_component_regulated_product": "Is the AI a safety component of a product under EU product law (e.g., machinery/robots)?",
    "interacts_with_people": "Does it interact directly with people (e.g., chatbot/voice agent)?",
    "generates_synthetic_content": "Does it generate synthetic text, audio, image or video for others?",
    "uses_gpai_model": "Is it built on a general-purpose AI model (e.g., an LLM)?",
    "capable_of_monitoring_employees": "Could it technically be used to monitor employee behaviour or performance (even if not intended)?",
    "processes_personal_data": "Does it process personal data?",
}

PROHIBITED_FROM = "2025-02-02"
TRANSPARENCY_FROM = "2026-08-02"
SYNTHETIC_FROM = "2026-08-02"
SYNTHETIC_LEGACY_TRANSITION = "2026-12-02"
LEGAL_SOURCES = {
    "AI Act": "https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng",
    "Amendment": "https://eur-lex.europa.eu/eli/reg/2026/1744/oj/eng",
    "Timeline": "https://ai-act-service-desk.ec.europa.eu/en/ai-act/timeline/timeline-implementation-eu-ai-act",
    "German co-determination": "https://www.gesetze-im-internet.de/betrvg/__87.html",
    "GDPR": "https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng",
}
ANNEX_III_FROM = "2027-12-02"
ANNEX_I_FROM = "2028-08-02"
GPAI_FROM = "2025-08-02"


@dataclass
class Obligation:
    text: str
    reference: str
    applies_from: str = ""


@dataclass
class Screening:
    category: (
        str  # prohibited | high-risk (Annex III) | high-risk (Annex I, via product) | transparency | minimal | not AI
    )
    obligations: list[Obligation] = field(default_factory=list)
    flags: list[Obligation] = field(default_factory=list)
    rationale: list[str] = field(default_factory=list)
    excluded: bool = False
    compliance_capex: float = 0.0  # EUR k, one-off adder
    delay_months: float = 0.0  # added before value starts
    go_live_gate: bool = False  # requires a pre-go-live gate in the roadmap

    unknown_questions: list[str] = field(default_factory=list)
    review_status: str = "pending human review"

    @property
    def summary(self) -> str:
        return self.category


def screen(answers: dict[str, bool], compliance_cfg: dict | None = None) -> Screening:
    """Preliminary flags, with incomplete information excluded from funding.

    A complete questionnaire is a modelling assumption, not legal approval.
    This bounded questionnaire is not an exhaustive catalogue of Art. 5/Annex III.
    """
    cfg = compliance_cfg or {}
    unsupported = set(answers) - set(QUESTIONS)
    if unsupported:
        raise ValueError("unsupported governance questions: " + ", ".join(sorted(map(str, unsupported))))
    if any(v is not None and type(v) is not bool for v in answers.values()):
        raise ValueError("governance answers must be booleans or null")
    unknown = [k for k in QUESTIONS if answers.get(k) is None]
    a = {k: answers.get(k) is True for k in QUESTIONS}

    def complete(s):
        s.unknown_questions = unknown
        if unknown:
            s.excluded = True
            s.go_live_gate = True
            s.rationale.append("Incomplete questionnaire: funding blocked until missing information is supplied.")
        return s

    if answers.get("uses_ai") is None:
        s = Screening(category="unknown", excluded=True)
        s.rationale.append("Whether this is an AI system is unknown; human assessment required.")
        _add_german_flags(a, s, cfg)
        return complete(s)
    if not a["uses_ai"]:
        s = Screening(category="not AI")
        s.rationale.append("No AI system involved; AI Act not triggered.")
        _add_german_flags(a, s, cfg)
        return complete(s)

    # 1. Prohibited practices (Art. 5)
    if a["emotion_recognition_workplace"] or a["biometric_categorisation_sensitive"]:
        s = Screening(category="prohibited", excluded=True)
        if a["emotion_recognition_workplace"]:
            s.obligations.append(
                Obligation(
                    "Emotion recognition in the workplace is prohibited (narrow medical/safety exception).",
                    "AI Act Art. 5(1)(f)",
                    PROHIBITED_FROM,
                )
            )
        if a["biometric_categorisation_sensitive"]:
            s.obligations.append(
                Obligation(
                    "Biometric categorisation to infer sensitive characteristics is prohibited.",
                    "AI Act Art. 5(1)(g)",
                    PROHIBITED_FROM,
                )
            )
        s.rationale.append("Excluded from the portfolio unless redesigned.")
        return complete(s)

    s = Screening(category="minimal")

    # 2. High-risk, Annex III point 4 (employment and workers' management)
    annex3 = []
    if a["recruitment_selection"]:
        annex3.append("Annex III 4(a): recruitment and selection")
    if a["allocates_tasks_individual_behaviour"]:
        annex3.append("Annex III 4(b): task allocation based on individual behaviour/traits")
    if a["monitors_evaluates_workers"]:
        annex3.append("Annex III 4(b): monitoring/evaluating worker performance or behaviour")
    if a["decisions_on_work_terms"]:
        annex3.append("Annex III 4(b): decisions affecting terms of work relationships")
    if annex3:
        s.category = "high-risk (Annex III)"
        s.rationale.extend(annex3)
        s.rationale.append(
            "Check whether the Art. 6(3) exception applies (narrow procedural or preparatory task "
            "without materially influencing decisions); profiling of natural persons is always high-risk."
        )
        s.obligations.extend(
            [
                Obligation(
                    "Deployer: use per instructions, assign competent human oversight, monitor operation, keep logs.",
                    "AI Act Art. 26(1)-(6)",
                    ANNEX_III_FROM,
                ),
                Obligation(
                    "Employer-deployer: inform workers' representatives and affected workers before use at the workplace.",
                    "AI Act Art. 26(7)",
                    ANNEX_III_FROM,
                ),
                Obligation(
                    "Provider (vendor or in-house builder): risk management, data governance, technical documentation, "
                    "conformity assessment, registration.",
                    "AI Act Art. 9-17, 43, 49",
                    ANNEX_III_FROM,
                ),
            ]
        )
        s.compliance_capex = float(cfg.get("high_risk_capex", 400))
        s.delay_months = float(cfg.get("high_risk_delay_months", 6))
        s.go_live_gate = True

    # 3. High-risk via product legislation (Annex I), e.g. machinery safety components
    if a["safety_component_regulated_product"]:
        if s.category == "minimal":
            s.category = "high-risk (Annex I, via product)"
        s.rationale.append(
            "Potential product-route high risk: confirm Annex I coverage AND third-party conformity requirement under Art. 6(1)."
        )
        s.obligations.append(
            Obligation(
                "Mainly a provider (vendor) obligation via product conformity; as deployer, require vendor CE/conformity "
                "evidence and follow instructions for use.",
                "AI Act Art. 6(1), Annex I; Art. 26",
                ANNEX_I_FROM,
            )
        )
        s.compliance_capex = max(s.compliance_capex, float(cfg.get("product_route_capex", 100)))
        s.go_live_gate = True

    # 4. Transparency (Art. 50)
    if a["interacts_with_people"]:
        if s.category == "minimal":
            s.category = "transparency"
        s.obligations.append(
            Obligation(
                "People must be informed they are interacting with an AI system (unless obvious).",
                "AI Act Art. 50(1)",
                TRANSPARENCY_FROM,
            )
        )
        s.compliance_capex += float(cfg.get("transparency_capex", 30))
    if a["generates_synthetic_content"]:
        if s.category == "minimal":
            s.category = "transparency"
        s.obligations.append(
            Obligation(
                "Provider marking of synthetic content; legacy systems marketed before 2 Aug 2026 have a "
                "2 Dec 2026 transition. Deployer disclosure for deepfakes/public-interest text needs Art. 50(4) review.",
                "AI Act Art. 50(2), 50(4); amended Art. 111",
                SYNTHETIC_FROM,
            )
        )

    # 5. GPAI
    if a["uses_gpai_model"]:
        s.obligations.append(
            Obligation(
                "GPAI model obligations sit with the model provider; as downstream user, obtain the provider's "
                "documentation and check usage terms.",
                "AI Act Art. 53-55",
                GPAI_FROM,
            )
        )

    # 6. AI literacy applies to all providers/deployers
    s.obligations.append(
        Obligation("Ensure sufficient AI literacy of staff operating the system.", "AI Act Art. 4", PROHIBITED_FROM)
    )

    if s.category == "minimal":
        s.rationale.append("No prohibited, high-risk or transparency trigger answered 'yes'.")

    _add_german_flags(a, s, cfg)
    return complete(s)


def _add_german_flags(a: dict[str, bool], s: Screening, cfg: dict) -> None:
    if a["capable_of_monitoring_employees"] or a["monitors_evaluates_workers"]:
        s.flags.append(
            Obligation(
                "Works council co-determination is likely required for technical systems capable of monitoring "
                "employee behaviour or performance (German sites).",
                "BetrVG s. 87(1) no. 6",
            )
        )
        s.delay_months = max(s.delay_months, float(cfg.get("works_council_delay_months", 3)))
        s.go_live_gate = True
    if a["processes_personal_data"]:
        s.flags.append(
            Obligation(
                "Check lawful basis and whether a data protection impact assessment is required.",
                "GDPR Art. 6, 35; BDSG s. 26",
            )
        )
