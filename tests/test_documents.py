"""Regression coverage for the professional Excel and PDF decision documents."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest
from openpyxl import load_workbook
from pypdf import PdfReader

from invest_engine import excel_analysis, investment_committee_pdf, load_case
from invest_engine.service import analyse

ROOT = Path(__file__).resolve().parents[1]
CASES = ("dhl_supply_chain", "allianz", "bmw_group")
SHEETS = [
    "Executive Summary",
    "Portfolio",
    "Financials",
    "Delivery Plan",
    "Scenarios",
    "Governance",
    "Assumptions",
    "Sources & Method",
]


def _analysis(case_id: str, **settings):
    return analyse(load_case(ROOT / "cases" / case_id), **settings)


def _workbook(data: bytes):
    return load_workbook(io.BytesIO(data), data_only=False)


def _pdf_text(data: bytes) -> tuple[PdfReader, str]:
    reader = PdfReader(io.BytesIO(data))
    return reader, "\n".join(page.extract_text() or "" for page in reader.pages)


def _cell_below(ws, label: str):
    for row in ws.iter_rows():
        for cell in row:
            if cell.value == label:
                return ws.cell(cell.row + 1, cell.column).value
    raise AssertionError(f"Missing workbook label: {label}")


def _xlsx_xml(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return "\n".join(
            archive.read(name).decode("utf-8", errors="ignore")
            for name in archive.namelist()
            if name.endswith((".xml", ".rels"))
        )


@pytest.mark.parametrize("case_id", CASES)
def test_default_documents_reconcile_with_current_analysis(case_id):
    a = _analysis(case_id)
    xlsx = excel_analysis(a)
    pdf = investment_committee_pdf(a)

    workbook = _workbook(xlsx)
    assert workbook.sheetnames == SHEETS
    summary = workbook["Executive Summary"]
    assert _cell_below(summary, "Expected NPV") == pytest.approx(a.portfolio.mean)
    assert _cell_below(summary, "Capital required") == pytest.approx(sum(a.portfolio.capex_by_year))
    assert _cell_below(summary, "Funded initiative types") == len(a.portfolio.funded)
    assert _cell_below(summary, "Scheduled deployments") == sum(a.portfolio.choice.values())

    financials = workbook["Financials"]
    reconciliation = [
        cell.value
        for row in financials.iter_rows()
        for cell in row
        if isinstance(cell.value, (int, float)) and cell.column == 5 and 10 <= cell.row <= 12
    ]
    assert reconciliation and max(abs(float(value)) for value in reconciliation) < 1e-6
    assert not any(cell.data_type == "f" for ws in workbook.worksheets for row in ws.iter_rows() for cell in row)

    reader, text = _pdf_text(pdf)
    assert 4 <= len(reader.pages) <= 12
    assert all(page.extract_text() for page in reader.pages)
    assert "Technology & AI Investment Strategy" in text
    assert a.case.company in text
    assert f"EUR {a.portfolio.mean / 1000:,.1f}m" in text
    assert "Illustrative model-based scenario" in text
    assert "Not an official company forecast" in text
    assert "Research proposals and uploaded documents are excluded" in text

    combined = _xlsx_xml(xlsx) + text
    assert "/Users/" not in combined
    assert "soham github" not in combined.lower()
    assert not re.search(r"(?:api[_-]?key|secret|token)\s*[=:]\s*['\"][^'\"]+", combined, re.I)


@pytest.mark.parametrize(
    ("case_id", "settings"),
    [
        ("dhl_supply_chain", {"discount": 0.12}),
        ("allianz", {"budget_scale": 0.75}),
        ("bmw_group", {"extra_delay_months": 3}),
    ],
)
def test_modified_scenario_documents_use_applied_results(case_id, settings):
    a = _analysis(case_id, **settings)
    workbook = _workbook(excel_analysis(a))
    summary = workbook["Executive Summary"]
    assert _cell_below(summary, "Expected NPV") == pytest.approx(a.portfolio.mean)
    assert _cell_below(summary, "Capital required") == pytest.approx(sum(a.portfolio.capex_by_year))
    scenario_inputs = workbook["Scenarios"]
    values = {row[1].value: row[2].value for row in scenario_inputs.iter_rows() if len(row) > 2}
    if "discount" in settings:
        assert values["Annual discount rate"] == settings["discount"]
    if "budget_scale" in settings:
        assert sum(a.case.budget_by_year) == pytest.approx(
            sum(load_case(ROOT / "cases" / case_id).budget_by_year) * settings["budget_scale"]
        )
    if "extra_delay_months" in settings:
        assert values["Deployment delay"] == load_case(ROOT / "cases" / case_id).deployment_delay_quarters + 1

    _, text = _pdf_text(investment_committee_pdf(a))
    assert f"EUR {a.portfolio.mean / 1000:,.1f}m" in text
    assert a.case.company in text


def test_zero_investment_documents_are_complete_and_truthful():
    a = _analysis("dhl_supply_chain", benefit_factor=0)
    assert sum(a.portfolio.choice.values()) == 0
    workbook = _workbook(excel_analysis(a))
    summary = workbook["Executive Summary"]
    assert _cell_below(summary, "Expected NPV") == pytest.approx(0)
    assert _cell_below(summary, "Scheduled deployments") == 0
    _, text = _pdf_text(investment_committee_pdf(a))
    assert "No funded initiatives" in text
    assert "EUR 0.0m" in text


def test_documents_are_deterministic_and_case_isolated():
    allianz = _analysis("allianz")
    assert excel_analysis(allianz) == excel_analysis(allianz)
    assert investment_committee_pdf(allianz) == investment_committee_pdf(allianz)

    xlsx_text = _xlsx_xml(excel_analysis(allianz))
    _, pdf_text = _pdf_text(investment_committee_pdf(allianz))
    combined = xlsx_text + pdf_text
    assert "Allianz" in combined
    assert "DHL Supply Chain" not in combined
    assert "BMW Group" not in combined
