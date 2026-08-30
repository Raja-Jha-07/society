from __future__ import annotations

import os
import shutil
import sqlite3
from contextlib import closing, contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

from .seed import (
    DEFAULT_EMI,
    MONTHLY_CONTRIBUTION,
    MONTHLY_INTEREST_RATE,
    OPENING_CONTRIBUTION,
    OPENING_MAINTENANCE_EXPENSE,
    OPENING_MEMBERS,
    OPENING_PERIOD,
    PREVIOUS_INTEREST,
)


def to_paise(value: float | int | str) -> int:
    return round(float(value) * 100)


def from_paise(value: int | None) -> float:
    return (value or 0) / 100


def default_data_dir() -> Path:
    override = os.environ.get("UTTHAN_DATA_DIR")
    if override:
        return Path(override)
    root = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(root) / "UtthanSociety"


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_no INTEGER NOT NULL UNIQUE,
    name TEXT NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    nominee TEXT NOT NULL DEFAULT '',
    join_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Active' CHECK(status IN ('Active', 'Inactive')),
    opening_contribution_paise INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS loans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL REFERENCES members(id),
    loan_type TEXT NOT NULL DEFAULT 'Fresh',
    issue_date TEXT NOT NULL,
    original_amount_paise INTEGER NOT NULL CHECK(original_amount_paise >= 0),
    outstanding_paise INTEGER NOT NULL CHECK(outstanding_paise >= 0),
    monthly_emi_paise INTEGER NOT NULL CHECK(monthly_emi_paise >= 0),
    monthly_interest_bp INTEGER NOT NULL CHECK(monthly_interest_bp >= 0),
    status TEXT NOT NULL CHECK(status IN ('Open', 'Closed')),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS periods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL CHECK(month BETWEEN 1 AND 12),
    status TEXT NOT NULL DEFAULT 'Open' CHECK(status IN ('Open', 'Closed')),
    generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at TEXT,
    UNIQUE(year, month)
);

CREATE TABLE IF NOT EXISTS dues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_id INTEGER NOT NULL REFERENCES periods(id),
    member_id INTEGER NOT NULL REFERENCES members(id),
    contribution_due_paise INTEGER NOT NULL DEFAULT 0,
    opening_loan_paise INTEGER NOT NULL DEFAULT 0,
    emi_due_paise INTEGER NOT NULL DEFAULT 0,
    interest_due_paise INTEGER NOT NULL DEFAULT 0,
    arrears_due_paise INTEGER NOT NULL DEFAULT 0,
    late_fee_paise INTEGER NOT NULL DEFAULT 0,
    contribution_paid_paise INTEGER NOT NULL DEFAULT 0,
    principal_paid_paise INTEGER NOT NULL DEFAULT 0,
    interest_paid_paise INTEGER NOT NULL DEFAULT 0,
    arrears_paid_paise INTEGER NOT NULL DEFAULT 0,
    late_fee_paid_paise INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'Unpaid' CHECK(status IN ('Unpaid', 'Part-paid', 'Paid')),
    notes TEXT NOT NULL DEFAULT '',
    UNIQUE(period_id, member_id)
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_date TEXT NOT NULL,
    member_id INTEGER REFERENCES members(id),
    due_id INTEGER REFERENCES dues(id),
    loan_id INTEGER REFERENCES loans(id),
    transaction_type TEXT NOT NULL,
    amount_paise INTEGER NOT NULL,
    payment_method TEXT NOT NULL DEFAULT 'Cash',
    reference TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expense_date TEXT NOT NULL,
    category TEXT NOT NULL,
    amount_paise INTEGER NOT NULL CHECK(amount_paise >= 0),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS opening_funds (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    previous_interest_paise INTEGER NOT NULL DEFAULT 0,
    bank_balance_paise INTEGER NOT NULL DEFAULT 0,
    cash_balance_paise INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    details TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_loans_member ON loans(member_id);
CREATE INDEX IF NOT EXISTS idx_dues_period ON dues(period_id);
CREATE INDEX IF NOT EXISTS idx_transactions_member ON transactions(member_id);
"""


class Database:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or default_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir = self.data_dir / "Reports"
        self.backups_dir = self.data_dir / "Backups"
        self.reports_dir.mkdir(exist_ok=True)
        self.backups_dir.mkdir(exist_ok=True)
        self.path = self.data_dir / "utthan_society.db"
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            count = connection.execute("SELECT COUNT(*) FROM members").fetchone()[0]
            if count == 0:
                self._seed_opening_balances(connection)

    def _seed_opening_balances(self, connection: sqlite3.Connection) -> None:
        settings = {
            "society_name": "UTHAN CREATIVE SOCIETY",
            "group_name": "UTTHAN SELF HELP GROUP",
            "monthly_contribution": str(to_paise(MONTHLY_CONTRIBUTION)),
            "monthly_interest_bp": str(round(MONTHLY_INTEREST_RATE * 100)),
            "default_emi": str(to_paise(DEFAULT_EMI)),
            "currency": "INR",
        }
        connection.executemany(
            "INSERT INTO settings(key, value) VALUES(?, ?)", settings.items()
        )
        connection.execute(
            "INSERT INTO opening_funds(id, previous_interest_paise, notes) VALUES(1, ?, ?)",
            (to_paise(PREVIOUS_INTEREST), "Opening value from August 2026 PDF"),
        )
        for number, name, outstanding, lifetime, kind, loan_month, _, _ in OPENING_MEMBERS:
            cursor = connection.execute(
                """INSERT INTO members(member_no, name, join_date, opening_contribution_paise, notes)
                   VALUES(?, ?, ?, ?, ?)""",
                (
                    number,
                    name,
                    "2022-03-01",
                    to_paise(OPENING_CONTRIBUTION),
                    "Opening balance imported from August 2026 due list",
                ),
            )
            if outstanding:
                connection.execute(
                    """INSERT INTO loans(member_id, loan_type, issue_date,
                       original_amount_paise, outstanding_paise, monthly_emi_paise,
                       monthly_interest_bp, status, notes)
                       VALUES(?, ?, ?, ?, ?, ?, ?, 'Open', ?)""",
                    (
                        cursor.lastrowid,
                        kind or "Fresh",
                        f"{loan_month}-01" if loan_month else "2026-08-01",
                        to_paise(max(lifetime, outstanding)),
                        to_paise(outstanding),
                        to_paise(DEFAULT_EMI),
                        round(MONTHLY_INTEREST_RATE * 100),
                        f"Lifetime loan total in source PDF: Rs {lifetime:,.0f}",
                    ),
                )
        period_id = connection.execute(
            "INSERT INTO periods(year, month) VALUES(?, ?)", OPENING_PERIOD
        ).lastrowid
        member_map = {
            row["member_no"]: row["id"]
            for row in connection.execute("SELECT id, member_no FROM members")
        }
        for number, _, outstanding, _, _, _, arrears, late_fee in OPENING_MEMBERS:
            emi = min(DEFAULT_EMI, outstanding) if outstanding else 0
            interest = round(outstanding * MONTHLY_INTEREST_RATE / 100)
            connection.execute(
                """INSERT INTO dues(period_id, member_id, contribution_due_paise,
                   opening_loan_paise, emi_due_paise, interest_due_paise,
                   arrears_due_paise, late_fee_paise, notes)
                   VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    period_id,
                    member_map[number],
                    to_paise(MONTHLY_CONTRIBUTION),
                    to_paise(outstanding),
                    to_paise(emi),
                    to_paise(interest),
                    to_paise(arrears),
                    to_paise(late_fee),
                    "Opening due imported from August 2026 PDF",
                ),
            )
        connection.execute(
            "INSERT INTO expenses(expense_date, category, amount_paise, notes) VALUES(?, ?, ?, ?)",
            (
                "2026-08-01",
                "Maintenance",
                to_paise(OPENING_MAINTENANCE_EXPENSE),
                "Opening maintenance expense shown in August 2026 PDF",
            ),
        )
        self._audit(connection, "IMPORT", "database", None, "Imported August 2026 opening balances")

    @staticmethod
    def _audit(
        connection: sqlite3.Connection,
        action: str,
        entity_type: str,
        entity_id: int | None,
        details: str,
    ) -> None:
        connection.execute(
            "INSERT INTO audit_log(action, entity_type, entity_id, details) VALUES(?, ?, ?, ?)",
            (action, entity_type, entity_id, details),
        )

    def setting(self, key: str, default: str = "") -> str:
        with self.connect() as connection:
            row = connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row[0] if row else default

    def save_settings(self, values: dict[str, str]) -> None:
        with self.connect() as connection:
            connection.executemany(
                """INSERT INTO settings(key, value) VALUES(?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                values.items(),
            )
            self._audit(connection, "UPDATE", "settings", None, ", ".join(values))

    def list_members(self, include_inactive: bool = False) -> list[sqlite3.Row]:
        where = "" if include_inactive else "WHERE m.status = 'Active'"
        with self.connect() as connection:
            return connection.execute(
                f"""SELECT m.*,
                    m.opening_contribution_paise + COALESCE((
                        SELECT SUM(d.contribution_paid_paise) FROM dues d WHERE d.member_id = m.id
                    ), 0) AS contribution_balance_paise,
                    COALESCE((SELECT SUM(l.outstanding_paise) FROM loans l
                        WHERE l.member_id = m.id AND l.status = 'Open'), 0) AS loan_outstanding_paise
                    FROM members m {where} ORDER BY m.member_no"""
            ).fetchall()

    def member(self, member_id: int) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(
                """SELECT m.*,
                    m.opening_contribution_paise + COALESCE((
                        SELECT SUM(d.contribution_paid_paise) FROM dues d WHERE d.member_id = m.id
                    ), 0) AS contribution_balance_paise,
                    COALESCE((SELECT SUM(l.outstanding_paise) FROM loans l
                        WHERE l.member_id = m.id AND l.status = 'Open'), 0) AS loan_outstanding_paise
                    FROM members m WHERE m.id = ?""",
                (member_id,),
            ).fetchone()

    def add_member(
        self,
        name: str,
        phone: str = "",
        address: str = "",
        nominee: str = "",
        join_date: str | None = None,
        opening_contribution: float = 0,
        notes: str = "",
    ) -> int:
        if not name.strip():
            raise ValueError("Member name is required")
        with self.connect() as connection:
            next_number = connection.execute(
                "SELECT COALESCE(MAX(member_no), 0) + 1 FROM members"
            ).fetchone()[0]
            cursor = connection.execute(
                """INSERT INTO members(member_no, name, phone, address, nominee,
                   join_date, opening_contribution_paise, notes)
                   VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    next_number,
                    name.strip(),
                    phone.strip(),
                    address.strip(),
                    nominee.strip(),
                    join_date or date.today().isoformat(),
                    to_paise(opening_contribution),
                    notes.strip(),
                ),
            )
            self._audit(connection, "CREATE", "member", cursor.lastrowid, name.strip())
            return int(cursor.lastrowid)

    def update_member_status(self, member_id: int, status: str) -> None:
        if status not in {"Active", "Inactive"}:
            raise ValueError("Invalid member status")
        with self.connect() as connection:
            connection.execute("UPDATE members SET status = ? WHERE id = ?", (status, member_id))
            self._audit(connection, "UPDATE", "member", member_id, f"Status: {status}")

    def list_loans(self, open_only: bool = False) -> list[sqlite3.Row]:
        condition = "WHERE l.status = 'Open'" if open_only else ""
        with self.connect() as connection:
            return connection.execute(
                f"""SELECT l.*, m.member_no, m.name FROM loans l
                    JOIN members m ON m.id = l.member_id {condition}
                    ORDER BY CASE l.status WHEN 'Open' THEN 0 ELSE 1 END, l.issue_date DESC"""
            ).fetchall()

    def issue_loan(
        self,
        member_id: int,
        amount: float,
        issue_date: str,
        loan_type: str,
        emi: float,
        monthly_interest_rate: float,
        notes: str = "",
    ) -> int:
        if amount <= 0 or emi < 0 or monthly_interest_rate < 0:
            raise ValueError("Loan values must not be negative and amount must be positive")
        amount_paise = to_paise(amount)
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO loans(member_id, loan_type, issue_date, original_amount_paise,
                   outstanding_paise, monthly_emi_paise, monthly_interest_bp, status, notes)
                   VALUES(?, ?, ?, ?, ?, ?, ?, 'Open', ?)""",
                (
                    member_id,
                    loan_type,
                    issue_date,
                    amount_paise,
                    amount_paise,
                    to_paise(emi),
                    round(monthly_interest_rate * 100),
                    notes.strip(),
                ),
            )
            connection.execute(
                """INSERT INTO transactions(transaction_date, member_id, loan_id,
                   transaction_type, amount_paise, notes) VALUES(?, ?, ?, 'Loan disbursement', ?, ?)""",
                (issue_date, member_id, cursor.lastrowid, -amount_paise, notes.strip()),
            )
            self._audit(connection, "CREATE", "loan", cursor.lastrowid, f"Rs {amount:,.2f}")
            return int(cursor.lastrowid)

    def list_periods(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return connection.execute(
                "SELECT * FROM periods ORDER BY year DESC, month DESC"
            ).fetchall()

    def period(self, year: int, month: int) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(
                "SELECT * FROM periods WHERE year = ? AND month = ?", (year, month)
            ).fetchone()

    def generate_period(self, year: int, month: int) -> int:
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT id FROM periods WHERE year = ? AND month = ?", (year, month)
            ).fetchone()
            if existing:
                return int(existing[0])
            period_id = connection.execute(
                "INSERT INTO periods(year, month) VALUES(?, ?)", (year, month)
            ).lastrowid
            contribution = int(self._setting_in_connection(connection, "monthly_contribution", "50000"))
            default_rate = int(self._setting_in_connection(connection, "monthly_interest_bp", "150"))
            members = connection.execute(
                "SELECT id FROM members WHERE status = 'Active' ORDER BY member_no"
            ).fetchall()
            for member in members:
                loans = connection.execute(
                    "SELECT * FROM loans WHERE member_id = ? AND status = 'Open'",
                    (member["id"],),
                ).fetchall()
                opening = sum(row["outstanding_paise"] for row in loans)
                emi = sum(min(row["monthly_emi_paise"], row["outstanding_paise"]) for row in loans)
                interest = sum(
                    round(row["outstanding_paise"] * row["monthly_interest_bp"] / 10_000)
                    for row in loans
                )
                # A loan can intentionally use its own rate; the setting is retained for new loans.
                _ = default_rate
                prior = connection.execute(
                    """SELECT d.* FROM dues d JOIN periods p ON p.id = d.period_id
                       WHERE d.member_id = ? AND (p.year < ? OR (p.year = ? AND p.month < ?))
                       ORDER BY p.year DESC, p.month DESC LIMIT 1""",
                    (member["id"], year, year, month),
                ).fetchone()
                arrears = self._due_balance(prior) if prior else 0
                connection.execute(
                    """INSERT INTO dues(period_id, member_id, contribution_due_paise,
                       opening_loan_paise, emi_due_paise, interest_due_paise, arrears_due_paise)
                       VALUES(?, ?, ?, ?, ?, ?, ?)""",
                    (period_id, member["id"], contribution, opening, emi, interest, arrears),
                )
            self._audit(connection, "CREATE", "period", period_id, f"{year:04d}-{month:02d}")
            return int(period_id)

    @staticmethod
    def _setting_in_connection(connection: sqlite3.Connection, key: str, default: str) -> str:
        row = connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    @staticmethod
    def _due_balance(row: sqlite3.Row | None) -> int:
        if not row:
            return 0
        due = (
            row["contribution_due_paise"]
            + row["emi_due_paise"]
            + row["interest_due_paise"]
            + row["arrears_due_paise"]
            + row["late_fee_paise"]
        )
        paid = (
            row["contribution_paid_paise"]
            + row["principal_paid_paise"]
            + row["interest_paid_paise"]
            + row["arrears_paid_paise"]
            + row["late_fee_paid_paise"]
        )
        return max(0, due - paid)

    def period_dues(self, period_id: int) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return connection.execute(
                """SELECT d.*, m.member_no, m.name, p.year, p.month, p.status AS period_status,
                    (d.contribution_due_paise + d.emi_due_paise + d.interest_due_paise +
                     d.arrears_due_paise + d.late_fee_paise) AS total_due_paise,
                    (d.contribution_paid_paise + d.principal_paid_paise + d.interest_paid_paise +
                     d.arrears_paid_paise + d.late_fee_paid_paise) AS total_paid_paise
                    FROM dues d JOIN members m ON m.id = d.member_id
                    JOIN periods p ON p.id = d.period_id
                    WHERE d.period_id = ? ORDER BY m.member_no""",
                (period_id,),
            ).fetchall()

    def due(self, due_id: int) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(
                """SELECT d.*, m.member_no, m.name, p.year, p.month,
                    (d.contribution_due_paise + d.emi_due_paise + d.interest_due_paise +
                     d.arrears_due_paise + d.late_fee_paise) AS total_due_paise,
                    (d.contribution_paid_paise + d.principal_paid_paise + d.interest_paid_paise +
                     d.arrears_paid_paise + d.late_fee_paid_paise) AS total_paid_paise
                    FROM dues d JOIN members m ON m.id = d.member_id
                    JOIN periods p ON p.id = d.period_id WHERE d.id = ?""",
                (due_id,),
            ).fetchone()

    def record_payment(
        self,
        due_id: int,
        contribution: float,
        principal: float,
        interest: float,
        arrears: float,
        late_fee: float,
        payment_date: str,
        payment_method: str,
        reference: str = "",
        notes: str = "",
    ) -> int:
        values = [contribution, principal, interest, arrears, late_fee]
        if any(value < 0 for value in values) or sum(values) <= 0:
            raise ValueError("Payment must be greater than zero")
        paise = [to_paise(value) for value in values]
        with self.connect() as connection:
            due = connection.execute(
                """SELECT d.*, p.status AS period_status FROM dues d
                   JOIN periods p ON p.id = d.period_id WHERE d.id = ?""",
                (due_id,),
            ).fetchone()
            if not due:
                raise ValueError("Due record not found")
            if due["period_status"] == "Closed":
                raise ValueError("Closed periods cannot be changed")
            limits = [
                due["contribution_due_paise"] - due["contribution_paid_paise"],
                due["emi_due_paise"] - due["principal_paid_paise"],
                due["interest_due_paise"] - due["interest_paid_paise"],
                due["arrears_due_paise"] - due["arrears_paid_paise"],
                due["late_fee_paise"] - due["late_fee_paid_paise"],
            ]
            if any(value > max(0, limit) for value, limit in zip(paise, limits)):
                raise ValueError("A payment component exceeds its outstanding due")
            connection.execute(
                """UPDATE dues SET
                    contribution_paid_paise = contribution_paid_paise + ?,
                    principal_paid_paise = principal_paid_paise + ?,
                    interest_paid_paise = interest_paid_paise + ?,
                    arrears_paid_paise = arrears_paid_paise + ?,
                    late_fee_paid_paise = late_fee_paid_paise + ?
                    WHERE id = ?""",
                (*paise, due_id),
            )
            principal_left = paise[1]
            loans = connection.execute(
                "SELECT * FROM loans WHERE member_id = ? AND status = 'Open' ORDER BY issue_date, id",
                (due["member_id"],),
            ).fetchall()
            for loan in loans:
                if principal_left <= 0:
                    break
                applied = min(principal_left, loan["outstanding_paise"])
                new_balance = loan["outstanding_paise"] - applied
                connection.execute(
                    "UPDATE loans SET outstanding_paise = ?, status = ? WHERE id = ?",
                    (new_balance, "Closed" if new_balance == 0 else "Open", loan["id"]),
                )
                principal_left -= applied
            total = sum(paise)
            cursor = connection.execute(
                """INSERT INTO transactions(transaction_date, member_id, due_id,
                   transaction_type, amount_paise, payment_method, reference, notes)
                   VALUES(?, ?, ?, 'Member payment', ?, ?, ?, ?)""",
                (
                    payment_date,
                    due["member_id"],
                    due_id,
                    total,
                    payment_method,
                    reference.strip(),
                    notes.strip(),
                ),
            )
            updated = connection.execute("SELECT * FROM dues WHERE id = ?", (due_id,)).fetchone()
            balance = self._due_balance(updated)
            total_due = (
                updated["contribution_due_paise"] + updated["emi_due_paise"]
                + updated["interest_due_paise"] + updated["arrears_due_paise"]
                + updated["late_fee_paise"]
            )
            if balance == 0:
                status = "Paid"
            elif balance < total_due:
                status = "Part-paid"
            else:
                status = "Unpaid"
            connection.execute("UPDATE dues SET status = ? WHERE id = ?", (status, due_id))
            self._audit(connection, "PAYMENT", "due", due_id, f"Rs {total / 100:,.2f}")
            return int(cursor.lastrowid)

    def add_expense(self, expense_date: str, category: str, amount: float, notes: str = "") -> int:
        if amount <= 0 or not category.strip():
            raise ValueError("Category and a positive amount are required")
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO expenses(expense_date, category, amount_paise, notes) VALUES(?, ?, ?, ?)",
                (expense_date, category.strip(), to_paise(amount), notes.strip()),
            )
            self._audit(connection, "CREATE", "expense", cursor.lastrowid, category.strip())
            return int(cursor.lastrowid)

    def list_expenses(self) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return connection.execute(
                "SELECT * FROM expenses ORDER BY expense_date DESC, id DESC"
            ).fetchall()

    def dashboard(self) -> dict[str, int]:
        with self.connect() as connection:
            active_members = connection.execute(
                "SELECT COUNT(*) FROM members WHERE status = 'Active'"
            ).fetchone()[0]
            contributions = connection.execute(
                """SELECT COALESCE(SUM(opening_contribution_paise), 0) +
                   COALESCE((SELECT SUM(contribution_paid_paise) FROM dues), 0) FROM members"""
            ).fetchone()[0]
            loans = connection.execute(
                "SELECT COALESCE(SUM(outstanding_paise), 0) FROM loans WHERE status = 'Open'"
            ).fetchone()[0]
            collected_income = connection.execute(
                "SELECT COALESCE(SUM(interest_paid_paise + late_fee_paid_paise), 0) FROM dues"
            ).fetchone()[0]
            opening_interest = connection.execute(
                "SELECT previous_interest_paise FROM opening_funds WHERE id = 1"
            ).fetchone()[0]
            expenses = connection.execute(
                "SELECT COALESCE(SUM(amount_paise), 0) FROM expenses"
            ).fetchone()[0]
            latest = connection.execute(
                "SELECT id, year, month FROM periods ORDER BY year DESC, month DESC LIMIT 1"
            ).fetchone()
            period_due = period_paid = 0
            if latest:
                rows = connection.execute("SELECT * FROM dues WHERE period_id = ?", (latest["id"],)).fetchall()
                period_due = sum(
                    row["contribution_due_paise"] + row["emi_due_paise"]
                    + row["interest_due_paise"] + row["arrears_due_paise"]
                    + row["late_fee_paise"] for row in rows
                )
                period_paid = sum(
                    row["contribution_paid_paise"] + row["principal_paid_paise"]
                    + row["interest_paid_paise"] + row["arrears_paid_paise"]
                    + row["late_fee_paid_paise"] for row in rows
                )
            corpus = contributions + opening_interest + collected_income - expenses
            return {
                "active_members": active_members,
                "contributions": contributions,
                "loan_outstanding": loans,
                "interest_earned": opening_interest + collected_income,
                "expenses": expenses,
                "corpus": corpus,
                "available_funds": corpus - loans,
                "period_due": period_due,
                "period_paid": period_paid,
                "latest_year": latest["year"] if latest else 0,
                "latest_month": latest["month"] if latest else 0,
            }

    def transactions(self, limit: int = 500) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return connection.execute(
                """SELECT t.*, m.name FROM transactions t LEFT JOIN members m ON m.id = t.member_id
                   ORDER BY t.transaction_date DESC, t.id DESC LIMIT ?""",
                (limit,),
            ).fetchall()

    def close_period(self, period_id: int) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE periods SET status = 'Closed', closed_at = ? WHERE id = ?",
                (datetime.now().isoformat(timespec="seconds"), period_id),
            )
            self._audit(connection, "CLOSE", "period", period_id, "Period closed")

    def backup(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.backups_dir / f"utthan-backup-{stamp}.db"
        with closing(sqlite3.connect(self.path)) as source, closing(sqlite3.connect(target)) as destination:
            source.backup(destination)
        return target

    def restore(self, source: Path) -> None:
        if not source.exists():
            raise ValueError("Backup file does not exist")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safety = self.backups_dir / f"before-restore-{stamp}.db"
        shutil.copy2(self.path, safety)
        with closing(sqlite3.connect(source)) as backup, closing(sqlite3.connect(self.path)) as destination:
            backup.backup(destination)
