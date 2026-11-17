# Quarterly financial and selection methodology

All money is EUR thousands; charts convert to €m. The worked portfolio is exclusively hypothetical DHL Supply Chain planning. The engine itself has no company-specific rules.

## Shared rollout policy

`deployment.py` creates a quarterly cohort vector for each discrete initiative/scale option. Deployments are integer counts, spread evenly across remaining quarters inside the fixed `rollout_years × 4` deadline; earlier quarters take remainders. Programme/gate start and earliest deployment respect additional case delay and prerequisite lead time. Options with no remaining rollout quarter are unavailable, not zero-cost investments. Compliance lead is `max(required_gate, ceil(delay_months/3))` quarters. A funding prerequisite or zero-baseline coverage dependency requires a prior-quarter prerequisite deployment. Coverage against positive baseline capacity may begin earlier but is checked each quarter.

Central implementation FTE-years are charged at `central_fte / 4` in every programme quarter, including gate quarters; site effort is charged in its completion quarter. Each quarter's capacity is the corresponding year's capacity divided by four. Deployment counts are initiative/site completions, not necessarily different physical facilities.

## Cash-flow convention

A cohort completes at the end of quarter t. Its capex is paid at that quarter end. Platform and screening capex are paid at programme start. The cohort pays annual opex / four in each following operating quarter. Benefits begin only after completion and intrinsic time-to-value. For q > t:

`maturity(q,t) = (q − t − 0.5)/4 − months_to_value/12`

`benefit(q,t) = sites(t) × annual_benefit/4 × clip(maturity/ramp_years, 0, 1) × outcome_multiplier`

Zero ramp uses an immediate step at nonnegative maturity. Compliance delay is already spent in pre-deployment gates and is not counted twice. This remains a quarterly midpoint approximation to a continuous benefit ramp.

`NPV = Σ_q net_cash(q) / (1 + annual_discount_rate)^((q+1)/4)`

Annual capex, FTE, benefits and cash flows sum their underlying quarters. Annual discounted cash flows sum already-discounted quarters; they are not discounted a second time at year end. Planned benefits in the tracker use each quarter's actual modelled benefit, rather than annual benefit / four. Payback remains the year of sustained undiscounted year-end recovery, using the quarterly plan aggregated by year.

Analytical reference: one site completed at Q1-end, capex 60, annual opex 10, annual benefit 80, no ramp/delay, annual rate 10% and three-year horizon gives quarter cash flows `[-60,17.5,…,17.5]` (11 operating quarters). Annual flows are `[-7.5,70,70]`; NPV is `−60/1.1^0.25 + Σ(q=2..12)17.5/1.1^(q/4)`.

## Uncertainty and objective

Triangular economics, initiative Bernoulli success/underdelivery, shared demand draws, seed and common random numbers across scales remain unchanged. Success affects benefits, not physical deployment or incurred costs. Dependency failure contagion and overlapping benefits are not modelled. There is no terminal value, tax or working-capital adjustment. Include implementation labour in input costs; FTE is a capacity measure, not an additional wage charge.

The objective remains `Σ_i [E(NPV_i) − λ E(max(0,−NPV_i))]`. It penalizes the sum of initiative expected losses, not aggregate portfolio expected loss. One discrete scale is selected for each initiative, including zero. Annual or cumulative expected capex, annual and quarterly FTE, quarterly deployment counts, minimum commitments, exclusion/pilot rules and mutually exclusive groups apply.

For every quarter q and coverage dependency i → j:

`Σ(t≤q) deployments_i(t) ≤ baseline_coverage + Σ(t<q) deployments_j(t)`

An `any` dependency likewise requires positive prerequisite deployment in a preceding quarter before the dependent's first deployment. This prevents a final-coverage-feasible portfolio from operating prematurely.

## Optimality and benchmark

CP-SAT uses conservative resource rounding at 1e6 units per EUR k/FTE-year, €1 objective precision, one worker and a fixed seed. An independent unrounded check validates quarterly/annual capacities and dependencies before the roadmap is displayed. Bounds/status/gap are retained; failures do not produce recommendations. OPTIMAL refers to this integer **fixed-phasing scale-choice model**, not the unrestricted scheduling problem. The objective-rounding error is at most €0.50 per initiative per portfolio.

The ranked baseline retains its maximum-scale value/capex ranking and largest-feasible-scale insertion rule. Each insertion now passes the same quarterly checks. It does not package enablers or revisit skipped prerequisites; an infeasible commitment set is unavailable. It is a simple benchmark, not an optimal sequencing method.

Scenarios revalue and reoptimize using the same policy. The original set is base plus seven adverse scenarios; the extended application adds adoption −20% and a real two-quarter deployment delay. Additional delay compresses available rollout quarters within the unchanged deadline and can change the feasible scales. Intrinsic months-to-value is a separate financial assumption. Stability includes feasible scenario solves, not a statistical confidence estimate.
