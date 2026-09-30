from __future__ import annotations

import csv
import os
import re
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import escape

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
from reportlab.platypus.flowables import HRFlowable

from .database import Database, from_paise


def _register_fonts() -> tuple[str, str]:
    fonts_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for regular, bold in (("arial.ttf", "arialbd.ttf"), ("Nirmala.ttf", "NirmalaB.ttf")):
        try:
            pdfmetrics.registerFont(TTFont("UtthanFont", fonts_dir / regular))
        except Exception:
            continue
        bold_name = "UtthanFont"
        try:
            pdfmetrics.registerFont(TTFont("UtthanFont-Bold", fonts_dir / bold))
            bold_name = "UtthanFont-Bold"
        except Exception:
            pass
        pdfmetrics.registerFontFamily(
            "UtthanFont", normal="UtthanFont", bold=bold_name,
            italic="UtthanFont", boldItalic=bold_name,
        )
        return "UtthanFont", bold_name
    return "Helvetica", "Helvetica-Bold"


FONT, FONT_BOLD = _register_fonts()
NAVY = colors.HexColor("#173F5F")
BLUE = colors.HexColor("#20639B")
LIGHT = colors.HexColor("#E8F1F8")
GRID = colors.HexColor("#9FB3C8")
MUTED = colors.HexColor("#627D98")
GOOD = colors.HexColor("#236B5E")
WARN = colors.HexColor("#8A2C23")
MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def money(paise: int | None) -> str:
    return f"Rs. {from_paise(paise):,.2f}"


_ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
    "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen",
    "Eighteen", "Nineteen",
]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _two_digits(value: int) -> str:
    if value < 20:
        return _ONES[value]
    tens, ones = divmod(value, 10)
    return f"{_TENS[tens]} {_ONES[ones]}".strip()


def number_in_words(value: int) -> str:
    """Indian numbering: crore, lakh, thousand, hundred."""
    if value == 0:
        return "Zero"
    crore, value = divmod(value, 10_000_000)
    lakh, value = divmod(value, 100_000)
    thousand, value = divmod(value, 1000)
    hundred, value = divmod(value, 100)
    parts = []
    if crore:
        parts.append(f"{number_in_words(crore)} Crore")
    if lakh:
        parts.append(f"{_two_digits(lakh)} Lakh")
    if thousand:
        parts.append(f"{_two_digits(thousand)} Thousand")
    if hundred:
        parts.append(f"{_ONES[hundred]} Hundred")
    if value:
        parts.append(_two_digits(value))
    return " ".join(parts)


def amount_in_words(paise: int) -> str:
    rupees, remainder = divmod(abs(int(paise)), 100)
    text = f"Rupees {number_in_words(rupees)}"
    if remainder:
        text += f" and {_two_digits(remainder)} Paise"
    return f"{text} Only"


def _display_date(value: str) -> str:
    try:
        return date.fromisoformat(value).strftime("%d %b %Y")
    except (TypeError, ValueError):
        return value or ""


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
    _bill_document(target).build(_bill_story(db, row))
    return target


def generate_all_bills(db: Database, period_id: int) -> Path:
    rows = [
        row for row in db.period_dues(period_id)
        if row["total_due_paise"] > row["total_paid_paise"]
    ]
    if not rows:
        raise ValueError("Every member has fully paid this period")
    target = db.reports_dir / f"All-Bills-{rows[0]['year']:04d}-{rows[0]['month']:02d}.pdf"
    story: list = []
    for index, row in enumerate(rows):
        if index:
            story.append(PageBreak())
        story.extend(_bill_story(db, row))
    _bill_document(target).build(story)
    return target


def _bill_document(target: Path) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        str(target), pagesize=A4, rightMargin=22 * mm, leftMargin=22 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
    )


def _bill_story(db: Database, row) -> list:
    story: list = []
    _header(story, db, f"Monthly Due Bill - {MONTHS[row['month'] - 1]} {row['year']}")
    styles = getSampleStyleSheet()
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontName=FONT, fontSize=10, leading=15)
    story.append(Paragraph(f"Member No.: <b>{row['member_no']}</b>", body))
    story.append(Paragraph(f"Member Name: <b>{escape(row['name'])}</b>", body))
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
    return story


RECEIPT_COMPONENT_LABELS = [
    "Monthly contribution (savings)",
    "Loan principal (EMI)",
    "Interest on loan",
    "Previous due",
    "Late fee",
]


def _text_style(
    name: str, size: float = 8.5, font: str = FONT, color=colors.black, align: int = TA_LEFT,
) -> ParagraphStyle:
    return ParagraphStyle(
        name, fontName=font, fontSize=size, leading=size * 1.3, textColor=color, alignment=align,
    )


def _receipt_heading(society: str, group: str, copy_label: str, inner: float) -> Table:
    heading = Table(
        [
            [Paragraph(escape(society), _text_style("RcSociety", 13, FONT_BOLD, NAVY)),
             Paragraph(copy_label, _text_style("RcCopy", 8, FONT_BOLD, BLUE, TA_RIGHT))],
            [Paragraph(escape(group), _text_style("RcGroup", 8.5, color=MUTED)),
             Paragraph("PAYMENT RECEIPT", _text_style("RcTitle", 11, FONT_BOLD, NAVY, TA_RIGHT))],
        ],
        colWidths=[inner * 0.62, inner * 0.38],
    )
    heading.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 4),
        ("LINEBELOW", (0, -1), (-1, -1), 1.2, NAVY),
    ]))
    return heading


def _receipt_info(details: dict, inner: float) -> Table:
    cell = _text_style("RcCell")
    period = f"{MONTHS[details['month'] - 1]} {details['year']}" if details["month"] else "-"
    info = Table(
        [
            ["Receipt No.", f"UT-{details['transaction_id']:06d}",
             "Receipt date", _display_date(details["transaction_date"])],
            ["Member", Paragraph(f"{details['member_no']} - {escape(details['name'])}", cell),
             "For period", period],
            ["Payment method", details["payment_method"],
             "Reference / UTR", Paragraph(escape(details["reference"] or "-"), cell)],
        ],
        colWidths=[inner * 0.16, inner * 0.36, inner * 0.18, inner * 0.30],
    )
    info.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("FONTNAME", (1, 0), (1, 0), FONT_BOLD),
        ("BACKGROUND", (0, 0), (0, -1), LIGHT),
        ("BACKGROUND", (2, 0), (2, -1), LIGHT),
        ("TEXTCOLOR", (0, 0), (0, -1), NAVY),
        ("TEXTCOLOR", (2, 0), (2, -1), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return info


def _receipt_amounts(details: dict, inner: float) -> Table:
    if details["components"] is not None:
        rows = [
            [label, money(value) if value else "-"]
            for label, value in zip(RECEIPT_COMPONENT_LABELS, details["components"])
        ]
    else:
        rows = [["Payment received (split not recorded)", money(details["amount_paise"])]]
    breakdown = Table(
        [["Payment details", "Amount"], *rows, ["Total received", money(details["amount_paise"])]],
        colWidths=[inner * 0.36, inner * 0.18],
    )
    breakdown.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTNAME", (0, -1), (-1, -1), FONT_BOLD),
        ("FONTSIZE", (0, -1), (-1, -1), 9.5),
        ("BACKGROUND", (0, -1), (-1, -1), LIGHT),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    if not details["has_due"]:
        return breakdown
    balance = details["balance_after_paise"]
    status, status_color = ("PAID IN FULL", GOOD) if balance == 0 else ("BALANCE PENDING", WARN)
    summary = Table(
        [
            ["Period account", ""],
            ["Total due for period", money(details["total_due_paise"])],
            ["Paid earlier", money(details["paid_before_paise"])],
            ["Paid now", money(details["amount_paise"])],
            ["Balance remaining", money(balance)],
            [status, ""],
        ],
        colWidths=[inner * 0.26, inner * 0.16],
    )
    summary.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("SPAN", (0, 0), (-1, 0)),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -2), (-1, -2), FONT_BOLD),
        ("BACKGROUND", (0, -2), (-1, -2), LIGHT),
        ("SPAN", (0, -1), (-1, -1)),
        ("ALIGN", (0, -1), (-1, -1), "CENTER"),
        ("FONTNAME", (0, -1), (-1, -1), FONT_BOLD),
        ("FONTSIZE", (0, -1), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, -1), (-1, -1), status_color),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    layout = Table([[breakdown, "", summary]], colWidths=[inner * 0.54, inner * 0.04, inner * 0.42])
    layout.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return layout


def _receipt_copy(
    details: dict, society: str, group: str, copy_label: str, width: float, printed: str,
) -> Table:
    inner = width - 6 * mm
    words = Table(
        [[Paragraph(
            f"Amount in words: <b>{amount_in_words(details['amount_paise'])}</b>",
            _text_style("RcWords", 9),
        )]],
        colWidths=[inner],
    )
    words.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    signatures = Table(
        [["", "", ""], ["Received by (Treasurer / Secretary)", "", "Member signature"]],
        colWidths=[inner * 0.4, inner * 0.2, inner * 0.4],
        rowHeights=[11 * mm, None],
    )
    signatures.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (-1, -1), MUTED),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LINEABOVE", (0, 1), (0, 1), 0.6, NAVY),
        ("LINEABOVE", (2, 1), (2, 1), 0.6, NAVY),
    ]))
    rows: list[list] = [
        [_receipt_heading(society, group, copy_label, inner)],
        [_receipt_info(details, inner)],
        [_receipt_amounts(details, inner)],
        [words],
    ]
    if details["notes"]:
        rows.append([Paragraph(f"Notes: {escape(details['notes'])}", _text_style("RcNotes", 8))])
    rows.append([signatures])
    rows.append([Paragraph(
        f"Computer-generated receipt from Utthan Society Manager | Printed {printed}",
        _text_style("RcFoot", 7, color=MUTED, align=TA_CENTER),
    )])
    outer = Table(rows, colWidths=[width])
    outer.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.9, NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (0, 0), 3 * mm),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 2.5 * mm),
    ]))
    return outer


def generate_receipt(db: Database, transaction_id: int) -> Path:
    details = db.receipt_details(transaction_id)
    if not details:
        raise ValueError("Receipts are available only for member payments")
    society = db.setting("society_name", "UTHAN CREATIVE SOCIETY")
    group = db.setting("group_name", "")
    target = db.reports_dir / f"Receipt-{transaction_id:06d}-{safe_name(details['name'])}.pdf"
    document = SimpleDocTemplate(
        str(target), pagesize=A4, rightMargin=12 * mm, leftMargin=12 * mm,
        topMargin=10 * mm, bottomMargin=10 * mm,
        title=f"Receipt UT-{transaction_id:06d}", author=society,
    )
    printed = datetime.now().strftime("%d %b %Y, %I:%M %p")
    story = [
        _receipt_copy(details, society, group, "MEMBER COPY", document.width, printed),
        Spacer(1, 4 * mm),
        HRFlowable(width="100%", thickness=0.6, color=GRID, dash=(4, 3), spaceAfter=1 * mm),
        Paragraph("cut here", _text_style("RcCut", 7, color=MUTED, align=TA_CENTER)),
        Spacer(1, 3 * mm),
        _receipt_copy(details, society, group, "OFFICE COPY", document.width, printed),
    ]
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
