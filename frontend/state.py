"""Explicit scenario state, isolated on case changes; no valuation logic."""

from copy import deepcopy

LABELS = {
    "budget_scale": "Capital envelope",
    "discount": "Discount rate",
    "risk": "Downside penalty",
    "benefit_factor": "Benefits / adoption",
    "extra_delay_months": "Deployment delay",
    "carryover": "Capital carryover",
    "n_samples": "Simulation draws",
}


def defaults(case):
    return dict(
        budget_scale=1.0,
        discount=case.discount_rate,
        risk=float(case.risk_aversion),
        benefit_factor=1.0,
        extra_delay_months=0,
        carryover=False,
        n_samples=case.n_samples,
    )


def initialize(state, folder, case):
    if state.get("active_case") != folder:
        for key in list(state):
            if key.startswith(("input_", "question_", "review_", "benefits_", "candidate_", "research_")):
                del state[key]
        state.active_case = folder
        state.active_config = defaults(case)
        state.overrides = {}
        state.previous_scenario = None
        state.last_summary = None
        state.saved_state = None
        state.pop("saved_run", None)


def reset(state, case):
    state.active_config = defaults(case)
    state.overrides = {}
    state.previous_scenario = None
    for key, value in defaults(case).items():
        state[f"input_{key}"] = value * 100 if key == "discount" else value
    for key in list(state):
        if key.startswith("question_"):
            del state[key]


def apply(state, config):
    if config != state.active_config:
        state.previous_scenario = deepcopy(state.get("last_summary"))
        state.active_config = deepcopy(config)


def summary(a):
    return {
        "npv": a.portfolio.mean,
        "capex": float(a.portfolio.capex_by_year.sum()),
        "choice": a.portfolio.choice.copy(),
    }


def changes(config, case):
    return [LABELS[k] for k, v in defaults(case).items() if config[k] != v]
