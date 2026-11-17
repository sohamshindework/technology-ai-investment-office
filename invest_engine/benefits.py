"""Benefits-realization plan, observation validation and management summaries.

Observed benefits are operational measurements supplied by a user. They do not
change valuation, portfolio selection or planned cash flows, and they do not by
themselves establish causal attribution to an investment.
"""

from __future__ import annotations

import zlib
from datetime import date

import numpy as np
import pandas as pd

from .portfolio import Portfolio
from .schema import Case

RAG_GREEN, RAG_AMBER = 0.95, 0.80
MATERIAL_VARIANCE_PERCENT = 0.20
MATERIAL_VARIANCE_EUR_K = 50.0
CONFIDENCE_LEVELS = ("high", "medium", "low")
OBSERVATION_COLUMNS = [
    "company_id",
    "initiative_id",
    "quarter",
    "reporting_period_end",
    "observed_benefit_EUR_k",
    "currency",
    "source",
    "observation_date",
    "confidence",
    "revision",
    "is_simulated",
]


def rag(ratio: float) -> str:
    if pd.isna(ratio):
        return "unavailable"
    return "on plan" if ratio >= RAG_GREEN else "watch" if ratio >= RAG_AMBER else "below plan"


def _quarter_end(year: int, quarter: int) -> date:
    month = quarter * 3
    return (pd.Timestamp(year, month, 1) + pd.offsets.MonthEnd()).date()


def track(case: Case, portfolio: Portfolio, valuations, quarters_elapsed: int = 6) -> pd.DataFrame:
    """Build the quarterly plan and a separate fictional example series.

    The example values support product demonstration only. No value is placed in
    the observed-benefit column until the user explicitly loads example data or
    imports a validated observation file.
    """
    rows = []
    for iid, sites in portfolio.funded.items():
        quarterly = valuations[iid][sites].benefit_by_quarter
        rng = np.random.default_rng([case.seed, zlib.crc32(("benefits" + iid).encode())])
        drift = rng.normal(-0.04, 0.10)
        for q in range(quarters_elapsed):
            planned = float(quarterly[q]) if q < len(quarterly) else 0.0
            noise = rng.normal(0, 0.05)
            example = max(0.0, planned * (1 + drift * min(1.0, (q + 1) / 3) + noise))
            rows.append(
                {
                    "company_id": case.id,
                    "initiative_id": iid,
                    "quarter": q + 1,
                    "kpi": case.get(iid).kpi,
                    "planned_benefit": planned,
                    "example_observed_benefit": example,
                }
            )
    columns = ["company_id", "initiative_id", "quarter", "kpi", "planned_benefit", "example_observed_benefit"]
    plan = pd.DataFrame(rows, columns=columns)
    return _calculate(plan)


def observation_template(plan: pd.DataFrame) -> pd.DataFrame:
    """Return a documented, unpopulated CSV template for the current plan."""
    rows = plan[["company_id", "initiative_id", "quarter"]].copy()
    rows["reporting_period_end"] = rows.quarter.map(
        lambda q: _quarter_end(2025 + (q - 1) // 4, (q - 1) % 4 + 1)
    )
    rows["observed_benefit_EUR_k"] = None
    rows["currency"] = "EUR"
    rows["source"] = None
    rows["observation_date"] = None
    rows["confidence"] = None
    rows["revision"] = 1
    rows["is_simulated"] = False
    return rows[OBSERVATION_COLUMNS]


def fictional_observations(plan: pd.DataFrame) -> pd.DataFrame:
    """Return clearly labeled fictional observations for product demonstration."""
    rows = observation_template(plan)
    lookup = plan.set_index(["initiative_id", "quarter"]).example_observed_benefit
    rows["observed_benefit_EUR_k"] = [lookup.loc[(r.initiative_id, r.quarter)] for r in rows.itertuples()]
    rows["source"] = "Fictional demonstration dataset"
    rows["observation_date"] = rows.reporting_period_end
    rows["confidence"] = "medium"
    rows["is_simulated"] = True
    return rows


def _coerce_boolean(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(bool)
    values = series.astype(str).str.strip().str.lower()
    if not values.isin({"true", "false"}).all():
        raise ValueError("is_simulated must contain only true or false")
    return values.map({"true": True, "false": False})


def validate_observations(actuals: pd.DataFrame, case: Case, *, max_quarter: int = 6) -> pd.DataFrame:
    """Validate observation identity, period, provenance and measurement fields."""
    missing = set(OBSERVATION_COLUMNS) - set(actuals)
    if missing:
        raise ValueError(f"observation file is missing columns: {', '.join(sorted(missing))}")
    a = actuals[OBSERVATION_COLUMNS].copy()
    if a.empty:
        raise ValueError("observation file contains no rows")
    if a.duplicated(["company_id", "initiative_id", "quarter"]).any():
        raise ValueError("duplicate company, initiative and reporting quarter")

    if a.company_id.isna().any() or not (a.company_id.astype(str) == case.id).all():
        raise ValueError(f"all observations must use company_id {case.id}")
    allowed = {item.id for item in case.initiatives}
    unknown = sorted(set(a.initiative_id.astype(str)) - allowed)
    if unknown:
        raise ValueError(f"unknown initiative identifiers: {', '.join(unknown)}")

    quarter_number = pd.to_numeric(a.quarter, errors="coerce")
    if quarter_number.isna().any() or (quarter_number % 1 != 0).any():
        raise ValueError("quarter must be a whole number")
    a["quarter"] = quarter_number.astype(int)
    if not a.quarter.between(1, max_quarter).all():
        raise ValueError(f"quarter must be between 1 and {max_quarter}")

    amount = pd.to_numeric(a.observed_benefit_EUR_k, errors="coerce")
    if amount.isna().any() or not np.isfinite(amount).all():
        raise ValueError("observed benefits must be finite numbers; zero and negative values are permitted")
    a["observed_benefit_EUR_k"] = amount.astype(float)
    if a.currency.isna().any() or not (a.currency.astype(str).str.strip().str.upper() == "EUR").all():
        raise ValueError("currency must be EUR for this model")
    a["currency"] = "EUR"

    period_end = pd.to_datetime(a.reporting_period_end, errors="coerce")
    observed_at = pd.to_datetime(a.observation_date, errors="coerce")
    if period_end.isna().any() or observed_at.isna().any():
        raise ValueError("reporting_period_end and observation_date must be valid ISO dates")
    if not ((period_end.dt.month % 3 == 0) & period_end.dt.is_month_end).all():
        raise ValueError("reporting_period_end must be a calendar quarter-end date")
    period_index = period_end.dt.year * 4 + ((period_end.dt.month - 1) // 3)
    if (period_index - a.quarter).nunique() != 1:
        raise ValueError("reporting quarter and period-end dates are not aligned")
    if (observed_at < period_end).any():
        raise ValueError("observation_date cannot precede reporting_period_end")
    if (observed_at.dt.date > date.today()).any():
        raise ValueError("observation_date cannot be in the future")
    a["reporting_period_end"] = period_end.dt.date
    a["observation_date"] = observed_at.dt.date

    source = a.source.fillna("").astype(str).str.strip()
    if (source.str.len() < 3).any() or (source.str.len() > 200).any():
        raise ValueError("source must contain 3 to 200 characters")
    a["source"] = source
    confidence = a.confidence.fillna("").astype(str).str.strip().str.lower()
    if not confidence.isin(CONFIDENCE_LEVELS).all():
        raise ValueError(f"confidence must be one of: {', '.join(CONFIDENCE_LEVELS)}")
    a["confidence"] = confidence
    revision = pd.to_numeric(a.revision, errors="coerce")
    if revision.isna().any() or (revision % 1 != 0).any() or (revision < 1).any():
        raise ValueError("revision must be a positive whole number")
    a["revision"] = revision.astype(int)
    a["is_simulated"] = _coerce_boolean(a.is_simulated)
    return a


def import_actuals(plan: pd.DataFrame, actuals: pd.DataFrame, *, case: Case | None = None) -> pd.DataFrame:
    """Join validated observations; unreported periods remain unknown, never zero."""
    if case is None:
        raise ValueError("case metadata is required to validate benefit observations")
    max_quarter = max(int(plan.quarter.max()), 6) if not plan.empty else 6
    a = validate_observations(actuals, case, max_quarter=max_quarter)
    if plan.empty:
        return plan.copy()
    keys = ["company_id", "initiative_id", "quarter"]
    matched = a.merge(plan[keys], on=keys, how="inner")
    observation_fields = [column for column in OBSERVATION_COLUMNS if column not in keys]
    base = plan.drop(columns=observation_fields, errors="ignore")
    out = base.merge(matched[[*keys, *observation_fields]], on=keys, how="left", validate="one_to_one")
    return _calculate(out)


def _material(row) -> bool:
    if pd.isna(row.observed_benefit_EUR_k):
        return False
    variance = abs(row.variance_EUR_k)
    if row.planned_benefit == 0:
        return variance >= MATERIAL_VARIANCE_EUR_K
    return variance >= MATERIAL_VARIANCE_EUR_K and abs(row.variance_percent) >= MATERIAL_VARIANCE_PERCENT


def _calculate(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy().sort_values(["initiative_id", "quarter"], ignore_index=True)
    if "observed_benefit_EUR_k" not in out:
        out["observed_benefit_EUR_k"] = np.nan
    if "is_simulated" not in out:
        out["is_simulated"] = pd.NA
    out["variance_EUR_k"] = out.observed_benefit_EUR_k - out.planned_benefit
    out["variance_percent"] = out.variance_EUR_k / out.planned_benefit.replace(0, np.nan)
    out["material_deviation"] = out.apply(_material, axis=1)
    out["observation_status"] = np.where(out.observed_benefit_EUR_k.notna(), "reported", "missing")
    return out


def initiative_summary(df: pd.DataFrame, reporting_quarter: int | None = None) -> pd.DataFrame:
    """Compare observed benefits only with matching planned periods."""
    columns = [
        "initiative_id", "kpi", "reporting_quarter", "planned_for_observed", "observed_benefit",
        "variance_EUR_k", "variance_percent", "expected_periods", "observed_periods", "coverage",
        "missing_periods", "confidence", "sources", "material_deviation", "observation_type",
    ]
    if df.empty:
        return pd.DataFrame(columns=columns)
    cutoff = reporting_quarter or int(df.quarter.max())
    use = df[df.quarter <= cutoff].copy()
    rows = []
    confidence_order = {"high": 0, "medium": 1, "low": 2}
    for (initiative_id, kpi), group in use.groupby(["initiative_id", "kpi"], sort=False):
        observed = group[group.observed_benefit_EUR_k.notna()]
        planned = float(observed.planned_benefit.sum())
        actual = float(observed.observed_benefit_EUR_k.sum()) if not observed.empty else np.nan
        variance = actual - planned if not observed.empty else np.nan
        ratio = variance / planned if not observed.empty and planned != 0 else np.nan
        confidence = (
            max(observed.confidence, key=lambda value: confidence_order[value]) if not observed.empty else "unavailable"
        )
        simulated = bool(observed.is_simulated.fillna(False).any()) if not observed.empty else False
        rows.append(
            {
                "initiative_id": initiative_id,
                "kpi": kpi,
                "reporting_quarter": cutoff,
                "planned_for_observed": planned,
                "observed_benefit": actual,
                "variance_EUR_k": variance,
                "variance_percent": ratio,
                "expected_periods": len(group),
                "observed_periods": len(observed),
                "coverage": len(observed) / len(group),
                "missing_periods": ", ".join(
                    f"Q{q}" for q in group.loc[group.observed_benefit_EUR_k.isna(), "quarter"]
                ),
                "confidence": confidence,
                "sources": "; ".join(sorted(set(observed.source))) if not observed.empty else "Unavailable",
                "material_deviation": bool(observed.material_deviation.any()),
                "observation_type": (
                    "Fictional demonstration" if simulated else "User-provided" if not observed.empty else "Unavailable"
                ),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def portfolio_summary(df: pd.DataFrame, reporting_quarter: int | None = None) -> dict:
    detail = initiative_summary(df, reporting_quarter)
    empty = {
        "reporting_quarter": reporting_quarter or 0,
        "planned": 0.0,
        "observed": None,
        "variance": None,
        "variance_percent": None,
        "coverage": 0.0,
        "material_count": 0,
        "complete": False,
    }
    if detail.empty:
        return empty
    observed = detail[detail.observed_periods > 0]
    if observed.empty:
        return {**empty, "reporting_quarter": int(detail.reporting_quarter.max())}
    planned = float(observed.planned_for_observed.sum())
    actual = float(observed.observed_benefit.sum())
    variance = actual - planned
    expected = int(detail.expected_periods.sum())
    reported = int(detail.observed_periods.sum())
    return {
        "reporting_quarter": int(detail.reporting_quarter.max()),
        "planned": planned,
        "observed": actual,
        "variance": variance,
        "variance_percent": variance / planned if planned else None,
        "coverage": reported / expected if expected else 0.0,
        "material_count": int(detail.material_deviation.sum()),
        "complete": reported == expected,
    }


def latest_status(df: pd.DataFrame) -> pd.DataFrame:
    """Compatibility presentation of the latest initiative summaries."""
    summary = initiative_summary(df)
    if summary.empty:
        return summary
    return summary.assign(
        cum_planned=summary.planned_for_observed,
        cum_actual=summary.observed_benefit,
        ratio=np.where(
            summary.planned_for_observed != 0,
            summary.observed_benefit / summary.planned_for_observed,
            np.nan,
        ),
        rag=lambda value: value.ratio.map(rag),
        benefit_gap=summary.variance_EUR_k,
    )


def follow_up_items(df: pd.DataFrame, reporting_quarter: int | None = None) -> list[str]:
    detail = initiative_summary(df, reporting_quarter)
    items = []
    for row in detail.itertuples(index=False):
        if row.observed_periods == 0:
            items.append(f"Obtain observations for {row.initiative_id} through Q{row.reporting_quarter}.")
        elif row.missing_periods:
            items.append(f"Complete {row.initiative_id} observations for {row.missing_periods}.")
        if row.material_deviation:
            items.append(
                f"Review the material variance for {row.initiative_id} and test whether the change is attributable to the investment."
            )
        if row.confidence == "low":
            items.append(f"Strengthen measurement evidence for {row.initiative_id}; current confidence is low.")
    return items
