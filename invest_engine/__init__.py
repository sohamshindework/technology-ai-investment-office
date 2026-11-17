"""Technology & AI Investment Strategy: a company-agnostic engine for prioritising
technology and AI initiatives under budget, capacity, dependency and EU AI Act constraints."""

from .ai_act import DISCLAIMER as AI_ACT_DISCLAIMER
from .ai_act import screen
from .benefits import latest_status, track
from .documents import excel_analysis, investment_committee_pdf
from .finance import value_case, value_initiative
from .portfolio import frontier, greedy, optimise
from .research import ResearchDocument, ResearchProposal, analyze_document, extract_document, review_proposal
from .roadmap import build_roadmap
from .schema import Case, CaseError, Initiative, load_case

__all__ = [
    "AI_ACT_DISCLAIMER",
    "Case",
    "CaseError",
    "Initiative",
    "build_roadmap",
    "frontier",
    "greedy",
    "latest_status",
    "load_case",
    "optimise",
    "ResearchDocument",
    "ResearchProposal",
    "analyze_document",
    "extract_document",
    "review_proposal",
    "screen",
    "track",
    "excel_analysis",
    "investment_committee_pdf",
    "value_case",
    "value_initiative",
]
__version__ = "0.2.0"
