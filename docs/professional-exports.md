# Professional exports

The Decision Brief creates two management-ready documents from the active `Analysis`. Both reflect the selected company, applied scenario, optimized portfolio and fixed quarterly implementation plan visible in the application. They do not read static examples or recalculate investment economics.

## Excel analysis

The `.xlsx` workbook contains eight print-formatted sheets:

1. Executive Summary
2. Portfolio
3. Financials
4. Delivery Plan
5. Scenarios
6. Governance
7. Assumptions
8. Sources & Method

Illustrative assumptions use a distinct input treatment; calculated outputs use separate result styling. The financial sheet displays engine-to-schedule reconciliation for NPV, capital and benefits. The workbook intentionally contains values rather than a duplicate editable formula model, so changing a cell does not rerun optimization.

## Investment committee PDF

The PDF is a concise five-page report covering the executive decision, recommended initiatives, annual financial outlook, constraints, quarterly implementation plan, scenario sensitivity, principal risks, governance, methodology, limitations and public sources. Every page identifies the case as an illustrative model-based scenario rather than an official company forecast.

## Security and reproducibility

XlsxWriter and ReportLab generate both files in memory. No temporary file or shared export directory is used. The export boundary rejects analyses that retain a local case path, limits the number of initiatives and quarters, and caps output size. Uploaded research documents, extracted proposals, credentials and local paths are excluded. Fixed document metadata and stable ordering make repeated downloads byte-identical for an unchanged analysis.

When observations are active, Delivery Plan includes portfolio and initiative-level realization summaries plus observation detail, sources, confidence, missing periods and material follow-up. The five-page PDF adds a concise realization table before the source register. With no observations, both formats state that results are unavailable rather than substituting demonstration values.

The regression suite opens every workbook with openpyxl, extracts every PDF page with pypdf, reconciles current values for all three cases, exercises one modified scenario per company and an empty portfolio, checks deterministic repeated downloads and verifies cross-case isolation. Benefits tests additionally reconcile imported observations, variances and missing periods. Visual validation renders every PDF page and every changed workbook print section.
