from __future__ import annotations

import csv
import os
import re
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .database import Database, from_paise


def _register_font() -> str:
    candidates = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "Nirmala.ttf",
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                pdfmetrics.registerFont(TTFont("UtthanFont", candidate))
                return "UtthanFont"
            except Exception:
                pass
    return "Helvetica"


FONT = _register_font()
MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def money(paise: int | None) -> str:
    return f"Rs. {from_paise(paise):,.2f}"


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-") or "report"


def open_file(path: Path) -> None:
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]


def _header(story: list, db: Database, title: str) -> None:
    styles = getSampleStyleSheet()
    center = ParagraphStyle(
        "Center", parent=styles["Title"], fontName=FONT, alignment=TA_CENTER,
        textColor=colors.HexColor("#173F5F"), spaceAfter=3 * mm,
    )
    subtitle = ParagraphStyle(
        "Subtitle", parent=styles["Heading2"], fontName=FONT, alignment=TA_CENTER,
        textColor=colors.HexColor("#20639B"), spaceAfter=5 * mm,
    )
    story.append(Paragraph(db.setting("society_name", "UTHAN CREATIVE SOCIETY"), center))
    story.append(Paragraph(title, subtitle))


def generate_due_list(db: Database, period_id: int) -> Path:
    rows = db.period_dues(period_id)
    if not rows:
        raise ValueError("No dues found for this period")
    year, month = rows[0]["year"], rows[0]["month"]
    target = db.reports_dir / f"Due-List-{year:04d}-{month:02d}.pdf"
    document = SimpleDocTemplate(
        str(target), pagesize=landscape(A4), rightMargin=8 * mm, leftMargin=8 * mm,
        topMargin=10 * mm, bottomMargin=10 * mm,
    )
    story: list = []
    _header(story, db, f"Due List - {MONTHS[month - 1]} {year}")
    small = ParagraphStyle("Small", fontName=FONT, fontSize=6.6, leading=8, alignment=TA_CENTER)
    left = ParagraphStyle("SmallLeft", parent=small, alignment=TA_LEFT)
    headings = [
        "No.", "Member", "Savings<br/>opening", "Monthly<br/>saving", "EMI",
        "Interest", "This month", "Loan<br/>opening", "Loan after<br/>EMI",
        "Savings<br/>after", "Old due", "Late fee", "Grand due", "Status",
    ]
    data = [[Paragraph(value, small) for value in headings]]
    totals = [0] * 11
    members = {row["id"]: row for row in db.list_members(include_inactive=True)}
    for row in rows:
        member = members[row["member_id"]]
        opening_saving = member["contribution_balance_paise"] - row["contribution_paid_paise"]
        monthly = row["contribution_due_paise"] + row["emi_due_paise"] + row["interest_due_paise"]
        grand = monthly + row["arrears_due_paise"] + row["late_fee_paise"]
        numeric = [
            opening_saving, row["contribution_due_paise"], row["emi_due_paise"],
            row["interest_due_paise"], monthly, row["opening_loan_paise"],
            max(0, row["opening_loan_paise"] - row["emi_due_paise"]),
            opening_saving + row["contribution_due_paise"], row["arrears_due_paise"],
            row["late_fee_paise"], grand,
        ]
        totals = [a + b for a, b in zip(totals, numeric)]
        data.append([
            str(row["member_no"]), Paragraph(row["name"], left),
            *[f"{from_paise(value):,.0f}" for value in numeric], row["status"],
        ])
    data.append([
        "", Paragraph("TOTAL", left), *[f"{from_paise(value):,.0f}" for value in totals], "",
    ])
    widths = [9, 34, 18, 17, 14, 15, 18, 18, 18, 18, 16, 14, 18, 15]
    table = Table(data, colWidths=[value * mm for value in widths], repeatRows=1)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 1), (-1, -1), 6.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173F5F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E8F1F8")),
        ("FONTNAME", (0, -1), (-1, -1), FONT),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 1), (-2, -1), "RIGHT"),
        ("ALIGN", (-1, 1), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#829AB1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F7FAFC")]),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    story.append(table)
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "Generated by Utthan Society Manager. Amounts are calculated from the local ledger.",
        ParagraphStyle("Foot", fontName=FONT, fontSize=7, textColor=colors.grey),
    ))
    document.build(story)
    return target


def generate_member_bill(db: Database, due_id: int) -> Path:
    row = db.due(due_id)
    if not row:
        raise ValueError("Due record not found")
    target = db.reports_dir / (
        f"Bill-{row['year']:04d}-{row['month']:02d}-{safe_name(row['name'])}.pdf"
    )
    document = SimpleDocTemplate(
        str(target), pagesize=A4, rightMargin=22 * mm, leftMargin=22 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
    )
    story: list = []
    _header(story, db, f"Monthly Due Bill - {MONTHS[row['month'] - 1]} {row['year']}")
    styles = getSampleStyleSheet()
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontName=FONT, fontSize=10, leading=15)
    story.append(Paragraph(f"Member No.: <b>{row['member_no']}</b>", body))
    story.append(Paragraph(f"Member Name: <b>{row['name']}</b>", body))
    story.append(Spacer(1, 7 * mm))
    paid = row["total_paid_paise"]
    total = row["total_due_paise"]
    data = [
        ["Description", "Amount"],
        ["Monthly contribution", money(row["contribution_due_paise"])],
        ["Loan principal instalment", money(row["emi_due_paise"])],
        ["Interest on opening loan", money(row["interest_due_paise"])],
        ["Previous unpaid amount", money(row["arrears_due_paise"])],
        ["Late fee", money(row["late_fee_paise"])],
        ["Total due", money(total)],
        ["Amount received", money(paid)],
        ["Balance payable", money(max(0, total - paid))],
    ]
    table = Table(data, colWidths=[105 * mm, 45 * mm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173F5F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9FB3C8")),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BACKGROUND", (0, -3), (-1, -1), colors.HexColor("#E8F1F8")),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(table)
    story.append(Spacer(1, 12 * mm))
    story.append(Paragraph("Authorised signature: ______________________________", body))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph(
        f"Generated {datetime.now().strftime('%d %b %Y, %I:%M %p')} | Data stored locally",
        ParagraphStyle("Foot", parent=body, fontSize=8, textColor=colors.grey),
    ))
    document.build(story)
    return target


def generate_receipt(db: Database, transaction_id: int) -> Path:
    with db.connect() as connection:
        row = connection.execute(
            """SELECT t.*, m.member_no, m.name, d.contribution_paid_paise,
                d.principal_paid_paise, d.interest_paid_paise, d.arrears_paid_paise,
                d.late_fee_paid_paise, p.year, p.month
                FROM transactions t JOIN members m ON m.id = t.member_id
                LEFT JOIN dues d ON d.id = t.due_id LEFT JOIN periods p ON p.id = d.period_id
                WHERE t.id = ?""",
            (transaction_id,),
        ).fetchone()
    if not row:
        raise ValueError("Payment transaction not found")
    target = db.reports_dir / f"Receipt-{transaction_id:06d}-{safe_name(row['name'])}.pdf"
    document = SimpleDocTemplate(
        str(target), pagesize=A4, rightMargin=28 * mm, leftMargin=28 * mm,
        topMargin=22 * mm, bottomMargin=22 * mm,
    )
    story: list = []
    _header(story, db, "Payment Receipt")
    style = ParagraphStyle("Body", fontName=FONT, fontSize=11, leading=17)
    info = [
        ["Receipt No.", f"UT-{transaction_id:06d}"],
        ["Date", row["transaction_date"]],
        ["Member", f"{row['member_no']} - {row['name']}"],
        ["For period", f"{MONTHS[row['month'] - 1]} {row['year']}" if row["month"] else ""],
        ["Payment method", row["payment_method"]],
        ["Reference", row["reference"] or "-"],
        ["Amount received", money(row["amount_paise"])],
    ]
    table = Table(info, colWidths=[45 * mm, 95 * mm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E8F1F8")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9FB3C8")),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("FONTNAME", (1, -1), (1, -1), FONT),
        ("FONTSIZE", (1, -1), (1, -1), 13),
    ]))
    story.append(table)
    story.append(Spacer(1, 18 * mm))
    story.append(Paragraph("Received by: _________________________", style))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("Member signature: ____________________", style))
    document.build(story)
    return target


def export_period_csv(db: Database, period_id: int) -> Path:
    rows = db.period_dues(period_id)
    if not rows:
        raise ValueError("No dues found")
    target = db.reports_dir / f"Due-List-{rows[0]['year']:04d}-{rows[0]['month']:02d}.csv"
    fields = [
        "member_no", "name", "contribution_due_paise", "emi_due_paise",
        "interest_due_paise", "arrears_due_paise", "late_fee_paise",
        "total_due_paise", "total_paid_paise", "status",
    ]
    with target.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "Member No", "Member Name", "Contribution", "EMI", "Interest",
            "Old Due", "Late Fee", "Total Due", "Paid", "Status",
        ])
        for row in rows:
            writer.writerow([
                row["member_no"], row["name"],
                *[f"{from_paise(row[field]):.2f}" for field in fields[2:-1]],
                row["status"],
            ])
    return target
