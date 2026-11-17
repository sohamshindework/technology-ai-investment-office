# Investment research assistant

The Portfolio page contains a controlled research workflow for authorized company publications. It supports the existing investment process; it is not a chatbot and does not change the financial recommendation.

## Workflow

1. Select an approved case source as context or provide source metadata.
2. Upload an authorized PDF, TXT or Markdown file no larger than 5 MB. PDFs are limited to 200 pages and must contain extractable text.
3. Review source-linked factual passages, technology themes, draft validation topics, missing information and management questions.
4. Accept the draft for management validation or reject it. A review note is required.
5. Download the structured JSON record if needed. Acceptance never adds an initiative to optimization.

Each finding contains the document title, publication date and URL when supplied, PDF page or text location, and exact supporting passage. A finding is emitted only when its cited passage appears in the extracted document. Suggested initiatives are explicitly validation topics and contain no generated cost, benefit, NPV or rollout assumption.

## Privacy and security

Uploaded bytes are processed in memory, are not written to disk or SQLite, and are not included in committee reports. Structured research state is cleared when the company changes. The parser rejects oversized files, unsupported types, local-path filenames, binary text, malformed or encrypted PDFs and documents without extractable text. Instruction-like document content is flagged and excluded from findings.

This is a local single-user Streamlit architecture, not authenticated multi-user isolation. A public deployment would require tested session controls, retention policy and infrastructure protections before accepting confidential documents.

## Evaluation

`research/reference_set.yaml` contains three reviewed synthetic excerpts covering logistics, insurance and manufacturing, including an adversarial instruction. `scripts/evaluate_research.py` reports citation correctness, unsupported-claim rate, extraction completeness, structured-output validity, review behavior and prompt-injection block rate. These metrics evaluate only the committed fixtures and must not be presented as general research accuracy.

## Boundaries

The deterministic method uses passage segmentation and reviewed theme keywords. It does not use OCR, semantic retrieval, a language model or live web access. It may miss relevant passages, especially in tables, images, unfamiliar terminology or languages other than English. Analysts remain responsible for source rights, factual interpretation, completeness, commercial reasoning and approval.
