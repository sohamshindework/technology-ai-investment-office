# Technology & AI Investment Strategy

**Portfolio Optimization · Financial Modeling · Scenario Planning**

Current development specification · 16 November 2026

## 1. Product and final scope

Support a strategy manager, investment analyst, delivery lead and investment committee in selecting technology/AI investments under capital, delivery, dependency, uncertainty and governance constraints. Recommendations must be inspectable and clearly distinguish calculated hypothetical outcomes from reported company facts and actual performance.

Exactly **three** industry case studies are in final scope:

1. **DHL Supply Chain — Logistics & Supply Chain**, flagship display title **DHL Supply Chain — Logistics & Automation**. This is exclusively the Supply Chain division, not a DHL Group-wide portfolio.
2. **Allianz — Insurance & Financial Services**. Implemented/admitted as an independent, explicitly hypothetical German P&C claims and customer-service case. Its [business validation](cases/allianz/business_validation.md) documents the decision boundary and limits.
3. **BMW Group — Automotive & Manufacturing**. Implemented/admitted as an independent, explicitly hypothetical German vehicle-production line-workflow case. [Business validation](cases/bmw_group/business_validation.md) records its decision boundary.

No additional industry cases. The existing synthetic case and blank template remain engineering support, not a fourth company/industry. Company reports may support divisional facts; no company is affiliated with or endorses the project. Do not present hypothetical allocations as corporate plans.

## 2. Branding and navigation

- Application / README / CV title: **Technology & AI Investment Strategy**.
- Subtitle: **Portfolio Optimization · Financial Modeling · Scenario Planning**.
- Portfolio dashboard heading: **Technology Investment Portfolio**.
- Dashboard description: **Evaluate opportunities. Allocate capital. Plan implementation.**

| Destination | Required working capabilities |
|---|---|
| **Portfolio** | Decision and selected scales, NPV/capital/uncertainty, ranked comparison, contribution analysis, candidate filtering, evidence, dependencies, assumptions and reviewed research notes |
| **Scenario Lab** | Explicit assumption application/reset; reference/previous comparisons, changed scales, feasibility, capital tradeoff, modeled uncertainty and existing stress tests |
| **Delivery Plan** | Rollout/capacity, dependencies, planned gates, governance questionnaire/human review/audit, benefits plan and validated observation import/tracking |
| **Decision Brief** | Executive rationale, benefits realization, alternatives, assumptions, risks, approval points, evidence, current Excel/PDF/Markdown/CSV/JSON/ZIP and local analysis records |

Retain the premium light editorial design, local Manrope/Inter, shared formatting and accessibility improvements. No new cosmetic redesign is required. Industry differences are restrained case metadata, KPIs, explanatory context and relevant shared chart choices, not copied interfaces. Business copy should describe the decision/action and keep material assumptions/limitations accessible.

## 3. Validated mathematical contract

Preserve the corrected quarterly-cohort model described in [rollout-correction.md](docs/rollout-correction.md):

- Integer cohort options are phased across available quarters within the rollout deadline. The solver chooses scales, not arbitrary deployment dates.
- Review lead time occurs before deployment once. Prerequisite coverage uses earlier-quarter completed deployments plus declared baseline coverage.
- Capex occurs at deployment completion; platform/compliance costs at programme start. Recurring operating costs/benefits begin in following quarters, with intrinsic time-to-value and midpoint ramp assumptions.
- Discount quarter-end cash flows at the case's annual rate. Annual financial tables sum quarterly vectors, including their already-discounted values.
- Enforce annual capital/carryover, annual and quarterly FTE, quarterly deployment capacity, dependency timing, commitments, exclusions, pilot gates and mutually exclusive alternatives.
- Select the sum of expected NPV minus the case's downside penalty times the **sum of initiative expected losses**; report portfolio risk separately. Integer objective precision is €1, not a claim of unrestricted/continuous optimality.
- The ranked list, roadmap, tracking plan, charts, reports and saved bundles must use the same analysis and schedule.

DHL numerical outputs are regression observations, not tuning targets. Preserve financial inputs unless an explicitly documented business/model correction is authorized. Do not recover the retired €156.20m annual-model result. An independent audit script now checks seeded cash flows and enumerates feasible scale combinations under the fixed policy; it must fail rather than claim optimality if its node limit is exceeded.

## 4. Reusable architecture

Use the current Python dataclass/YAML validation, NumPy/pandas, OR-Tools CP-SAT, Streamlit, Plotly and SQLite implementation. Pydantic validates the research proposal boundary and pypdf extracts authorized local PDFs. No domain-model migration, DuckDB migration or new UI framework is required.

- `invest_engine/`: common validation, governance rules, quarterly valuation/selection/roadmap, benefits, application service, reports and persistence. No company-specific financial calculation branches.
- `frontend/`: shared presentation/state/theme and four workflow pages; no valuation or optimization logic in chart functions.
- `cases/<case_id>/`: company scope, public evidence and explicitly hypothetical candidate economics.
- `research/`: a small reviewed reference set for deterministic citation and review evaluation.
- An explicit three-case catalog, strict `profile.yaml` / `evidence.yaml` admission and source/KPI/units validation support DHL, Allianz and BMW. See [case-configuration.md](docs/case-configuration.md).

The minimum profile records industry/scope, deployment-unit semantics, typed KPI definitions, versioned governance coverage, allowed chart choices, accents and reviewed decision notes. Economic assumptions and existing constraints remain common fields. KPI observations are not inferred from benefit money or corporate totals. Unknown units, constraints, rule profiles or metadata keys must fail validation/admission rather than silently falling back to DHL assumptions.

The current governance questionnaire is bounded and **not insurance-complete**. Unknown question keys now fail closed. Sector extensions, if needed, are reviewed registered rules returning generic eligibility/cost/lead-time outputs; they do not duplicate company-specific financial calculations. Do not admit unsupported underwriting/pricing/eligibility functions under a workplace-only questionnaire.

## 5. Implemented release scope

The development candidate contains the corrected quarterly model, the DHL Supply Chain flagship case, independent Allianz and BMW Group cases, the company-agnostic engine, the four-page frontend, current exports, local snapshots and review records, validated benefits-realization tracking, and a deterministic investment research workflow.

Each admitted case has:

- a bounded operating scope and deployment unit;
- a public evidence register separated from hypothetical economics;
- approximately 8–12 investment candidates;
- explicit capital, staffing, launch, dependency and approval constraints;
- industry-specific KPI definitions and governance context;
- the same independent valuation, feasibility and export checks; and
- desktop and mobile presentation through the shared interface.

The current [validation record](docs/validation.md) contains the numerical and regression results. A working hypothetical application is not a real investment approval or authenticated compliance system.

The Portfolio research panel accepts an authorized PDF, TXT or Markdown document, extracts cited facts and themes, records missing information and management questions, and requires explicit accept/reject review. Research acceptance is never financial-model admission. It does not create costs, benefits, rollout assumptions or company plans. Uploaded bytes are not persisted or exported.

## 6. Out of scope unless separately authorized

No further industries, live research retrieval, paid/model-assisted research, authentication/multitenancy/hosting, unbounded model extensions, actual company-internal datasets, new corporate approvals or fabricated sources/evaluation metrics. Excel and PDF outputs are presentation documents, not separate editable calculation engines. No framework/package/repository rename. Do not modify the original source folder or unrelated projects.

## 7. Tests and integrity gates

Run `python -m pytest -q`, `python -m ruff check .`, all three `scripts/validate_case.py` audits and `python scripts/evaluate_research.py`. Use fixed seeds; explicitly review any numerical drift. Independent analytical/cash-flow references and feasible enumeration must accompany genuine model changes. Configuration validation must not truncate commitments or ignore unsupported governance answers. Preserve all working features and existing tests; adapt assertions only when their UI contract legitimately changes.

All evidence must be source-addressable; opinions, assumptions, simulations and user reports remain distinct. Planned gates do not prove legal approval. Current financial distributions, expected-cost constraints, fixed phasing, missing benefit-overlap adjustment and lack of site-level mapping must remain visible where material. Never hardcode computed recommendations in the UI or exports.
