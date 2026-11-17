# Quarterly rollout correction — DHL Supply Chain

14 November 2026. Supersedes the earlier annual-model financial results. No additional company cases were created; no commit or push was made.

## Original inconsistency

The annual valuation spread every rollout evenly across three years and discounted annual cash flows. Selection constrained annual capital/FTE and final dependency coverage. A second greedy roadmap subsequently applied quarterly staffing, review gates and an eight-deployment portfolio-wide ceiling. Those dates never fed back into valuation. The selected 590 initiative/site deployments could not fit a 96-deployment, 12-quarter maximum; merely showing a warning did not resolve this. The benefits tracker also assumed every quarter received one fourth of an annual benefit, even before go-live.

## Smallest consistent correction

Retain the existing discrete options, seeded Monte Carlo, CP-SAT, risk objective and annual budget policy. Replace the two independent timing rules with one deterministic quarterly cohort policy, shared across the entire pipeline:

1. Compliance lead time is rounded up to whole quarters and planned before deployment, with a minimum one-quarter gate when required. It is not added again to benefit delay.
2. Earliest deployment respects the case's additional delay and any prerequisite needing a prior-quarter deployment. Baseline-covered dependencies can start against existing coverage.
3. Each scale option splits integer cohorts evenly across remaining quarters before the original rollout deadline, earlier quarters taking remainders. An option with no remaining deployment quarter is unavailable.
4. The optimizer enforces quarterly site capacity, quarterly FTE-years (annual capacity / four), annual/cumulative expected capex, commitments, exclusions, pilot gates and alternatives. Coverage is tested in every quarter using prerequisite deployments completed in previous quarters, not merely final totals.
5. Deployments complete at quarter end. Capex is paid then; platform/compliance costs occur at programme start. Opex and benefits start in the following quarter; intrinsic months-to-value and benefit ramp remain unchanged. Cash flows are discounted at quarter end using the annual discount rate. Annual tables aggregate those cash flows and their already-discounted values.
6. Roadmap rows project the chosen valuation cohorts. Planned tracking benefits use those exact quarterly benefits. No independent rescheduling or annual-benefit division remains.

This is a fixed-phasing portfolio model, not a free-start-date scheduling optimizer. That restriction is deliberate: it keeps the correction small, additive and independently testable. It can leave feasible time slots/capital unused; optimality is only over the stated policy. The initial 18-month roadmap API remains a projection of the complete plan; later deployments are already scheduled, not unvalued backlog.

## Recomputed default results

| Measure | Value |
|---|---:|
| Expected portfolio NPV | €48.11m |
| Expected capex | €23.49m |
| Ranked baseline NPV | €27.36m |
| NPV difference | €20.75m |
| P10 / P90 NPV | €5.74m / €87.37m |
| Simulated negative-NPV draws | 277 / 4000 (6.925%) |
| Undiscounted operating benefits over 8 years | €210.15m |
| Candidates / funded initiatives | 12 / 3 |
| Scheduled initiative/site deployments | 80 / 80 |
| Unscheduled selected deployments | 0 |

The funded initiatives are the integration layer (20), AMRs (20) and AI orchestration (40), all scoped to DHL Supply Chain. The solver reports OPTIMAL, gap 0.000%, risk-adjusted objective bound €45.86m. It selects 80 deployments; 42 complete by month 18 and the other 38 by month 36. Maximum quarterly throughput is eight. Annual FTE-years are 12.2 / 14.2 / 11.6, below 45 / 45 / 35.

All original numeric case settings and all 12 candidates' cost/benefit distributions, success probabilities, site options and dependency inputs were checked against the supplied original and remain unchanged. Changed results come from the corrected timing/feasibility model, not economic retuning. Company-name metadata alone was separately tested not to change valuation.

## Scope correction

The case name, selector, chart context, settings and memo now say **DHL Supply Chain**. The €60m envelope and its staffing/KPIs are hypothetical divisional assumptions. Publisher/report titles correctly retain “DHL Group” when citing division facts. The Group-strategy context fact and cross-division replication recommendations were removed; no Group-wide portfolio is implemented.

## Regression and verification

See `docs/validation.md` for measured results. Added independent analytical cash-flow references, exhaustive small-instance selection under quarterly constraints, gate/no-double-delay tests, temporal coverage counterexamples, quarterly staffing/deployment infeasibility, delay/deadline handling, stale-capacity detection and a full DHL roadmap/valuation/benefits/export reconciliation. Existing tests were retained. Annual cash-flow expectations and the obsolete fixed UI headline were intentionally updated to the documented quarter-end convention; the budget test now checks budget display rather than demanding an NPV change when capital is not binding.

The dashboard retains its premium light theme. Calculation-version-aware caching prevents old annual-model results from being reused. Memo, CSV, JSON and ZIP exports are regenerated from the same current Analysis. No API key, new dependency, company case, commit or GitHub push is involved.

## Remaining limitations

Fixed phasing is a policy restriction, not globally optimal sequencing. Capital constraints use expected sampled cost, not guaranteed worst-case cost. Financial distributions remain hypothetical; benefit overlap, failure contagion, taxes and working capital are not modelled. Midpoint quarterly ramps are an approximation. Planned gates do not demonstrate human legal approval. Actual benefit tracking remains explicitly simulated unless user-supplied. Native PDF/XLSX and research AI remain unimplemented.
