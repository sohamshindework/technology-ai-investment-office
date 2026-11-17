"""Professional in-memory XLSX and PDF exports from the current Analysis.

The financial engine remains the only calculation source. These functions format
the current analysis and add independent reconciliation displays; they do not
recalculate investment economics or read research-upload state.
"""

from __future__ import annotations

import io
import math
import re
from datetime import datetime, timezone
from html import escape

import pandas as pd
import xlsxwriter
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from .benefits import initiative_summary, portfolio_summary
from .branding import PROJECT_TITLE, SUBTITLE
from .reporting import settings, tables

MAX_EXPORT_INITIATIVES = 100
MAX_EXPORT_QUARTERS = 80
MAX_EXPORT_BYTES = 20_000_000

IVORY = "#F7F8F5"
WHITE = "#FFFFFF"
INK = "#24332F"
MUTED = "#66736F"
TEAL = "#276E65"
TEAL_DARK = "#1E544D"
TEAL_PALE = "#E8F1EE"
AMBER = "#B1792B"
AMBER_PALE = "#F8EFD9"
RED = "#A94442"
RED_PALE = "#F8E4E2"
GRID = "#D8DEDA"


class ExportError(ValueError):
    """Raised when an analysis cannot be exported safely."""


def _clean(value) -> str:
    text = str(value or "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _pdf_text(value) -> str:
    return (
        _clean(value)
        .replace("—", "-")
        .replace("–", "-")
        .replace("·", " | ")
        .replace("€", "EUR ")
        .replace("−", "-")
    )


def _money(value: float, decimals: int = 1) -> str:
    return f"EUR {value / 1000:,.{decimals}f}m"


def _validate(a) -> None:
    c = a.case
    if len(c.initiatives) > MAX_EXPORT_INITIATIVES:
        raise ExportError(f"Exports support at most {MAX_EXPORT_INITIATIVES} initiatives.")
    if c.horizon_years * 4 > MAX_EXPORT_QUARTERS:
        raise ExportError(f"Exports support at most {MAX_EXPORT_QUARTERS} quarters.")
    if c.path is not None:
        raise ExportError("The export analysis must not retain a local case path.")
    for value in (a.portfolio.mean, *a.portfolio.capex_by_year):
        if not math.isfinite(float(value)):
            raise ExportError("The analysis contains a non-finite portfolio result.")


def _benefits_total(a) -> float:
    return float(sum(a.valuations[iid][sites].benefit_by_year.sum() for iid, sites in a.portfolio.choice.items()))


def _last_quarter(a) -> int:
    return max((row.quarter for row in a.roadmap if row.sites), default=0)


def _decision(a, initiative) -> str:
    if a.portfolio.choice[initiative.id] > 0:
        return "Funded"
    if a.screenings[initiative.id].excluded:
        return "Excluded pending governance review"
    if initiative.pilot_gate:
        return "Pilot or defer"
    return "Deferred"


def _dependencies(a, initiative) -> str:
    if not initiative.requires:
        return "None declared"
    parts = []
    for item in initiative.requires:
        name = a.case.get(item.initiative).name
        if item.mode == "sites":
            parts.append(f"{name}; earlier-quarter coverage; baseline {item.baseline_sites}")
        else:
            parts.append(f"{name}; earlier-quarter enablement")
    return " | ".join(parts)


def _initiative_rows(a) -> list[dict]:
    rows = []
    for initiative in a.case.initiatives:
        sites = a.portfolio.choice[initiative.id]
        option = a.valuations[initiative.id][sites]
        rows.append(
            {
                "Initiative ID": initiative.id,
                "Initiative": initiative.name,
                "Function": initiative.function,
                "Public status": initiative.status,
                "Decision": _decision(a, initiative),
                "Selected deployments": sites,
                "Expected NPV (EUR k)": option.mean,
                "P10 NPV (EUR k)": option.pct(10),
                "P90 NPV (EUR k)": option.pct(90),
                "Capex (EUR k)": float(option.capex_by_year.sum()),
                "Loss probability": option.p_loss,
                "Governance category": a.screenings[initiative.id].category,
                "Dependencies": _dependencies(a, initiative),
                "Rationale": initiative.description,
            }
        )
    return rows


def _quarterly_capacity(a) -> pd.DataFrame:
    c = a.case
    cash = (
        tables(a)["quarterly_cash_flows"]
        .groupby("quarter", as_index=False)
        .sum(numeric_only=True)
        .drop(columns=["deployments_completed", "gate", "fte_years"])
    )
    roadmap = pd.DataFrame(
        [
            {
                "quarter": row.quarter,
                "deployments": row.sites,
                "fte": row.fte_used,
                "gate": int(row.activity == "gate"),
            }
            for row in a.roadmap
        ]
    )
    if roadmap.empty:
        roadmap = pd.DataFrame(columns=["quarter", "deployments", "fte", "gate"])
    use = roadmap.groupby("quarter", as_index=False).sum(numeric_only=True)
    for column in ("deployments", "fte", "gate"):
        if column not in use:
            use[column] = 0.0
    result = pd.DataFrame({"Quarter": range(1, c.rollout_years * 4 + 1)})
    result = result.merge(use, left_on="Quarter", right_on="quarter", how="left").drop(columns="quarter")
    result = result.merge(cash, left_on="Quarter", right_on="quarter", how="left").drop(columns="quarter")
    result = result.fillna(0)
    result["Deployment limit"] = c.max_sites_per_quarter
    result["Deployment utilization"] = result.deployments / result["Deployment limit"]
    result["FTE-years limit"] = result.Quarter.map(lambda q: c.fte_capacity_by_year[(q - 1) // 4] / 4)
    result["FTE utilization"] = result.fte / result["FTE-years limit"]
    return result.rename(
        columns={
            "deployments": "Deployments",
            "fte": "FTE-years required",
            "gate": "Review gates",
            "benefit_EUR_k": "Benefits (EUR k)",
            "capex_EUR_k": "Capex (EUR k)",
            "opex_EUR_k": "Operating costs (EUR k)",
            "net_cash_EUR_k": "Net cash (EUR k)",
            "discounted_cash_EUR_k": "Discounted cash (EUR k)",
        }
    )


def _xlsx_formats(workbook, case_accent: str) -> dict:
    return {
        "title": workbook.add_format({"font_name": "Arial", "font_size": 16, "bold": True, "font_color": INK}),
        "subtitle": workbook.add_format({"font_name": "Arial", "font_size": 10, "font_color": MUTED}),
        "case": workbook.add_format({"font_name": "Arial", "font_size": 11, "bold": True, "font_color": case_accent}),
        "note": workbook.add_format({"font_name": "Arial", "font_size": 9, "italic": True, "font_color": MUTED}),
        "section": workbook.add_format(
            {"font_name": "Arial", "font_size": 11, "bold": True, "font_color": WHITE, "bg_color": TEAL_DARK, "align": "left", "valign": "vcenter"}
        ),
        "header": workbook.add_format(
            {"font_name": "Arial", "font_size": 9, "bold": True, "font_color": WHITE, "bg_color": TEAL, "align": "center", "valign": "vcenter", "text_wrap": True, "border": 1, "border_color": WHITE}
        ),
        "body": workbook.add_format({"font_name": "Arial", "font_size": 9, "font_color": INK, "valign": "top"}),
        "body_wrap": workbook.add_format({"font_name": "Arial", "font_size": 9, "font_color": INK, "valign": "top", "text_wrap": True}),
        "integer": workbook.add_format({"font_name": "Arial", "font_size": 9, "font_color": INK, "num_format": "#,##0", "valign": "top"}),
        "decimal": workbook.add_format({"font_name": "Arial", "font_size": 9, "font_color": INK, "num_format": "#,##0.00", "valign": "top"}),
        "money": workbook.add_format({"font_name": "Arial", "font_size": 9, "font_color": INK, "num_format": '€#,##0.0;[Red](€#,##0.0);-'}),
        "percent": workbook.add_format({"font_name": "Arial", "font_size": 9, "italic": True, "font_color": INK, "num_format": "0.0%"}),
        "input": workbook.add_format({"font_name": "Arial", "font_size": 9, "font_color": "#1F4E79", "bg_color": AMBER_PALE, "valign": "top"}),
        "input_number": workbook.add_format({"font_name": "Arial", "font_size": 9, "font_color": "#1F4E79", "bg_color": AMBER_PALE, "num_format": "#,##0.00"}),
        "calculated": workbook.add_format({"font_name": "Arial", "font_size": 9, "font_color": INK, "bg_color": TEAL_PALE, "valign": "top"}),
        "calculated_money": workbook.add_format({"font_name": "Arial", "font_size": 9, "font_color": INK, "bg_color": TEAL_PALE, "num_format": '€#,##0.0;[Red](€#,##0.0);-'}),
        "metric_label": workbook.add_format({"font_name": "Arial", "font_size": 9, "bold": True, "font_color": MUTED, "bg_color": IVORY, "align": "center"}),
        "metric_money": workbook.add_format({"font_name": "Arial", "font_size": 14, "bold": True, "font_color": TEAL_DARK, "bg_color": IVORY, "align": "center", "num_format": '€0.0, "m";[Red](€0.0, "m");-'}),
        "metric_number": workbook.add_format({"font_name": "Arial", "font_size": 14, "bold": True, "font_color": TEAL_DARK, "bg_color": IVORY, "align": "center", "num_format": "#,##0"}),
        "metric_percent": workbook.add_format({"font_name": "Arial", "font_size": 14, "bold": True, "font_color": TEAL_DARK, "bg_color": IVORY, "align": "center", "num_format": "0.0%"}),
        "check": workbook.add_format({"font_name": "Arial", "font_size": 9, "font_color": INK, "num_format": "0.00"}),
        "risk": workbook.add_format({"font_name": "Arial", "font_size": 9, "font_color": RED, "bg_color": RED_PALE, "text_wrap": True}),
        "source": workbook.add_format({"font_name": "Arial", "font_size": 9, "font_color": "#0563C1", "underline": True, "valign": "top", "text_wrap": True}),
    }


def _setup_sheet(ws, landscape: bool = True) -> None:
    ws.hide_gridlines(2)
    ws.set_margins(0.35, 0.35, 0.55, 0.55)
    ws.set_header("&LTechnology & AI Investment Strategy")
    ws.set_footer("&LIllustrative model-based scenario&RPage &P of &N")
    ws.set_landscape() if landscape else ws.set_portrait()
    ws.set_paper(9)
    ws.fit_to_pages(1, 0)
    ws.set_column(0, 0, 2.5)


def _sheet_title(ws, formats, case, title: str) -> int:
    ws.set_row(1, 22)
    ws.write(1, 1, title, formats["title"])
    ws.write(2, 1, SUBTITLE, formats["subtitle"])
    ws.write(3, 1, case.title, formats["case"])
    ws.write(4, 1, "Illustrative model-based scenario. Not an official company forecast.", formats["note"])
    return 6


def _section(ws, formats, row: int, title: str, end_col: int = 8) -> int:
    ws.merge_range(row, 1, row, end_col, title, formats["section"])
    ws.set_row(row, 20)
    return row + 2


def _excel_value(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, (list, tuple, dict)):
        return _clean(value)
    if hasattr(value, "item"):
        return value.item()
    return value


def _write_table(ws, formats, row: int, col: int, frame: pd.DataFrame, *, widths=None, assumptions=False) -> int:
    if frame.empty:
        ws.write(row, col, "No records for the current analysis.", formats["note"])
        return row + 2
    columns = [str(name) for name in frame.columns]
    for offset, name in enumerate(columns):
        ws.write(row, col + offset, name, formats["header"])
    ws.set_row(row, 30)
    for r_index, values in enumerate(frame.itertuples(index=False, name=None), start=row + 1):
        max_len = 0
        for c_index, (name, value) in enumerate(zip(columns, values, strict=True), start=col):
            value = _excel_value(value)
            max_len = max(max_len, len(str(value or "")))
            target = formats["input"] if assumptions else formats["body"]
            if isinstance(value, bool):
                ws.write_boolean(r_index, c_index, value, target)
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                if "probability" in name.lower() or "utilization" in name.lower() or "rate" in name.lower() or "share" in name.lower():
                    target = formats["percent"] if not assumptions else formats["input_number"]
                elif "EUR k" in name or name in {"Expected NPV", "P10 NPV", "P90 NPV", "Capex", "Benefits"}:
                    target = formats["money"] if not assumptions else formats["input_number"]
                elif isinstance(value, int) or float(value).is_integer():
                    target = formats["integer"] if not assumptions else formats["input_number"]
                else:
                    target = formats["decimal"] if not assumptions else formats["input_number"]
                ws.write_number(r_index, c_index, float(value), target)
            else:
                text = _clean(value)
                target = formats["input"] if assumptions else (formats["body_wrap"] if len(text) > 45 else formats["body"])
                ws.write_string(r_index, c_index, text, target)
        if max_len > 80:
            ws.set_row(r_index, 36)
        elif max_len > 45:
            ws.set_row(r_index, 28)
    if widths:
        for offset, width in enumerate(widths):
            ws.set_column(col + offset, col + offset, width)
    else:
        for offset, name in enumerate(columns):
            values = frame.iloc[:, offset].astype(str).map(len) if len(frame) else pd.Series(dtype=int)
            width = max(len(name) + 2, int(values.max()) + 2 if not values.empty else 10)
            ws.set_column(col + offset, col + offset, min(max(width, 10), 36))
    return row + len(frame) + 3


def _populate_portfolio(ws, formats, a) -> None:
    _setup_sheet(ws)
    row = _sheet_title(ws, formats, a.case, "Portfolio recommendation")
    row = _section(ws, formats, row, "Selected and excluded initiatives", 14)
    frame = pd.DataFrame(_initiative_rows(a))
    _write_table(
        ws,
        formats,
        row,
        1,
        frame,
        widths=[13, 34, 18, 12, 25, 13, 15, 15, 15, 14, 13, 20, 33, 48],
    )
    ws.freeze_panes(row + 1, 2)
    ws.autofilter(row, 1, row + len(frame), 14)
    ws.repeat_rows(row, row)
    ws.print_area(1, 1, row + len(frame), 14)


def _populate_executive(workbook, ws, formats, a) -> None:
    _setup_sheet(ws)
    ws.set_column(1, 1, 28)
    ws.set_column(2, 2, 16)
    ws.set_column(3, 3, 3)
    ws.set_column(4, 4, 28)
    ws.set_column(5, 5, 16)
    ws.set_column(6, 10, 14)
    row = _sheet_title(ws, formats, a.case, PROJECT_TITLE)
    labels = ["Expected NPV", "Capital required", "Funded initiative types", "Scheduled deployments"]
    values = [a.portfolio.mean, float(a.portfolio.capex_by_year.sum()), len(a.portfolio.funded), sum(a.portfolio.funded.values())]
    fmts = [formats["metric_money"], formats["metric_money"], formats["metric_number"], formats["metric_number"]]
    for index, (label, value, fmt) in enumerate(zip(labels, values, fmts, strict=True)):
        col = 1 + index * 2
        ws.write(row, col, label, formats["metric_label"])
        ws.write_number(row + 1, col, value, fmt)
        ws.set_column(col, col, 22)
    row += 4
    risk_labels = ["P10 NPV", "P90 NPV", "Loss probability", "Last deployment quarter"]
    risk_values = [a.portfolio.pct(10), a.portfolio.pct(90), a.portfolio.p_loss, _last_quarter(a)]
    risk_fmts = [formats["metric_money"], formats["metric_money"], formats["metric_percent"], formats["metric_number"]]
    for index, (label, value, fmt) in enumerate(zip(risk_labels, risk_values, risk_fmts, strict=True)):
        col = 1 + index * 2
        ws.write(row, col, label, formats["metric_label"])
        ws.write_number(row + 1, col, value, fmt)
    row += 4
    row = _section(ws, formats, row, "Recommended portfolio", 10)
    funded = []
    for initiative in a.case.initiatives:
        sites = a.portfolio.choice[initiative.id]
        if sites:
            funded.append(
                {
                    "Initiative": initiative.name,
                    "Deployments": sites,
                    "Expected NPV (EUR k)": a.valuations[initiative.id][sites].mean,
                    "Rationale": initiative.description,
                }
            )
    start = row
    row = _write_table(ws, formats, row, 1, pd.DataFrame(funded), widths=[35, 14, 18, 52])
    if funded:
        chart = workbook.add_chart({"type": "bar"})
        chart.add_series(
            {
                "name": "Expected NPV (EUR k)",
                "categories": [ws.name, start + 1, 1, start + len(funded), 1],
                "values": [ws.name, start + 1, 3, start + len(funded), 3],
                "fill": {"color": TEAL},
                "border": {"none": True},
            }
        )
        chart.set_title({"name": "Expected value by funded initiative"})
        chart.set_legend({"none": True})
        chart.set_x_axis({"name": "EUR k", "major_gridlines": {"visible": False}})
        chart.set_y_axis({"major_gridlines": {"visible": False}})
        chart.set_style(10)
        chart.set_size({"width": 500, "height": 250})
        ws.insert_chart(start, 6, chart)
    row = max(row, start + 15)
    row = _section(ws, formats, row, "Decision conditions", 10)
    conditions = [
        ["Portfolio status", a.portfolio.status],
        ["Capital envelope", _money(sum(a.case.budget_by_year))],
        ["Implementation deadline", f"{a.case.rollout_years * 12} months"],
        ["Undiscounted benefits", _money(_benefits_total(a))],
        ["Optimization boundary", "Discrete rollout scales with fixed quarterly phasing"],
    ]
    for offset, pair in enumerate(conditions):
        ws.write(row + offset, 1, pair[0], formats["metric_label"])
        ws.write(row + offset, 2, pair[1], formats["calculated"])
    if a.case.profile:
        approval_row = row
        ws.write(approval_row, 4, "Approvals and validation required", formats["metric_label"])
        for offset, item in enumerate(a.case.profile.decision_notes["approval_points"], start=1):
            ws.write(approval_row + offset, 4, _clean(item), formats["body_wrap"])
        ws.set_column(4, 4, 48)
    ws.print_area(1, 1, row + max(8, len(conditions)), 10)


def _populate_financials(ws, formats, a) -> None:
    _setup_sheet(ws)
    row = _sheet_title(ws, formats, a.case, "Financial outlook and cash flows")
    row = _section(ws, formats, row, "Portfolio reconciliation", 8)
    frame = tables(a)
    annual = frame["cash_flows"].groupby("year", as_index=False).sum(numeric_only=True)
    discounted = float(annual.discounted_cash_EUR_k.sum())
    checks = pd.DataFrame(
        [
            ["Expected NPV", a.portfolio.mean, discounted, discounted - a.portfolio.mean],
            ["Capital required", float(a.portfolio.capex_by_year.sum()), float(annual.capex_EUR_k.sum()), float(annual.capex_EUR_k.sum() - a.portfolio.capex_by_year.sum())],
            ["Undiscounted benefits", _benefits_total(a), float(annual.benefit_EUR_k.sum()), float(annual.benefit_EUR_k.sum() - _benefits_total(a))],
        ],
        columns=["Measure", "Engine result (EUR k)", "Schedule result (EUR k)", "Difference (EUR k)"],
    )
    row = _write_table(ws, formats, row, 1, checks, widths=[26, 20, 22, 18])
    row = _section(ws, formats, row, "Annual cash-flow schedule", 8)
    annual = annual.rename(
        columns={
            "year": "Year",
            "benefit_EUR_k": "Benefits (EUR k)",
            "capex_EUR_k": "Capex (EUR k)",
            "opex_EUR_k": "Operating costs (EUR k)",
            "net_cash_EUR_k": "Net cash (EUR k)",
            "discounted_cash_EUR_k": "Discounted cash (EUR k)",
        }
    )
    row = _write_table(ws, formats, row, 1, annual, widths=[10, 18, 18, 22, 18, 22])
    row = _section(ws, formats, row, "Quarterly cash-flow schedule", 9)
    quarterly = frame["quarterly_cash_flows"].groupby("quarter", as_index=False).sum(numeric_only=True)
    quarterly = quarterly.rename(
        columns={
            "quarter": "Quarter",
            "deployments_completed": "Deployments",
            "fte_years": "FTE-years",
            "benefit_EUR_k": "Benefits (EUR k)",
            "capex_EUR_k": "Capex (EUR k)",
            "opex_EUR_k": "Operating costs (EUR k)",
            "net_cash_EUR_k": "Net cash (EUR k)",
            "discounted_cash_EUR_k": "Discounted cash (EUR k)",
        }
    ).drop(columns=["gate"], errors="ignore")
    _write_table(ws, formats, row, 1, quarterly, widths=[10, 13, 13, 18, 18, 21, 18, 22])
    ws.freeze_panes(row + 1, 2)


def _populate_delivery(workbook, ws, formats, a) -> None:
    _setup_sheet(ws)
    row = _sheet_title(ws, formats, a.case, "Quarterly implementation plan")
    row = _section(ws, formats, row, "Capacity and financial schedule", 16)
    capacity = _quarterly_capacity(a)
    table_row = row
    row = _write_table(ws, formats, row, 1, capacity, widths=[10, 13, 13, 15, 16, 16, 15, 13, 18, 18, 21, 18, 22])
    chart = workbook.add_chart({"type": "column"})
    chart.add_series(
        {
            "name": "Deployments",
            "categories": [ws.name, table_row + 1, 1, table_row + len(capacity), 1],
            "values": [ws.name, table_row + 1, 2, table_row + len(capacity), 2],
            "fill": {"color": TEAL},
            "border": {"none": True},
        }
    )
    chart.add_series(
        {
            "name": "Deployment limit",
            "categories": [ws.name, table_row + 1, 1, table_row + len(capacity), 1],
            "values": [ws.name, table_row + 1, 10, table_row + len(capacity), 10],
            "type": "line",
            "line": {"color": AMBER, "dash_type": "dash", "width": 2},
        }
    )
    chart.set_title({"name": "Quarterly deployments and limit"})
    chart.set_x_axis({"name": "Quarter"})
    chart.set_y_axis({"name": "Deployments", "min": 0})
    chart.set_legend({"position": "top"})
    chart.set_size({"width": 560, "height": 280})
    ws.insert_chart(table_row, 15, chart)
    row = _section(ws, formats, row, "Implementation activities", 8)
    roadmap = pd.DataFrame(
        [
            {
                "Quarter": item.quarter,
                "Initiative": a.case.get(item.initiative_id).name,
                "Activity": item.activity.title(),
                "Deployments": item.sites,
                "Cumulative deployments": item.cumulative_sites,
                "FTE-years": item.fte_used,
            }
            for item in a.roadmap
        ]
    )
    row = _write_table(ws, formats, row, 1, roadmap, widths=[10, 38, 16, 14, 20, 14])
    ws.set_h_pagebreaks([row])
    row = _section(ws, formats, row, "Benefits realization", 13)
    summary = portfolio_summary(a.benefits)
    if summary["observed"] is None:
        ws.write(row, 1, "Observed benefits", formats["metric_label"])
        ws.write(row, 2, "Unavailable", formats["calculated"])
        ws.write(
            row + 1,
            1,
            "No validated observations are active. Missing periods are not treated as zero and do not affect valuation.",
            formats["note"],
        )
        row += 4
    else:
        review = pd.DataFrame(
            [
                ["Reporting period", f"Through Q{summary['reporting_quarter']}"],
                ["Planned for observed periods (EUR k)", summary["planned"]],
                ["Observed benefits (EUR k)", summary["observed"]],
                ["Variance (EUR k)", summary["variance"]],
                ["Observation coverage", summary["coverage"]],
                ["Material follow-up items", summary["material_count"]],
            ],
            columns=["Measure", "Current result"],
        )
        row = _write_table(ws, formats, row, 1, review, widths=[34, 24])
        detail = initiative_summary(a.benefits).assign(
            Initiative=lambda frame: frame.initiative_id.map(lambda value: a.case.get(value).name)
        )
        detail = detail[
            [
                "Initiative", "planned_for_observed", "observed_benefit", "variance_EUR_k", "variance_percent",
                "coverage", "missing_periods", "confidence", "sources", "material_deviation", "observation_type",
            ]
        ].rename(
            columns={
                "planned_for_observed": "Plan for observed periods (EUR k)",
                "observed_benefit": "Observed benefits (EUR k)",
                "variance_EUR_k": "Variance (EUR k)",
                "variance_percent": "Variance (%)",
                "coverage": "Coverage",
                "missing_periods": "Missing periods",
                "confidence": "Confidence",
                "sources": "Observation sources",
                "material_deviation": "Material follow-up",
                "observation_type": "Observation type",
            }
        )
        row = _write_table(
            ws,
            formats,
            row,
            1,
            detail,
            widths=[38, 21, 20, 18, 16, 14, 20, 14, 34, 18, 22],
        )
        observations = a.benefits[a.benefits.observed_benefit_EUR_k.notna()].assign(
            Initiative=lambda frame: frame.initiative_id.map(lambda value: a.case.get(value).name)
        )
        observations = observations[
            [
                "Initiative", "quarter", "reporting_period_end", "planned_benefit", "observed_benefit_EUR_k",
                "variance_EUR_k", "variance_percent", "currency", "source", "observation_date", "confidence",
                "revision", "is_simulated", "material_deviation",
            ]
        ].rename(
            columns={
                "quarter": "Quarter",
                "reporting_period_end": "Reporting period end",
                "planned_benefit": "Planned benefit (EUR k)",
                "observed_benefit_EUR_k": "Observed benefit (EUR k)",
                "variance_EUR_k": "Variance (EUR k)",
                "variance_percent": "Variance (%)",
                "currency": "Currency",
                "source": "Source",
                "observation_date": "Observation date",
                "confidence": "Confidence",
                "revision": "Revision",
                "is_simulated": "Fictional",
                "material_deviation": "Material follow-up",
            }
        )
        row = _section(ws, formats, row, "Observation detail", 13)
        row = _write_table(
            ws,
            formats,
            row,
            1,
            observations,
            widths=[38, 10, 18, 20, 20, 18, 15, 11, 32, 18, 14, 10, 11, 18],
        )
        ws.write(
            row + 1,
            1,
            "Observed changes may have multiple causes. Validate source, baseline, definition and attribution evidence before action.",
            formats["note"],
        )
    ws.freeze_panes(table_row + 1, 2)


def _populate_scenarios(ws, formats, a) -> None:
    _setup_sheet(ws)
    row = _sheet_title(ws, formats, a.case, "Scenario assumptions and sensitivity")
    row = _section(ws, formats, row, "Active model inputs", 8)
    model = settings(a)
    inputs = pd.DataFrame(
        [
            ["Annual discount rate", model["discount_rate"], "Probability"],
            ["Downside penalty", model["risk_aversion"], "Weight"],
            ["Simulation draws", model["n_samples"], "Count"],
            ["Deployment delay", model["deployment_delay_quarters"], "Quarters"],
            ["Capital carryover", model["carryover"], "Boolean"],
            ["Portfolio ceiling", sum(model["budget_by_year_EUR_k"]), "EUR k"],
        ],
        columns=["Input", "Active value", "Unit"],
    )
    row = _write_table(ws, formats, row, 1, inputs, widths=[26, 18, 16], assumptions=True)
    row = _section(ws, formats, row, "Stress-tested portfolios", 9)
    scenario = a.scenarios.copy()
    scenario["delta_vs_current_EUR_k"] = scenario.expected_npv - a.portfolio.mean
    scenario = scenario.rename(
        columns={
            "scenario": "Scenario",
            "status": "Optimization status",
            "expected_npv": "Expected NPV (EUR k)",
            "p10_npv": "P10 NPV (EUR k)",
            "n_funded": "Funded initiative types",
            "capex": "Capex (EUR k)",
            "delta_vs_current_EUR_k": "Change vs current (EUR k)",
        }
    )
    row = _write_table(ws, formats, row, 1, scenario, widths=[36, 24, 18, 18, 18, 16, 22])
    row = _section(ws, formats, row, "Capital sensitivity", 9)
    frontier = pd.DataFrame(a.frontier).rename(
        columns={
            "budget_scale": "Capital scale",
            "budget_total": "Capital envelope (EUR k)",
            "expected_npv": "Expected NPV (EUR k)",
            "p10_npv": "P10 NPV (EUR k)",
            "p90_npv": "P90 NPV (EUR k)",
            "capex_total": "Capital required (EUR k)",
            "n_funded": "Funded initiative types",
        }
    )
    row = _write_table(ws, formats, row, 1, frontier, widths=[14, 22, 20, 18, 18, 22, 20])
    row = _section(ws, formats, row, "Selection stability", 14)
    robust = a.robustness.reset_index(names="Initiative ID")
    robust.insert(1, "Initiative", robust["Initiative ID"].map(lambda iid: a.case.get(iid).name))
    _write_table(ws, formats, row, 1, robust, widths=[14, 36, *([15] * (len(robust.columns) - 2))])


def _populate_governance(ws, formats, a) -> None:
    _setup_sheet(ws)
    row = _sheet_title(ws, formats, a.case, "Governance and approval considerations")
    row = _section(ws, formats, row, "Initiative governance summary", 9)
    summary = pd.DataFrame(
        [
            {
                "Initiative": item.name,
                "Decision": _decision(a, item),
                "Category": a.screenings[item.id].category,
                "Review status": a.screenings[item.id].review_status,
                "Missing information": "; ".join(a.screenings[item.id].unknown_questions) or "None recorded",
                "Pilot gate": "Required" if item.pilot_gate else "Not configured",
                "Dependencies": _dependencies(a, item),
            }
            for item in a.case.initiatives
        ]
    )
    row = _write_table(ws, formats, row, 1, summary, widths=[36, 25, 20, 18, 44, 16, 38])
    if a.case.profile:
        row = _section(ws, formats, row, "Management approvals and principal risks", 8)
        items = [["Approval", item] for item in a.case.profile.decision_notes["approval_points"]]
        items += [["Risk", item] for item in a.case.profile.decision_notes["risks"]]
        row = _write_table(ws, formats, row, 1, pd.DataFrame(items, columns=["Type", "Consideration"]), widths=[16, 90])
    row = _section(ws, formats, row, "Detailed governance questionnaire", 12)
    detailed = tables(a)["governance_PENDING_REVIEW"].rename(
        columns={
            "id": "Initiative ID",
            "question": "Question",
            "answer": "Current answer",
            "evidence": "Evidence or assumption",
            "category": "Category",
            "review_status": "Review status",
            "missing_questions": "Missing questions",
            "provisions": "Relevant provisions",
            "remaining_uncertainty": "Remaining uncertainty",
            "human_approval": "Human approval recorded",
        }
    )
    _write_table(ws, formats, row, 1, detailed, widths=[14, 42, 16, 48, 18, 18, 36, 42, 48, 18])


def _populate_assumptions(ws, formats, a) -> None:
    _setup_sheet(ws)
    row = _sheet_title(ws, formats, a.case, "Financial and operating assumptions")
    row = _section(ws, formats, row, "Portfolio model assumptions", 8)
    model = settings(a)
    model_rows = [
        ["Valuation horizon", model["horizon_years"], "Years", "Illustrative"],
        ["Rollout horizon", model["rollout_years"], "Years", "Illustrative"],
        ["Discount rate", model["discount_rate"], "Probability", "Illustrative"],
        ["Downside penalty", model["risk_aversion"], "Weight", "Illustrative"],
        ["Quarterly deployment limit", model["max_sites_per_quarter"], "Deployments", "Illustrative"],
        ["Simulation draws", model["n_samples"], "Count", "Model setting"],
        ["Random seed", model["seed"], "Integer", "Model setting"],
        ["Capital carryover", model["carryover"], "Boolean", "Scenario setting"],
    ]
    row = _write_table(
        ws,
        formats,
        row,
        1,
        pd.DataFrame(model_rows, columns=["Input", "Active value", "Unit", "Nature"]),
        widths=[32, 18, 18, 20],
        assumptions=True,
    )
    row = _section(ws, formats, row, "Initiative assumptions", 8)
    assumptions = tables(a)["assumptions"].rename(
        columns={"id": "Initiative ID", "input": "Input", "low": "Low", "mode": "Mode", "high": "High", "unit": "Unit", "nature": "Nature"}
    )
    _write_table(ws, formats, row, 1, assumptions, widths=[14, 24, 16, 16, 16, 16, 16], assumptions=True)
    ws.freeze_panes(row + 1, 2)


def _populate_sources(ws, formats, a) -> None:
    _setup_sheet(ws, landscape=False)
    row = _sheet_title(ws, formats, a.case, "Methodology, provenance and limitations")
    ws.set_column(1, 1, 28)
    ws.set_column(2, 2, 90)
    row = _section(ws, formats, row, "Methodology", 5)
    method = [
        ("Calculation source", "All values are exported from the active Python Analysis result shown in the application."),
        ("Valuation", f"Quarterly cohort cash flows over {a.case.horizon_years} years, discounted at {a.case.discount_rate:.1%} annually."),
        ("Selection", "OR-Tools CP-SAT selects discrete rollout scales subject to capital, staffing, deployment, dependency and governance constraints."),
        ("Uncertainty", f"Seeded Monte Carlo simulation with {a.case.n_samples:,} draws. P10 and P90 are modeled percentiles."),
        ("Scheduling", "Fixed quarterly phasing. Selected scale is optimized; arbitrary start dates are not optimized."),
        ("Research boundary", "Research-assistant proposals and uploaded documents are not included and cannot change the financial model."),
    ]
    for offset, (label, text) in enumerate(method):
        ws.write(row + offset, 1, label, formats["metric_label"])
        ws.write(row + offset, 2, text, formats["body_wrap"])
        ws.set_row(row + offset, 28)
    row += len(method) + 2
    row = _section(ws, formats, row, "Material limitations", 5)
    limitations = [
        "Financial inputs, budgets, capacity and returns are illustrative model assumptions, not company forecasts.",
        "Capital constraints use expected cost. Taxes, working capital, terminal value and failure contagion are excluded.",
        "Benefits may overlap; no automatic benefit-overlap adjustment is applied.",
        "Planned gates do not prove legal, workforce, security or management approval.",
        "Simulated benefits are demonstration data. User-provided actuals remain unverified.",
    ]
    for offset, text in enumerate(limitations):
        ws.write(row + offset, 1, f"{offset + 1}.", formats["body"])
        ws.write(row + offset, 2, text, formats["body_wrap"])
    row += len(limitations) + 2
    row = _section(ws, formats, row, "Source register", 5)
    source_row = row
    headers = ["Source ID", "Title", "Publisher", "Accessed", "URL"]
    for offset, header in enumerate(headers):
        ws.write(source_row, 1 + offset, header, formats["header"])
    for index, (source_id, source) in enumerate(a.case.sources.items(), start=source_row + 1):
        ws.write(index, 1, source_id, formats["body"])
        ws.write(index, 2, _clean(source.get("title")), formats["body_wrap"])
        ws.write(index, 3, _clean(source.get("publisher")), formats["body_wrap"])
        ws.write(index, 4, _clean(source.get("accessed")), formats["body"])
        ws.write_url(index, 5, source["url"], formats["source"], string=source["url"])
        ws.set_row(index, 36)
    ws.set_column(1, 1, 12)
    ws.set_column(2, 2, 55)
    ws.set_column(3, 3, 24)
    ws.set_column(4, 4, 14)
    ws.set_column(5, 5, 70)


def excel_analysis(a) -> bytes:
    """Return a professional XLSX snapshot of the current analysis."""
    _validate(a)
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(
        output,
        {
            "in_memory": True,
            "strings_to_formulas": False,
            "strings_to_urls": False,
            "nan_inf_to_errors": True,
        },
    )
    workbook.set_properties(
        {
            "title": f"{PROJECT_TITLE} - {a.case.title}",
            "subject": "Current investment portfolio analysis",
            "author": "Soham Shinde",
            "company": "Soham Shinde",
            "comments": "Illustrative model-based scenario; not an official company forecast.",
            "created": datetime(2000, 1, 1, tzinfo=timezone.utc),
        }
    )
    case_accent = a.case.profile.accent["primary"] if a.case.profile else TEAL
    formats = _xlsx_formats(workbook, case_accent)
    sheets = {
        name: workbook.add_worksheet(name)
        for name in (
            "Executive Summary",
            "Portfolio",
            "Financials",
            "Delivery Plan",
            "Scenarios",
            "Governance",
            "Assumptions",
            "Sources & Method",
        )
    }
    sheets["Executive Summary"].set_tab_color(TEAL_DARK)
    sheets["Assumptions"].set_tab_color(AMBER)
    sheets["Sources & Method"].set_tab_color(MUTED)
    _populate_portfolio(sheets["Portfolio"], formats, a)
    _populate_executive(workbook, sheets["Executive Summary"], formats, a)
    _populate_financials(sheets["Financials"], formats, a)
    _populate_delivery(workbook, sheets["Delivery Plan"], formats, a)
    _populate_scenarios(sheets["Scenarios"], formats, a)
    _populate_governance(sheets["Governance"], formats, a)
    _populate_assumptions(sheets["Assumptions"], formats, a)
    _populate_sources(sheets["Sources & Method"], formats, a)
    workbook.close()
    data = output.getvalue()
    if not data or len(data) > MAX_EXPORT_BYTES:
        raise ExportError("The Excel analysis exceeded the export size limit.")
    return data


class _InvariantCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        kwargs.update(invariant=1, pageCompression=1)
        super().__init__(*args, **kwargs)


def _styles():
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("Title", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=colors.HexColor(INK), alignment=TA_LEFT, spaceAfter=8),
        "subtitle": ParagraphStyle("Subtitle", parent=styles["Normal"], fontName="Helvetica", fontSize=10, leading=14, textColor=colors.HexColor(MUTED), spaceAfter=12),
        "h1": ParagraphStyle("H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=14, leading=17, textColor=colors.HexColor(TEAL_DARK), spaceBefore=8, spaceAfter=7),
        "h2": ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=colors.HexColor(INK), spaceBefore=6, spaceAfter=5),
        "body": ParagraphStyle("Body", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.5, leading=12, textColor=colors.HexColor(INK), spaceAfter=5),
        "small": ParagraphStyle("Small", parent=styles["BodyText"], fontName="Helvetica", fontSize=7, leading=9, textColor=colors.HexColor(MUTED), spaceAfter=3),
        "risk": ParagraphStyle("Risk", parent=styles["BodyText"], fontName="Helvetica", fontSize=8, leading=11, textColor=colors.HexColor(RED), spaceAfter=4),
    }


def _p(value, style) -> Paragraph:
    return Paragraph(escape(_pdf_text(value)), style)


def _pdf_table(rows, widths, styles, *, header=True, font_size=7.2) -> Table:
    prepared = []
    for r_index, row in enumerate(rows):
        prepared.append(
            [
                _p(value, styles["small"] if r_index or not header else ParagraphStyle("TableHead", parent=styles["small"], textColor=colors.white, fontName="Helvetica-Bold", fontSize=7, leading=8))
                for value in row
            ]
        )
    table = Table(prepared, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor(GRID)),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
    ]
    if header:
        commands += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(TEAL)), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
    table.setStyle(TableStyle(commands))
    return table


def _scenario_drawing(a, width=500, height=150) -> Drawing:
    scenarios = a.scenarios.copy()
    scenarios["delta"] = scenarios.expected_npv - a.portfolio.mean
    scenarios = scenarios.sort_values("delta").head(6)
    drawing = Drawing(width, height)
    label_width = 220
    axis_x = 490
    bar_width = 120
    max_abs = max(float(scenarios.delta.abs().max()), 1.0)
    drawing.add(Line(axis_x, 8, axis_x, height - 8, strokeColor=colors.HexColor(GRID), strokeWidth=0.8))
    step = (height - 20) / max(len(scenarios), 1)
    for index, row in enumerate(scenarios.itertuples(index=False)):
        y = height - 18 - index * step
        label = _pdf_text(row.scenario)
        if len(label) > 37:
            label = label[:34] + "..."
        drawing.add(String(0, y, label, fontName="Helvetica", fontSize=7, fillColor=colors.HexColor(INK)))
        length = abs(float(row.delta)) / max_abs * bar_width
        x = axis_x - length if row.delta < 0 else axis_x
        color = RED if row.delta < 0 else TEAL
        drawing.add(Rect(x, y - 3, max(length, 1), 7, fillColor=colors.HexColor(color), strokeColor=None))
        drawing.add(String(label_width, y, _money(float(row.expected_npv), 1), fontName="Helvetica", fontSize=7, fillColor=colors.HexColor(MUTED)))
    return drawing


def _page(canvas_obj, doc, a) -> None:
    canvas_obj.saveState()
    width, height = A4
    canvas_obj.setFillColor(colors.HexColor(IVORY))
    canvas_obj.rect(0, height - 18 * mm, width, 18 * mm, fill=1, stroke=0)
    canvas_obj.setFillColor(colors.HexColor(TEAL_DARK))
    canvas_obj.setFont("Helvetica-Bold", 8)
    canvas_obj.drawString(16 * mm, height - 11 * mm, PROJECT_TITLE)
    canvas_obj.setFillColor(colors.HexColor(MUTED))
    canvas_obj.setFont("Helvetica", 7)
    canvas_obj.drawRightString(width - 16 * mm, height - 11 * mm, _pdf_text(a.case.title))
    canvas_obj.setStrokeColor(colors.HexColor(GRID))
    canvas_obj.line(16 * mm, 14 * mm, width - 16 * mm, 14 * mm)
    canvas_obj.drawString(16 * mm, 9 * mm, "Illustrative model-based scenario. Not an official company forecast.")
    canvas_obj.drawRightString(width - 16 * mm, 9 * mm, f"Page {doc.page}")
    canvas_obj.restoreState()


def investment_committee_pdf(a) -> bytes:
    """Return a concise, deterministic investment committee PDF."""
    _validate(a)
    output = io.BytesIO()
    styles = _styles()
    doc = BaseDocTemplate(
        output,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=24 * mm,
        bottomMargin=19 * mm,
        title=f"{PROJECT_TITLE} - {_pdf_text(a.case.title)}",
        author="Soham Shinde",
        subject="Investment committee report",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="committee-report")
    doc.addPageTemplates(PageTemplate(id="all-pages", frames=[frame], onPageEnd=lambda c, d: _page(c, d, a)))
    story = [
        _p(PROJECT_TITLE, styles["title"]),
        _p(SUBTITLE, styles["subtitle"]),
        _p(a.case.title, styles["h1"]),
        _p("Illustrative case study | Current optimized portfolio and active scenario", styles["subtitle"]),
        _p("Executive decision summary", styles["h1"]),
    ]
    metrics = [
        ["Expected NPV", "Capital required", "P10 / P90 NPV", "Loss probability"],
        [_money(a.portfolio.mean), _money(float(a.portfolio.capex_by_year.sum())), f"{_money(a.portfolio.pct(10))} / {_money(a.portfolio.pct(90))}", f"{a.portfolio.p_loss:.1%}"],
    ]
    metric_table = _pdf_table(metrics, [42 * mm, 42 * mm, 52 * mm, 32 * mm], styles)
    metric_table.setStyle(TableStyle([("BACKGROUND", (0, 1), (-1, 1), colors.HexColor(TEAL_PALE)), ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold")]))
    story += [metric_table, Spacer(1, 4 * mm)]
    story.append(
        _p(
            f"Fund {len(a.portfolio.funded)} of {len(a.case.initiatives)} initiative types and schedule {sum(a.portfolio.funded.values())} deployments by Q{_last_quarter(a)}. Capital remains within the active {_money(sum(a.case.budget_by_year))} envelope. The recommendation is conditional on the listed approvals, operating baselines and delivery capacity.",
            styles["body"],
        )
    )
    story += [_p("Recommended initiatives", styles["h2"])]
    selected_rows = [["Initiative", "Deployments", "Expected NPV", "Rationale"]]
    for item in a.case.initiatives:
        sites = a.portfolio.choice[item.id]
        if sites:
            selected_rows.append([item.name, sites, _money(a.valuations[item.id][sites].mean), item.description])
    if len(selected_rows) == 1:
        selected_rows.append(["No funded initiatives", 0, _money(0), "Current constraints support holding investment."])
    story += [_pdf_table(selected_rows, [48 * mm, 22 * mm, 28 * mm, 70 * mm], styles), Spacer(1, 3 * mm)]
    story += [_p("Management decision", styles["h2"])]
    decisions = [
        "Validate the illustrative financial assumptions and eligible deployment scope.",
        "Confirm delivery ownership, prerequisites and quarterly staffing.",
        "Complete pilot, legal, security and workforce reviews before deployment.",
        "Assign benefit owners and evidence standards before tracking actuals.",
    ]
    for index, item in enumerate(decisions, start=1):
        story.append(_p(f"{index}. {item}", styles["body"]))
    story += [CondPageBreak(150 * mm), _p("Financial outlook", styles["h1"])]
    annual = tables(a)["cash_flows"].groupby("year", as_index=False).sum(numeric_only=True)
    financial_rows = [["Year", "Benefits", "Capex", "Operating costs", "Net cash", "Discounted cash"]]
    for row in annual.itertuples(index=False):
        financial_rows.append([row.year, _money(row.benefit_EUR_k), _money(row.capex_EUR_k), _money(row.opex_EUR_k), _money(row.net_cash_EUR_k), _money(row.discounted_cash_EUR_k)])
    story += [_pdf_table(financial_rows, [15 * mm, 30 * mm, 27 * mm, 31 * mm, 29 * mm, 34 * mm], styles)]
    story.append(
        _p(
            f"Discounted quarterly cash flows reconcile to expected NPV of {_money(a.portfolio.mean)}. Undiscounted operating benefits total {_money(_benefits_total(a))}. Capital constraints use expected cost rather than a worst-case cost reserve.",
            styles["body"],
        )
    )
    story += [_p("Investment and delivery constraints", styles["h2"])]
    constraints = [
        ["Constraint", "Active basis"],
        ["Capital", f"{_money(sum(a.case.budget_by_year))} across {a.case.rollout_years} years"],
        ["Quarterly deployments", f"Maximum {a.case.max_sites_per_quarter} per quarter"],
        ["Implementation staffing", " / ".join(f"{value:g}" for value in a.case.fte_capacity_by_year) + " FTE-years by year"],
        ["Timing", "Fixed quarterly phasing with prior-quarter dependencies"],
        ["Optimization", f"{a.portfolio.status}; relative gap {a.portfolio.relative_gap:.4%}"],
    ]
    story += [_pdf_table(constraints, [48 * mm, 120 * mm], styles)]
    story += [_p("Quarterly implementation plan", styles["h1"])]
    capacity = _quarterly_capacity(a)
    delivery_rows = [["Quarter", "Deployments / limit", "FTE-years / limit", "Capex", "Benefits", "Review gates"]]
    for _, row in capacity.iterrows():
        delivery_rows.append(
            [
                int(row["Quarter"]),
                f"{int(row['Deployments'])} / {int(row['Deployment limit'])}",
                f"{row['FTE-years required']:.2f} / {row['FTE-years limit']:.2f}",
                _money(row["Capex (EUR k)"]),
                _money(row["Benefits (EUR k)"]),
                int(row["Review gates"]),
            ]
        )
    story += [_pdf_table(delivery_rows, [17 * mm, 30 * mm, 31 * mm, 28 * mm, 28 * mm, 24 * mm], styles)]
    story += [CondPageBreak(150 * mm), _p("Scenario sensitivity and principal risks", styles["h1"])]
    story += [_p("Change in expected NPV under recalculated stress portfolios", styles["h2"]), _scenario_drawing(a), Spacer(1, 2 * mm)]
    scenario_rows = [["Scenario", "Status", "Expected NPV", "P10 NPV", "Capex", "Funded"]]
    for row in a.scenarios.itertuples(index=False):
        scenario_rows.append([row.scenario, row.status, _money(row.expected_npv) if pd.notna(row.expected_npv) else "Unavailable", _money(row.p10_npv) if pd.notna(row.p10_npv) else "Unavailable", _money(row.capex) if pd.notna(row.capex) else "Unavailable", row.n_funded if pd.notna(row.n_funded) else "n.a."])
    story += [_pdf_table(scenario_rows, [50 * mm, 28 * mm, 28 * mm, 25 * mm, 24 * mm, 15 * mm], styles)]
    story += [_p("Principal risks", styles["h2"])]
    risks = a.case.profile.decision_notes["risks"] if a.case.profile else ["Business assumptions and delivery readiness require management validation."]
    for item in risks:
        story.append(_p(f"- {item}", styles["risk"]))
    story += [CondPageBreak(150 * mm), _p("Governance and approval considerations", styles["h1"])]
    governance_rows = [["Initiative", "Decision", "Category", "Review status", "Open questions"]]
    for item in a.case.initiatives:
        screen = a.screenings[item.id]
        governance_rows.append([item.name, _decision(a, item), screen.category, screen.review_status, "; ".join(screen.unknown_questions) or "None recorded"])
    story += [_pdf_table(governance_rows, [45 * mm, 34 * mm, 27 * mm, 27 * mm, 35 * mm], styles)]
    if a.case.profile:
        story += [_p("Approvals required", styles["h2"])]
        for item in a.case.profile.decision_notes["approval_points"]:
            story.append(_p(f"- {item}", styles["body"]))
    story += [_p("Assumptions, methodology and limitations", styles["h1"])]
    method_rows = [
        ["Model setting", "Active value"],
        ["Valuation horizon", f"{a.case.horizon_years} years"],
        ["Discount rate", f"{a.case.discount_rate:.1%}"],
        ["Monte Carlo draws", f"{a.case.n_samples:,}; seed {a.case.seed}"],
        ["Deployment policy", "Fixed integer quarterly cohorts; gates before deployment; prior-quarter dependencies"],
        ["Research boundary", "Research proposals and uploaded documents are excluded from the financial model and this report"],
    ]
    story += [_pdf_table(method_rows, [50 * mm, 118 * mm], styles)]
    limitations = [
        "Costs, benefits, probabilities, budgets and returns are illustrative assumptions, not official company forecasts.",
        "No terminal value, tax, working-capital or failure-contagion model is included.",
        "No automatic benefit-overlap adjustment is applied.",
        "Capital limits use expected costs. Planned gates do not prove approval.",
        "Simulated benefits are demonstration values; imported actuals remain unverified.",
    ]
    for item in limitations:
        story.append(_p(f"- {item}", styles["body"]))
    story += [CondPageBreak(105 * mm), _p("Benefits realization", styles["h1"])]
    benefit_summary = portfolio_summary(a.benefits)
    if benefit_summary["observed"] is None:
        story.append(
            _p(
                "Observed benefits are unavailable. Missing observations are not treated as zero and do not change the investment recommendation.",
                styles["body"],
            )
        )
    else:
        benefit_rows = [["Initiative", "Plan", "Observed", "Variance", "Coverage", "Confidence", "Follow-up"]]
        for row in initiative_summary(a.benefits).itertuples(index=False):
            benefit_rows.append(
                [
                    a.case.get(row.initiative_id).name,
                    _money(row.planned_for_observed) if row.observed_periods else "Unavailable",
                    _money(row.observed_benefit) if pd.notna(row.observed_benefit) else "Unavailable",
                    _money(row.variance_EUR_k) if pd.notna(row.variance_EUR_k) else "Unavailable",
                    f"{row.coverage:.0%}",
                    row.confidence,
                    "Required" if row.material_deviation else "No",
                ]
            )
        story += [
            _p(
                f"Through Q{benefit_summary['reporting_quarter']}, observed benefits are {_money(benefit_summary['observed'])} versus {_money(benefit_summary['planned'])} planned for the same reported periods. Observation coverage is {benefit_summary['coverage']:.0%}. Values are operational observations, not valuation cash flows.",
                styles["body"],
            ),
            _pdf_table(benefit_rows, [42 * mm, 22 * mm, 23 * mm, 22 * mm, 18 * mm, 19 * mm, 22 * mm], styles),
            _p(
                "Observed changes may have multiple causes. Validate measurement sources, baselines and attribution evidence before action. Missing periods remain unavailable.",
                styles["small"],
            ),
        ]
    sources_heading = _p("Sources", styles["h2"])
    source_rows = [["ID", "Publisher and title", "Accessed", "URL"]]
    for source_id, source in a.case.sources.items():
        source_rows.append([source_id, f"{source.get('publisher', '')}: {source.get('title', '')}", source.get("accessed", ""), source["url"]])
    story += [KeepTogether([sources_heading, _pdf_table(source_rows, [11 * mm, 70 * mm, 20 * mm, 67 * mm], styles, font_size=6.5)])]

    doc.build(story, canvasmaker=_InvariantCanvas)
    data = output.getvalue()
    if not data or len(data) > MAX_EXPORT_BYTES:
        raise ExportError("The investment committee report exceeded the export size limit.")
    return data
