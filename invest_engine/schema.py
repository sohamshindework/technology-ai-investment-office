"""Data model and YAML loading for the investment engine.

The engine is company-agnostic. A *case* (one company) is a folder with:
  case.yaml         company context, budget, capacity, sources
  initiatives.yaml  candidate initiatives with labelled assumptions
Nothing company-specific lives in the engine package.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

VALID_STATUS = {"scale", "graduate", "new"}
STATUS_LABEL = {
    "scale": "Scale a publicly documented capability",
    "graduate": "Move a publicly documented pilot into live operations",
    "new": "Hypothetical incremental initiative",
}


class CaseError(ValueError):
    """Raised when a case file is inconsistent."""


@dataclass(frozen=True)
class Tri:
    """Triangular distribution (low, mode, high)."""

    low: float
    mode: float
    high: float

    def __post_init__(self):
        if not all(math.isfinite(v) for v in (self.low, self.mode, self.high)):
            raise CaseError("distribution values must be finite")
        if not self.low <= self.mode <= self.high:
            raise CaseError("distribution requires low <= mode <= high")

    @classmethod
    def parse(cls, value: Any, name: str) -> Tri:
        if isinstance(value, (int, float)):
            v = float(value)
            return cls(v, v, v)
        if isinstance(value, (list, tuple)) and len(value) == 3:
            lo, mo, hi = (float(x) for x in value)
            if not lo <= mo <= hi:
                raise CaseError(f"{name}: expected low <= mode <= high, got {value}")
            return cls(lo, mo, hi)
        raise CaseError(f"{name}: expected a number or [low, mode, high], got {value!r}")

    @property
    def mean(self) -> float:
        return (self.low + self.mode + self.high) / 3.0


@dataclass
class Dependency:
    initiative: str
    mode: str = "any"  # "any": B must be selected; "sites": sites_A <= baseline + sites_B
    baseline_sites: int = 0


@dataclass
class Initiative:
    id: str
    name: str
    function: str
    status: str
    description: str
    public_basis: str
    sources: list[str]
    site_options: list[int]
    capex_per_site: Tri  # EUR k, one-off per site
    opex_per_site: Tri  # EUR k per site per year
    benefit_per_site: Tri  # EUR k per site per year at full run-rate
    platform_capex: Tri  # EUR k, one-off if selected at all
    months_to_value: Tri  # delay after a site goes live
    ramp_years: float
    p_success: float
    fail_benefit_share: float
    fte_per_site: float  # implementation FTE-years per site rollout
    central_fte: float  # FTE-years per rollout year if selected
    kpi: str
    ai_act: dict[str, bool | None]
    requires: list[Dependency] = field(default_factory=list)
    committed_min_sites: int = 0
    assumption_notes: str = ""
    library_ref: str = ""
    exclusive_group: str = ""
    pilot_gate: dict[str, Any] = field(default_factory=dict)

    @property
    def status_label(self) -> str:
        return STATUS_LABEL[self.status]


@dataclass
class Case:
    id: str
    company: str
    unit: str
    title: str
    question: str
    currency_unit: str
    horizon_years: int
    rollout_years: int
    discount_rate: float
    budget_by_year: list[float]  # EUR k capex, years 1..n
    fte_capacity_by_year: list[float]
    risk_aversion: float
    volume_factor: Tri
    n_samples: int
    seed: int
    max_sites_per_quarter: int
    compliance: dict[str, Any]
    facts: list[dict[str, Any]]
    sources: dict[str, dict[str, str]]
    disclaimer: str
    initiatives: list[Initiative]
    path: Path | None = None
    deployment_delay_quarters: int = 0
    profile: Any | None = None

    def get(self, initiative_id: str) -> Initiative:
        for ini in self.initiatives:
            if ini.id == initiative_id:
                return ini
        raise KeyError(initiative_id)


def _initiative(raw: dict[str, Any], defaults: dict[str, Any]) -> Initiative:
    d = {**defaults, **raw}
    iid = d.get("id", "<missing id>")
    try:
        status = d["status"]
        if status not in VALID_STATUS:
            raise CaseError(f"{iid}: status must be one of {sorted(VALID_STATUS)}")
        if any(type(x) is not int or x < 0 for x in d["site_options"]):
            raise CaseError(f"{iid}: site options must be nonnegative integers")
        options = sorted(set(d["site_options"]) | {0})
        if any(v is not None and type(v) is not bool for v in (d.get("ai_act") or {}).values()):
            raise CaseError(f"{iid}: governance answers must be booleans or null")
        reqs = [Dependency(**r) for r in d.get("requires", [])]
        for r in reqs:
            if r.mode not in {"any", "sites"}:
                raise CaseError(f"{iid}: dependency mode must be 'any' or 'sites'")
        if type(d.get("committed_min_sites", 0)) is not int:
            raise CaseError(f"{iid}: committed_min_sites must be an integer")
        p = float(d["p_success"])
        if not 0 <= p <= 1:
            raise CaseError(f"{iid}: p_success must be in [0, 1]")
        return Initiative(
            id=iid,
            name=d["name"],
            function=d["function"],
            status=status,
            description=d["description"].strip(),
            public_basis=d.get("public_basis", "").strip(),
            sources=list(d.get("sources", [])),
            site_options=options,
            capex_per_site=Tri.parse(d["capex_per_site"], f"{iid}.capex_per_site"),
            opex_per_site=Tri.parse(d["opex_per_site"], f"{iid}.opex_per_site"),
            benefit_per_site=Tri.parse(d["benefit_per_site"], f"{iid}.benefit_per_site"),
            platform_capex=Tri.parse(d.get("platform_capex", 0), f"{iid}.platform_capex"),
            months_to_value=Tri.parse(d["months_to_value"], f"{iid}.months_to_value"),
            ramp_years=float(d["ramp_years"]),
            p_success=p,
            fail_benefit_share=float(d["fail_benefit_share"]),
            fte_per_site=float(d["fte_per_site"]),
            central_fte=float(d["central_fte"]),
            kpi=d["kpi"],
            ai_act=dict(d.get("ai_act") or {}),
            requires=reqs,
            committed_min_sites=d.get("committed_min_sites", 0),
            assumption_notes=d.get("assumption_notes", "").strip(),
            library_ref=d.get("library_ref", ""),
            exclusive_group=d.get("exclusive_group", ""),
            pilot_gate=d.get("pilot_gate", {}),
        )
    except KeyError as exc:
        raise CaseError(f"{iid}: missing field {exc}") from exc


def _load_case(folder: str | Path) -> Case:
    folder = Path(folder)
    case_raw = yaml.safe_load((folder / "case.yaml").read_text(encoding="utf-8"))
    ini_raw = yaml.safe_load((folder / "initiatives.yaml").read_text(encoding="utf-8"))
    defaults = ini_raw.get("defaults", {})
    initiatives = [_initiative(r, defaults) for r in ini_raw["initiatives"]]

    m = case_raw["model"]
    for key in (
        "horizon_years",
        "rollout_years",
        "n_samples",
        "seed",
        "max_sites_per_quarter",
        "deployment_delay_quarters",
    ):
        if key in m and type(m[key]) is not int:
            raise CaseError(f"{key} must be an integer")
    case = Case(
        id=case_raw["id"],
        company=case_raw["company"],
        unit=case_raw.get("unit", ""),
        title=case_raw["title"],
        question=case_raw["question"].strip(),
        currency_unit=m.get("currency_unit", "EUR k"),
        horizon_years=int(m["horizon_years"]),
        rollout_years=int(m["rollout_years"]),
        discount_rate=float(m["discount_rate"]),
        budget_by_year=[float(x) for x in m["budget_by_year"]],
        fte_capacity_by_year=[float(x) for x in m["fte_capacity_by_year"]],
        risk_aversion=float(m.get("risk_aversion", 0.5)),
        volume_factor=Tri.parse(m.get("volume_factor", 1.0), "volume_factor"),
        n_samples=int(m.get("n_samples", 4000)),
        seed=int(m.get("seed", 7)),
        max_sites_per_quarter=int(m.get("max_sites_per_quarter", 8)),
        deployment_delay_quarters=m.get("deployment_delay_quarters", 0),
        compliance=case_raw.get("compliance", {}),
        facts=case_raw.get("facts", []),
        sources=case_raw.get("sources", {}),
        disclaimer=case_raw.get("disclaimer", "").strip(),
        initiatives=initiatives,
        path=folder,
    )
    validate(case)
    if (folder / "profile.yaml").exists() or (folder / "evidence.yaml").exists():
        from .case_config import load_profile

        case.profile = load_profile(folder, case)
    return case


def validate(case: Case) -> None:
    from .ai_act import QUESTIONS

    def finite(value, name, minimum=None):
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise CaseError(f"{name} must be finite")
        if minimum is not None and value < minimum:
            raise CaseError(f"{name} must be >= {minimum}")

    for name in ("horizon_years", "rollout_years", "n_samples", "max_sites_per_quarter"):
        value = getattr(case, name)
        if type(value) is not int or value < 1:
            raise CaseError(f"{name} must be a positive integer")
    if type(case.seed) is not int or case.seed < 0:
        raise CaseError("seed must be a nonnegative integer")
    if type(case.deployment_delay_quarters) is not int or case.deployment_delay_quarters < 0:
        raise CaseError("deployment_delay_quarters must be a nonnegative integer")
    finite(case.discount_rate, "discount_rate")
    if case.discount_rate <= -1:
        raise CaseError("discount_rate must exceed -1")
    finite(case.risk_aversion, "risk_aversion", 0)
    if case.currency_unit != "EUR k":
        raise CaseError("supported currency_unit is EUR k; convert inputs explicitly")
    if case.volume_factor.low < 0:
        raise CaseError("volume factor cannot be negative")
    if len(case.budget_by_year) != case.rollout_years:
        raise CaseError("budget/capacity schedules must cover exactly rollout_years")
    for name in ("budget_by_year", "fte_capacity_by_year"):
        for x in getattr(case, name):
            finite(x, name, 0)
    for name, value in case.compliance.items():
        finite(value, f"compliance.{name}", 0)
    if not case.initiatives:
        raise CaseError("case needs at least one initiative")
    ids = [i.id for i in case.initiatives]
    if len(ids) != len(set(ids)):
        raise CaseError("duplicate initiative ids")
    if len(case.budget_by_year) != len(case.fte_capacity_by_year):
        raise CaseError("budget_by_year and fte_capacity_by_year must have the same length")
    if case.rollout_years > case.horizon_years:
        raise CaseError("rollout_years cannot exceed horizon_years")
    for ini in case.initiatives:
        if not ini.id or ini.status not in VALID_STATUS:
            raise CaseError("initiative needs an identifier and valid status")
        if ini.site_options != sorted(set(ini.site_options)) or 0 not in ini.site_options:
            raise CaseError(f"{ini.id}: site options must be sorted, unique and include zero")
        if any(type(x) is not int or x < 0 for x in ini.site_options):
            raise CaseError(f"{ini.id}: invalid site count")
        for name in ("capex_per_site", "opex_per_site", "benefit_per_site", "platform_capex", "months_to_value"):
            if getattr(ini, name).low < 0:
                raise CaseError(f"{ini.id}.{name} cannot be negative")
        if type(ini.committed_min_sites) is not int:
            raise CaseError(f"{ini.id}: committed_min_sites must be an integer")
        for name in ("ramp_years", "fte_per_site", "central_fte", "committed_min_sites"):
            finite(getattr(ini, name), f"{ini.id}.{name}", 0)
        for name in ("p_success", "fail_benefit_share"):
            finite(getattr(ini, name), f"{ini.id}.{name}", 0)
            if getattr(ini, name) > 1:
                raise CaseError(f"{ini.id}.{name} must be <= 1")
        unsupported = set(ini.ai_act) - set(QUESTIONS)
        if unsupported:
            raise CaseError(f"{ini.id}: unsupported governance questions: {sorted(map(str, unsupported))}")
        if any(v is not None and type(v) is not bool for v in ini.ai_act.values()):
            raise CaseError(f"{ini.id}: governance answers must be booleans or null")
        if ini.status in {"scale", "graduate"} and (not ini.sources or not ini.public_basis):
            raise CaseError(f"{ini.id}: public status requires sources and evidence")
        if ini.pilot_gate:
            threshold = ini.pilot_gate.get("min_success_probability")
            if threshold is None or not 0 <= threshold <= 1:
                raise CaseError(f"{ini.id}: pilot threshold must be in [0,1]")
            if type(ini.pilot_gate.get("approved")) is not bool:
                raise CaseError(f"{ini.id}: pilot approval must be explicit")
            if ini.pilot_gate["approved"] and not all(
                ini.pilot_gate.get(k) for k in ("reviewer", "evidence", "reviewed_at")
            ):
                raise CaseError(f"{ini.id}: pilot approval requires reviewer, evidence and date")
        if ini.pilot_gate.get("approved"):
            try:
                date.fromisoformat(ini.pilot_gate["reviewed_at"])
            except (ValueError, TypeError) as exc:
                raise CaseError(f"{ini.id}: pilot review date must be ISO format") from exc
        for r in ini.requires:
            if r.mode not in {"any", "sites"} or type(r.baseline_sites) is not int or r.baseline_sites < 0:
                raise CaseError(f"{ini.id}: invalid dependency")
            if r.initiative not in ids:
                raise CaseError(f"{ini.id}: unknown dependency {r.initiative}")
        for s in ini.sources:
            if s not in case.sources:
                raise CaseError(f"{ini.id}: source {s} not listed in case.yaml sources")
        if ini.committed_min_sites and ini.committed_min_sites not in ini.site_options:
            raise CaseError(f"{ini.id}: committed_min_sites must be one of site_options")
    for f in case.facts:
        if f.get("source") not in case.sources:
            raise CaseError(f"fact '{f.get('label')}' cites unknown source {f.get('source')}")

    visited, active = set(), set()

    def visit(iid):
        if iid in active:
            raise CaseError("cyclic initiative dependencies")
        if iid in visited:
            return
        active.add(iid)
        for dep in case.get(iid).requires:
            visit(dep.initiative)
        active.remove(iid)
        visited.add(iid)

    for iid in ids:
        visit(iid)
    for sid, source in case.sources.items():
        if not source.get("title") or not source.get("url", "").startswith("https://"):
            raise CaseError(f"{sid}: source needs title and HTTPS URL")
        try:
            date.fromisoformat(source["accessed"])
        except (KeyError, ValueError) as exc:
            raise CaseError(f"{sid}: accessed must be an ISO date") from exc


def load_case(folder: str | Path) -> Case:
    """Load trusted local YAML with consistent domain errors for malformed inputs."""
    try:
        return _load_case(folder)
    except CaseError:
        raise
    except (OSError, yaml.YAMLError, KeyError, TypeError, ValueError, AttributeError) as exc:
        raise CaseError(f"Could not load case: {exc}") from exc
