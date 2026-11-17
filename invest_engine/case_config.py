"""Strict, presentation-only admission metadata for the three planned cases."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from .schema import CaseError

INDUSTRIES = {"logistics", "insurance", "automotive"}
CHARTS = {
    "contribution", "baseline_waterfall", "capital_frontier", "npv_distribution",
    "scenario_delta", "quarterly_rollout", "quarterly_capacity", "planned_benefits",
    "claims_kpi_scorecard", "service_kpi_scorecard", "function_value", "manufacturing_kpi_scorecard",
}
PAGE_CHARTS = {
    "portfolio": {"contribution", "baseline_waterfall", "claims_kpi_scorecard", "service_kpi_scorecard", "function_value", "manufacturing_kpi_scorecard"},
    "scenarios": {"capital_frontier", "npv_distribution", "scenario_delta"},
    "delivery": {"quarterly_rollout", "quarterly_capacity", "planned_benefits"},
}
KPI_UNITS = {"hours", "days", "minutes", "EUR/claim", "EUR/vehicle", "kWh/vehicle", "percent_0_100", "count"}
GOVERNANCE_PROFILES = {"workplace_v1", "insurance_operations_v1", "manufacturing_operations_v1"}
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _fields(value, required, optional=(), label="record"):
    if not isinstance(value, dict):
        raise CaseError(f"{label} must be a mapping")
    missing = set(required) - set(value)
    extra = set(value) - set(required) - set(optional)
    if missing or extra:
        raise CaseError(f"{label}: missing {sorted(missing)}; unsupported {sorted(extra)}")


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise CaseError(f"{label} must be nonempty text")
    return value.strip()


def _string_list(value, label, *, nonempty=True):
    if not isinstance(value, list) or (nonempty and not value):
        raise CaseError(f"{label} must be a list")
    items = [_text(item, label) for item in value]
    if len(items) != len(set(items)):
        raise CaseError(f"{label} has duplicates")
    return items


@dataclass(frozen=True)
class Profile:
    schema_version: int
    case_id: str
    industry_id: str
    scope: dict
    as_of: str
    deployment_unit: dict
    accent: dict
    kpis: list[dict]
    governance: dict
    views: dict
    decision_notes: dict
    evidence: dict


def load_profile(folder: str | Path, case) -> Profile:
    """Validate metadata and evidence before a case can enter the selector."""
    folder = Path(folder)
    try:
        raw = yaml.safe_load((folder / "profile.yaml").read_text(encoding="utf-8"))
        evidence = yaml.safe_load((folder / "evidence.yaml").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CaseError(f"Could not load case profile/evidence: {exc}") from exc
    _validate_economic_fields(folder)
    _fields(raw, {"schema_version", "case_id", "industry_id", "scope", "as_of", "deployment_unit", "accent", "kpis", "governance", "views", "decision_notes"}, label="profile")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise CaseError("unsupported profile schema_version")
    if raw["case_id"] != case.id:
        raise CaseError("profile case_id does not match case.yaml")
    if raw["industry_id"] not in INDUSTRIES:
        raise CaseError("unsupported industry_id")
    try:
        date.fromisoformat(_text(raw["as_of"], "as_of"))
    except ValueError as exc:
        raise CaseError("as_of must be an ISO date") from exc
    scope = raw["scope"]
    _fields(scope, {"company", "operating_unit", "geography", "process", "beneficiary", "exclusions"}, label="scope")
    for key in ("company", "operating_unit", "geography", "process", "beneficiary"):
        _text(scope[key], f"scope.{key}")
    _string_list(scope["exclusions"], "scope.exclusions")
    if scope["company"] != case.company:
        raise CaseError("profile scope company does not match case")
    unit = raw["deployment_unit"]
    _fields(unit, {"singular", "plural", "definition", "coverage_noun"}, label="deployment_unit")
    for key in unit:
        _text(unit[key], f"deployment_unit.{key}")
    accent = raw["accent"]
    _fields(accent, {"primary", "support"}, label="accent")
    if any(not isinstance(v, str) or not HEX.fullmatch(v) for v in accent.values()):
        raise CaseError("accent colors must be six-digit hex values")
    governance = raw["governance"]
    _fields(governance, {"profile_id", "profile_version", "coverage_review", "domains", "approval_points"}, label="governance")
    if governance["profile_id"] not in GOVERNANCE_PROFILES or type(governance["profile_version"]) is not int or governance["profile_version"] != 1:
        raise CaseError("unsupported governance profile/version")
    if governance["coverage_review"] != "design_reviewed":
        raise CaseError("governance coverage must be design-reviewed before admission")
    _string_list(governance["domains"], "governance.domains")
    _string_list(governance["approval_points"], "governance.approval_points")
    if raw["industry_id"] == "insurance":
        if governance["profile_id"] != "insurance_operations_v1":
            raise CaseError("insurance requires the insurance operations governance profile")
        if not {"human_claim_decision", "privacy", "model_risk", "consumer_fairness", "ict_resilience"}.issubset(set(governance["domains"])):
            raise CaseError("insurance governance domains are incomplete")
        if not any("life/health pricing" in item.lower() for item in scope["exclusions"]):
            raise CaseError("insurance case must exclude unsupported life/health pricing")
    elif raw["industry_id"] == "automotive":
        if governance["profile_id"] != "manufacturing_operations_v1":
            raise CaseError("automotive requires the manufacturing operations governance profile")
        if not {"machine_safety", "quality", "workplace", "privacy", "human_oversight", "cybersecurity"}.issubset(set(governance["domains"])):
            raise CaseError("automotive governance domains are incomplete")
    elif governance["profile_id"] != "workplace_v1":
        raise CaseError("incompatible industry governance profile")
    views = raw["views"]
    _fields(views, {"portfolio", "scenarios", "delivery"}, label="views")
    for key, values in views.items():
        if set(_string_list(values, f"views.{key}")) - PAGE_CHARTS[key]:
            raise CaseError(f"views.{key} contains unsupported chart IDs")
    _fields(evidence, {"schema_version", "claims", "assumptions"}, label="evidence")
    if type(evidence["schema_version"]) is not int or evidence["schema_version"] != 1:
        raise CaseError("unsupported evidence schema_version")
    claims = evidence["claims"]
    if not isinstance(claims, list) or not claims:
        raise CaseError("evidence claims must be nonempty")
    claim_ids = set()
    for claim in claims:
        _fields(claim, {"id", "text", "source_ids"}, label="evidence claim")
        iid = _text(claim["id"], "claim.id")
        if iid in claim_ids:
            raise CaseError("duplicate evidence claim id")
        claim_ids.add(iid)
        _text(claim["text"], "claim.text")
        if set(_string_list(claim["source_ids"], "claim.source_ids")) - set(case.sources):
            raise CaseError("evidence claim cites unknown source")
    assumptions = evidence["assumptions"]
    if not isinstance(assumptions, list) or not assumptions:
        raise CaseError("evidence assumptions must be nonempty")
    assumption_ids = set()
    for item in assumptions:
        _fields(item, {"id", "rationale", "owner", "status"}, label="evidence assumption")
        for key in ("id", "rationale", "owner"):
            _text(item[key], f"assumption.{key}")
        if item["id"] in assumption_ids:
            raise CaseError("duplicate evidence assumption id")
        assumption_ids.add(item["id"])
        if item["status"] not in {"hypothetical", "owner_reviewed"}:
            raise CaseError("unsupported assumption status")
    kpis = raw["kpis"]
    if not isinstance(kpis, list) or not kpis:
        raise CaseError("profile kpis must be nonempty")
    kpi_ids = set()
    for kpi in kpis:
        _fields(kpi, {"id", "initiative_ids", "label", "unit", "direction", "frequency", "aggregation", "provenance", "source_ids", "owner", "baseline", "target"}, {"numerator", "denominator", "weight"}, label="kpi")
        iid = _text(kpi["id"], "kpi.id")
        if iid in kpi_ids:
            raise CaseError("duplicate KPI id")
        kpi_ids.add(iid)
        _text(kpi["label"], "kpi.label")
        _text(kpi["owner"], "kpi.owner")
        if kpi["unit"] not in KPI_UNITS or kpi["direction"] not in {"higher", "lower", "target_range"}:
            raise CaseError("unsupported KPI unit/direction")
        if kpi["frequency"] not in {"weekly", "monthly", "quarterly"} or kpi["aggregation"] not in {"mean", "mean_weighted_by_claims", "mean_weighted_by_contacts", "ratio_of_totals", "sum"}:
            raise CaseError("unsupported KPI frequency/aggregation")
        if kpi["aggregation"] == "ratio_of_totals":
            _text(kpi.get("numerator"), "kpi.numerator")
            _text(kpi.get("denominator"), "kpi.denominator")
        if kpi["aggregation"].startswith("mean_weighted_by_"):
            expected = "claim_count" if kpi["aggregation"].endswith("claims") else "contact_count"
            if kpi.get("weight") != expected:
                raise CaseError(f"weighted KPI requires {expected} weight")
        if kpi["provenance"] not in {"reported_fact", "hypothetical_assumption", "simulated", "user_reported"}:
            raise CaseError("unsupported KPI provenance")
        if kpi["baseline"] is not None or kpi["target"] is not None:
            raise CaseError("observed KPI baselines/targets need a separately validated measurement source")
        if set(_string_list(kpi["initiative_ids"], "kpi.initiative_ids")) - {i.id for i in case.initiatives}:
            raise CaseError("KPI references unknown initiative")
        if set(_string_list(kpi["source_ids"], "kpi.source_ids", nonempty=False)) - set(case.sources):
            raise CaseError("KPI references unknown source")
    notes = raw["decision_notes"]
    _fields(notes, {"rationale", "risks", "approval_points", "source_ids"}, label="decision_notes")
    _text(notes["rationale"], "decision_notes.rationale")
    _string_list(notes["risks"], "decision_notes.risks")
    _string_list(notes["approval_points"], "decision_notes.approval_points")
    if set(_string_list(notes["source_ids"], "decision_notes.source_ids")) - set(case.sources):
        raise CaseError("decision notes cite unknown source")
    return Profile(**raw, evidence=evidence)


def _validate_economic_fields(folder: Path) -> None:
    """Fail admission on ignored economic fields or unsupported constraints."""
    try:
        case = yaml.safe_load((folder / "case.yaml").read_text(encoding="utf-8"))
        initiatives = yaml.safe_load((folder / "initiatives.yaml").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CaseError(f"Could not inspect economic fields: {exc}") from exc
    _fields(case, {"id", "company", "title", "question", "disclaimer", "model", "compliance", "facts", "sources"}, {"unit"}, "case.yaml")
    _fields(case["model"], {"currency_unit", "horizon_years", "rollout_years", "discount_rate", "budget_by_year", "fte_capacity_by_year", "risk_aversion", "volume_factor", "n_samples", "seed", "max_sites_per_quarter"}, {"deployment_delay_quarters"}, "model")
    _fields(case["compliance"], {"high_risk_capex", "high_risk_delay_months", "product_route_capex", "transparency_capex", "works_council_delay_months"}, label="compliance")
    _fields(initiatives, {"defaults", "initiatives"}, label="initiatives.yaml")
    allowed = {"id", "name", "function", "status", "description", "public_basis", "sources", "site_options", "capex_per_site", "opex_per_site", "benefit_per_site", "platform_capex", "months_to_value", "ramp_years", "p_success", "fail_benefit_share", "fte_per_site", "central_fte", "kpi", "ai_act", "requires", "committed_min_sites", "assumption_notes", "library_ref", "exclusive_group", "pilot_gate"}
    _fields(initiatives["defaults"], (), allowed, "initiative defaults")
    for item in initiatives["initiatives"]:
        _fields(item, {"id", "name", "function", "status", "description", "sources", "site_options", "capex_per_site", "opex_per_site", "benefit_per_site", "months_to_value", "p_success", "fte_per_site", "central_fte", "kpi"}, allowed, "initiative")
        for dep in item.get("requires", []):
            _fields(dep, {"initiative", "mode"}, {"baseline_sites"}, "dependency")
        if item.get("pilot_gate"):
            _fields(item["pilot_gate"], {"approved", "min_success_probability", "evidence"}, {"reviewer", "reviewed_at"}, "pilot gate")


def admitted_cases(root: Path) -> list[Path]:
    """Only complete, validated business cases appear in the application selector."""
    path = root / "cases" / "catalog.yaml"
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CaseError(f"Could not load case catalog: {exc}") from exc
    _fields(raw, {"schema_version", "cases"}, label="catalog")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise CaseError("unsupported catalog schema_version")
    entries = raw["cases"]
    if not isinstance(entries, list) or len(entries) != 3:
        raise CaseError("catalog must declare exactly three business cases")
    expected = {"dhl_supply_chain", "allianz", "bmw_group"}
    found, admitted = set(), []
    for entry in entries:
        _fields(entry, {"id", "folder", "industry_id", "admission", "business_review"}, label="catalog entry")
        cid = _text(entry["id"], "catalog.id")
        folder = _text(entry["folder"], "catalog.folder")
        if cid in found or cid not in expected or folder != cid or Path(folder).name != folder:
            raise CaseError("catalog has duplicate/unsupported case or invalid folder")
        found.add(cid)
        if entry["industry_id"] not in INDUSTRIES or entry["admission"] not in {"planned", "validating", "implemented"} or entry["business_review"] not in {"pending", "reviewed"}:
            raise CaseError("invalid catalog industry/admission/review state")
        if entry["admission"] == "implemented":
            from .schema import load_case

            candidate = root / "cases" / folder
            case = load_case(candidate)
            if case.id != cid or case.profile is None or case.profile.industry_id != entry["industry_id"]:
                raise CaseError("catalog entry does not match validated case/profile")
            admitted.append(candidate)
    if found != expected:
        raise CaseError("catalog must declare DHL Supply Chain, Allianz and BMW Group")
    return admitted


def case_fingerprint(folder: str | Path, calculation_version: str) -> str:
    """Bind scenarios, reviews and cached reports to all admitted case inputs."""
    folder = Path(folder)
    files = ["case.yaml", "initiatives.yaml"]
    if (folder / "profile.yaml").exists() or (folder / "evidence.yaml").exists():
        files += ["profile.yaml", "evidence.yaml"]
    digest = hashlib.sha256(calculation_version.encode())
    try:
        for name in files:
            digest.update((folder / name).read_bytes())
    except OSError as exc:
        raise CaseError(f"Could not fingerprint case: {exc}") from exc
    return digest.hexdigest()
