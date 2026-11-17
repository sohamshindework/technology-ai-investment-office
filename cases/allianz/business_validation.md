# Allianz — hypothetical German P&C claims and service investment decision

Technology & AI Investment Strategy · 14 November 2026

## Decision boundary and public evidence

The modeled beneficiary is a **hypothetical German property and casualty claims/customer-service operating unit**, using comparable team-workflow deployments. It is not an Allianz Group-wide portfolio, a real budget, an assertion of gaps in existing Allianz systems, or a proposal for automated coverage, payout or denial authority. Life/health risk assessment and pricing, underwriting/credit eligibility and autonomous claim denial are outside scope. Every cost, benefit, probability, launch slot and capacity input is illustrative and needs local owner review.

Allianz reports [Insurance Copilot](https://www.allianz.com/en/mediacenter/news/articles/250205-smarter-claims-management-smoother-settlements.html) launched for Austrian motor claims and expanded to property, and [Enterprise Knowledge Assistant](https://www.allianz.com/en/mediacenter/news/articles/250207-allianz-ai-enterprise-knowledge-assistant-enhances-productivity.html) live in German entities including Allianz Versicherung. Its [responsible AI account](https://www.allianz.com/en/mediacenter/news/articles/260318-responsible-use-of-ai-at-allianz.html) describes OCR/AI checks for simple P&C claims and a German pet-insurance example. The [Australian Nemo example](https://www.allianz.com/en/mediacenter/news/articles/251103-when-the-storm-clears-so-should-the-claim-queue.html) describes bounded agentic food-spoilage claims preparation with a human payout decision. The [2025 annual report](https://www.allianz.com/content/dam/onemarketing/azcom/Allianz_com/investor-relations/en/results-reports/annual-report/ar-2025/en-allianz-group-annual-report-2025.pdf) describes AI in claims/customer service, customer feedback and formal complaint processes. These official publications establish existing capability and governance context, **not the economics or readiness of the modeled German team workflows**.

[EIOPA's AI governance opinion](https://www.eiopa.europa.eu/publications/opinion-artificial-intelligence-governance-and-risk-management_en) supports a separate insurance-sector risk/governance review. The current application questionnaire is a preliminary subset of AI Act workplace, transparency and GPAI questions; it does not certify insurance consumer fairness, privacy, model risk, ICT resilience or the actual claims decision process. The design profile requires human claim authority and these approval domains, but no real Allianz approval is recorded.

## Ten distinct hypothetical candidates

| ID | Investment question | Status and benefit boundary |
|---|---|---|
| DATA_TRACE | Extend policy/claim/service record links, consent and audit traces | Hypothetical local infrastructure; only reconciliation benefit counted, not downstream productivity |
| CLAIM_DOC | Extend document extraction and checks to eligible teams | Incremental coverage of documented capability; uncertain documents go to handlers |
| CLAIM_COPILOT | Extend sourced summaries and policy lookup to handlers | Incremental coverage of documented copilot pattern; handler retains decisions |
| CLAIM_TRIAGE | Route incoming complexity/urgency to human teams | Proposed local workflow; no coverage or payout decision |
| FRAUD_ASSIST | Provide explainable referrals to investigators | Pilot-gated; no automatic finding or denial; only review-workload value assumed |
| SERVICE_KNOWLEDGE | Extend EKA-style internal knowledge assistance | Incremental team coverage, not first invention of EKA |
| SERVICE_REPLY | Draft grounded responses for agent approval | Separate from knowledge-search value; human sends all messages |
| COMPLAINT_ROUTE | Flag complaints and vulnerable-customer cases | Human escalation with existing complaint deadlines preserved |
| SURGE_PREP | Prepare catastrophe-surge claim packets | Pilot-gated German adaptation; Australian Nemo speed is not transferred numerically |
| QUALITY_AUDIT | Sample claims and service outputs for review | Human quality function; fairness value remains nonmonetized |

The [case inputs](initiatives.yaml) list all low/mode/high EUR k per-team costs and annual gross benefits, success assumptions, intrinsic delays, resources, dependencies and gates. Shared assumptions are a seven-year cash horizon, 10% annual discount rate, three-year €11m illustrative capital envelope (€4m/€3.8m/€3.2m), annual effort capacity 12/12/10 FTE-years, at most four team-workflow deployments per quarter, 3,000 seeded draws and fixed quarterly phasing. A baseline of two compatible data connections is an **assumption**, not an Allianz inventory. No observed local volumes, costs or KPI baselines are available; the model cannot infer them from the public sources.

## Calculated recommendation and tradeoff

The common engine selects **DATA_TRACE 4, CLAIM_DOC 6, CLAIM_COPILOT 6 and SERVICE_KNOWLEDGE 6**: four initiative types and 22 team-workflow deployments. It calculates expected NPV **€3.940675m**, expected capex **€4.584192m**, seven-year undiscounted gross benefits **€21.894176m**, recurring opex **€9.223441m**, P10/P90 NPV **−€0.583415m / €8.263894m**, and modeled loss probability **13.07%**. The same-constraint ranked-list NPV is €3.206218m. Capital is not exhausted because its €11m ceiling is not the binding resource at this optimum. The result is an optimizer output, not a target value.

All 22 deployments complete by Q6 with quarter counts **4, 4, 4, 4, 3, 3**; the remaining quarters have zero selected deployments. The launch ceiling binds in Q1–Q4. The selected data prerequisite plus assumed two existing connections covers the six-document and six-copilot team deployments in the required earlier quarters; coverage is reusable by compatible workflows, not a consumed inventory. No deployment is unscheduled. A dependency-ordered independent audit checks all option cash flows, gates, capex, benefits, FTE and prior-quarter coverage, and enumerates **2,944 feasible portfolios** across **7,711 nodes**. It recovers the same selected scales and €3,068,140 integer risk-adjusted objective. Maximum seeded sample discrepancy is about 3.18 × 10⁻¹² EUR k. This is an optimum conditional on the fixed phasing and submitted options, not unrestricted sequencing or verified business assumptions.

In the shared stress scenarios, a 30% reduction in all benefits cuts optimized expected NPV to about **€0.315m** and capex to **€1.090m**; 20% lower adoption/benefits gives about **€1.139m** NPV and **€1.943m** capex. A six-month delivery delay gives **€3.122m** NPV at the original selected capex. These are re-optimized model scenarios. The selected portfolio can change; no fixed recommendation is embedded in the UI.

## Decision conditions and limitations

1. **Confirm baseline and incremental value.** Identify current copilot, EKA, OCR, claims platform and service coverage for the actual proposed teams. Validate claim/contact volumes, handling costs and retained value. Do not count existing-tool productivity as incremental savings.
2. **Separate benefit pools.** Document extraction and copilot can save the same handler minutes. EKA and response drafting can save the same agent minutes. The model has no overlap adjustment; the financial owner must create nonoverlapping benefit estimates or revise inputs before approval.
3. **Confirm control design.** Human adjusters decide coverage, payout and denial. Local legal/privacy, insurance model-risk, fairness, ICT/vendor and workforce owners must assess intended use, data flows, explainability, audit logs and resilience. The profile's design review is not legal or management approval.
4. **Keep pilots gated.** Fraud assistance and surge preparation are excluded under current unapproved pilot gates. Their positive standalone option values, if any, do not prove deployment readiness.
5. **Validate unit and timing.** One launch slot means one initiative in one eligible team workflow. Teams can share infrastructure but may need distinct integration work. Fixed quarterly phasing, modeled two existing connections and four launches per quarter are hypothetical. The engine does not optimize arbitrary start dates, staffing skills or regulatory capital.
6. **Measure operations separately.** The profile defines claim handling time, direct cost per claim, exception rate, customer response time and referral precision with owners and aggregation conventions. Their baselines/targets are intentionally null. The benefits tracker measures money; it does not invent operational KPI observations.

Subject to those validations, the calculated portfolio supports a **conditional investment investigation**: prioritize the data/control foundation and incremental, human-led document, copilot and service knowledge coverage; retain fraud/surge pilots for evidence review; revisit the remaining alternatives if capacity, benefits or approvals change.
