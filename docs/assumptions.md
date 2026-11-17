# Assumptions and adapting the case

The complete current assumption register is downloadable as `assumptions.csv`, together with `settings.json` containing all initiative inputs and current settings. No input was tuned to preserve a headline. DHL economics, rollout sizes, success probabilities, budgets, FTE and governance answers are explicitly hypothetical. Public footprint numbers support opportunity framing, not return estimates.

DHL Supply Chain defaults: EUR 60m annual capex split 22/22/16m; FTE-years 45/45/35; eight-year cash flows, three-year quarterly rollout; 9% discount rate; risk penalty 0.5; 4,000 draws; seed 2026; demand triangular [0.85,1,1.10]. Cost ranges and benefits are in `cases/dhl_supply_chain/initiatives.yaml`. Implementation and compliance cash costs should include labour where appropriate; FTE is a capacity measure, not a wage charge. Dependencies define required coverage and do not automatically suppress benefits in simulation when an enabler underdelivers.

All 13 governance answers are explicit in each initiative. The prior sparse answers are expanded to negative **design hypotheses**, not confirmed company facts. Missing or null answers exclude funding. Every screening still awaits human legal review. The questionnaire covers selected triggers, not every AI Act sector or prohibited practice. `screen` accepts partial inputs for preliminary flagging, but sets `excluded=True` if any essential answer is absent.

Adaptive robotics has an unapproved pilot gate and a hypothetical 81% minimum success rule. The financial break-even is recomputed from current quarterly cash flows and displayed in the option report; it can differ from the separate 81% committee rule. Passing a probability threshold is necessary but does not create approval. A gate requires `approved: true`, reviewer, evidence and ISO review date in the case file, as well as meeting its minimum success probability. This configuration is a local review workflow, not a tamper-resistant authorization mechanism.

## Add a company

1. Copy `cases/_template` to a named case folder. Set a unique `id`, company, unit, question and disclaimer. The blank template has no invented facts or citations.
2. Add public sources under `sources`, with identifier, title, HTTPS URL and ISO `accessed` date. Each fact must reference an existing source. Distinguish reviewed facts from proposed projects.
3. Create candidate initiatives with all required economics, explicit governance answers and zero/positive integer `site_options`. Ranges are scalar or `[low,mode,high]`. Costs, delays, ramp and FTE must be finite and nonnegative; probabilities are [0,1]; discount rate must exceed −1; budget/FTE lists cover rollout years exactly.
4. `scale` / `graduate` require sources and `public_basis`; `new` means a hypothetical proposal, never proof the company lacks a capability. Optional `requires` entries use `initiative`, `mode: any|sites` and nonnegative integer `baseline_sites`. Cycles are invalid.
5. Optional `exclusive_group` names alternatives: at most one funded member. Optional `pilot_gate` defines `approved`, `min_success_probability`, `reviewer`, `evidence`, `reviewed_at`.
6. Set the portfolio-wide quarterly site limit and annual FTE-years deliberately. The model enforces quarterly FTE-years at one fourth of annual capacity. Optional `deployment_delay_quarters` shifts earliest starts inside the unchanged rollout deadline. Compliance gates and prior-quarter coverage are shared with valuation. The engine optimizes scales under deterministic quarterly phasing; it does not optimize arbitrary start dates.
7. Run `python scripts/run_case.py cases/<folder>` and inspect the committee pack. Re-run tests. The synthetic case provides a company-independent, reproducible reference.

The public scope contains exactly three illustrative company cases. Numeric operational KPI measurements, milestone actuals and externally calibrated risk factors are not supplied; KPI definitions and scheduled gate/deployment activities are available.

The fixed-phasing policy and quarter-end cash-flow convention are defined in `docs/methodology.md`. Case labels do not affect economics. The €60m example, staffing, rollout deployments and recommendations are solely hypothetical DHL Supply Chain inputs/results, not a Group-wide allocation.
