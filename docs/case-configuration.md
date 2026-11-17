# Reusable case configuration — three admitted cases

Technology & AI Investment Strategy · 14 November 2026

The configuration contract has a strict catalog/profile/evidence implementation for **DHL Supply Chain, Allianz and BMW Group**. The synthetic case and blank template remain engineering support, not additional industries. The economic engine and four pages remain shared. Metadata approval checkpoints are not an automated legal determination.

## Minimum boundary

Keep one `Case` → `analyse()` → `Analysis` pipeline. Retain `finance.py`, `deployment.py`, `portfolio.py`, `roadmap.py`, `benefits.py`, the four workflow pages and current public imports. Company IDs must not select different financial equations. Prepare data and reviewed eligibility before analysis; select formatting/labels after analysis. Do not copy pages or calculators per company.

```text
cases/
  catalog.yaml                 # implemented: explicit three-case admission/status registry
  <case_id>/
    case.yaml                  # existing economic, capacity, source and scope data
    initiatives.yaml           # existing rollout options, distributions, dependencies, answers
    profile.yaml               # typed scope/KPI/review metadata
    evidence.yaml              # claim/assumption provenance
    memo.md                    # derived current report, never a valuation input
```

`invest_engine/case_config.py` loads and validates the catalog, profile and evidence. It rejects unsupported economic/profile fields, unknown units and chart IDs, missing scope, unresolved source/initiative references and incompatible governance profiles before admission. All three business cases use the same calculation path. Profile/evidence bytes enter the analysis cache and review fingerprint. Unprofiled synthetic fixtures remain available for engineering tests.

The catalog has exactly three business IDs, each with `folder`, `industry_id` and admission state `planned | validating | implemented`. The UI lists only admitted/implemented cases after validation. “Implemented” means the hypothetical application works; it does not mean the investment has business/legal approval. A separate business-review state remains `pending | reviewed`. Synthetic/test cases stay outside that business catalog and remain available to tests/local validation.

## Typed profile contract (version 1, implemented subset)

| Field | Representation / validation |
|---|---|
| `schema_version` | Integer 1, reject booleans, unsupported versions and unknown keys |
| `case_id`, `industry_id` | Nonempty IDs; case ID must match `case.yaml`; industry one of logistics, insurance, automotive |
| `scope` | Named company, operating unit, geography, process boundary, economic beneficiary and exclusions; never imply an undocumented group-wide allocation |
| `as_of` | ISO evidence/assumption review date; relative quarter numbers remain the scheduling convention |
| `deployment_unit` | Singular/plural business labels, compatible coverage noun and unit definition; not a count of unique physical sites unless supported by the data |
| `accent` | Validated primary/supporting hex colors; neutral canvas, typography, spacing and navigation stay shared |
| `kpis` | Typed records linked to existing initiative IDs; see below |
| `governance` | Versioned coverage profile, review domains, applicability evidence and readiness; no executable rule expressions |
| `views` | Page-specific IDs of available shared charts and KPI summaries; unsupported IDs rejected; the function-value chart and insurance/manufacturing measure definitions are selected from this registry |
| `decision_notes` | Reviewed strategic rationale, exclusions, approval points and source references; not hardcoded numerical recommendations |

Illustrative **shape**, not a populated company case:

```yaml
schema_version: 1
case_id: <matching_case_id>
industry_id: <logistics_or_insurance_or_automotive>
deployment_unit:
  singular: <business_unit_label>
  plural: <business_unit_labels>
  definition: <what_one_increment_and_one_launch_slot_mean>
governance:
  profile_id: <registered_reviewed_profile>
  profile_version: 1
  coverage_review: design_reviewed
views:
  portfolio: [contribution, baseline_waterfall]
  scenarios: [capital_frontier, npv_distribution, scenario_delta]
  delivery: [quarterly_rollout, quarterly_capacity, planned_benefits]
```

No `eval`, embedded Python, free-form formulas, arbitrary chart code or company-specific methods belong in these files. A small dataclass/standard-library validator can follow the existing project style; adding Pydantic is not a prerequisite.

## KPIs and monetization

A KPI record requires `id`, `initiative_ids`, `label`, `unit`, `direction` (`higher | lower | target_range`), `frequency`, `aggregation`, `provenance`, `source_ids`, and a measurement owner or an explicit unknown owner. Optional baseline/target values are `null` when unavailable, never invented or converted to zero. Percentages have a declared 0–1 or 0–100 convention; ratios declare numerator/denominator, and weighted averages require weights. Do not sum percentages or average ratios without their bases.

`provenance` distinguishes `reported_fact | hypothetical_assumption | simulated | user_reported`. Public corporate KPIs, modeled financial benefits and uploaded operational measurements are separate datasets. Existing benefits CSV reports **money**, not observed pick rates, claim times or OEE; retaining a KPI's name does not implement numeric KPI tracking.

Financial assumptions remain the current `Tri(low, mode, high)` distributions for capex, recurring annual opex, gross annual benefit at full run rate, platform capex and months to value; plus success/underdelivery, ramp, staffing and common volume factor. Keep EUR k input/output precision with presentation-only €m conversion. Record price basis, horizon, discount-rate basis, assumed useful life, owner and rationale. The model does not infer benefits from a KPI name or public revenue.

Document the benefit pool, cost boundary, retained-value assumption and overlap with other initiatives. A reviewed calculation worksheet may justify each annual cash input, but the runtime engine receives the same generic monetary fields. Do not multiply an observed KPI by invented volumes/wages inside a chart or UI component. Until overlap/capture assumptions are agreed, flag the recommendation as conditional; do not invent discounts merely to make it look prudent.

## Industry expression without duplicate calculations

| Industry | Intended operating lens | KPI examples for later configuration, not populated observations | Financial/constraint interpretation |
|---|---|---|---|
| Logistics & Supply Chain | Warehouse operations and automation | Picks/labor hour, integration lead time, on-time completion, downtime | Site-initiative rollouts; retained productivity benefit, RaaS opex, prerequisite coverage and launch/FTE limits |
| Insurance & Financial Services | A bounded claims/service operating-unit case | Claim handling time, manual touches, service quality, exception rate | Comparable process/team deployment packages; handling-cost and service benefits net of validated operating expenses; not underwriting risk or solvency capital |
| Automotive & Manufacturing | Hypothetical eligible German vehicle-production line workflows | Downtime, first-pass yield, equipment availability, rework cost, planning cycle and energy intensity; no observed local baseline | Line-workflow deployment packages; distinct avoided downtime/rework/planning/energy pools, equipment cost and engineering capacity; not a production-network optimizer |

One normalized deployment-unit definition must apply to a case's launch ceiling. BMW uses one initiative on one eligible line workflow, never a unique-plant count. Legacy `sites`, `site_options`, `*_per_site` and dependency field names can remain internally for compatibility; label them through metadata and export their unit definition. Do not compare robot counts to site coverage or mix plants, lines and process teams without an explicit common launch-unit convention. `sites` dependencies require compatible coverage units; `any` dependencies require an earlier enabling deployment.

The existing constraints are annual capital (or cumulative carryover), annual/quarterly FTE, a portfolio launch ceiling per quarter, integer scales, earlier-quarter dependencies, commitments, exclusions, pilot evidence and mutual-exclusion groups. Unsupported constraints must fail admission. Insurance regulatory capital, actuarial pricing/reserves, machine-hour capacity and unrestricted start-date optimization are not silently approximated by these fields. They would need a separately authorized engine extension.

## Governance coverage is an admission gate

The current questionnaire is bounded: workplace/product use, selected prohibitions, transparency/GPAI, German co-determination and personal-data flags. It is not an industry-complete compliance framework. Unknown question keys now raise errors rather than being silently ignored; this does not implement new insurance law.

Before an industry case is admitted, review intended purposes, deployer/provider roles, geography, data, applicable sector duties and coverage of the registered rules. In particular, life/health risk assessment and pricing is a separately listed insurance use in [Annex III 5(c)](https://ai-act-service-desk.ec.europa.eu/en/ai-act/annex-3); the current questionnaire has no corresponding trigger. General claims/service AI is not automatically in that category. The distinction and any exceptions require a qualified applicability review.

The Allianz case is bounded to operational claims/service workflows with human decision authority and explicit exclusions of life/health pricing, underwriting eligibility, credit scoring and autonomous claim denial. This scope is not an assertion that governance review is unnecessary. [EIOPA’s governance opinion](https://www.eiopa.europa.eu/eiopa-publishes-opinion-ai-governance-and-risk%2Dmanagement-2025-08-06_en) explains that sectoral governance and risk-management expectations also matter for insurance AI outside the AI Act’s high-risk categories. Do not label excluded functions as covered by checking only the shared questionnaire.

Implement any required additional **registered sector rule module once**, shared by all applicable cases, not `if company == ...` financial logic. It should produce the same generic eligibility/cost/lead-time/review outputs consumed before valuation and scheduling. Unknown coverage must block promotion/affected funding until resolved. Reuse the existing gate convention and avoid charging compliance delay/cost twice. Human review records stay linked to the exact current analysis; they are not authenticated legal approvals.

## Shared presentation and recommendations

Keep Portfolio, Scenario Lab, Delivery Plan (Rollout/Governance/Benefits) and Decision Brief. A chart registry binds allowed view IDs to existing computed result series; no free-form plotting/calculation code in case files. Primary chart emphasis can differ by industry while all pages retain the same layout and formatting. Use the agreed restrained accents: logistics `#276E65`, insurance `#405F91`, automotive `#496E83`, with their supplied support shades. No new pages, corporate logos or official-brand imitation are needed.

Executive text combines a shared result-driven recommendation (selected scales, money, uncertainty, comparisons, feasibility) with reviewed case notes and sources. Numbers must bind to `Analysis`, not YAML prose. Distinguish a declared prerequisite from proof of incremental causal value, and distinguish a deferred scale from an initiative being worthless or absent at the company.

## Identity, state and export contract

The immutable identity must cover economic YAML, initiatives, profile, evidence actually used, calculation version, governance-profile version, applied scenario and accepted actuals. Before adding files that affect eligibility/interpretation, extend the current cache and bundle identities to include them. Different IDs/versions/content must never reuse a prior case's cached analysis, review or saved-current message.

Continue resetting financial drafts/assumptions, questionnaire answers, reviewer forms, imports, comparisons and candidate filters when cases switch. Preserve the four-page destination itself. Same initiative IDs may occur in different cases; persisted records must be scoped by case identity/version, not initiative ID alone. Actuals are rejoined only to the active plan and retain provenance; missing periods stay unknown.

Exports need `schema_version`, case/profile versions, scope, deployment-unit and currency definitions, scenario inputs, provenance and matching sources, alongside existing numeric tables. Preserve existing APIs/CSV fields or explicitly version any format migration. All supported Excel/PDF/memo/CSV/JSON/ZIP formats and saved records must describe the active case/scenario.

## Admission tests

Current tests cover independent cash-flow/enumeration references, unsupported governance answers, genuine integer commitments, same-ID cross-case state isolation, source namespace isolation and actuals-free cross-case exports.

Before admitting new profiles, add tests that reject unknown keys/versions, duplicate case IDs, path traversal, industry/profile mismatch, unsupported rule/visualization IDs, unsupported monetary units, malformed KPI units/directions/aggregation, nonexistent initiative/source references, missing scope or economic beneficiary, missing review provenance, incompatible dependency units and unsupported resource constraints. Validate evidence for scale/graduate status; do not default unknown legal answers to false.

Tests verify that changing **only** industry labels/colors/KPI names leaves valuation, selection and cash-flow numbers unchanged; changing an economic assumption recalculates all four views and exports; changing profile/evidence/rule versions invalidates caches/reviews; and switching A→B→A with colliding initiative IDs cannot restore another case's drafts, imports or reviews. Synthetic fixtures cover engineering boundaries without introducing another public company case.
