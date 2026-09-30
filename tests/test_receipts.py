import tempfile
import unittest
from pathlib import Path

from src.utthan.database import PAYMENT_COMPONENT_COLUMNS, Database
from src.utthan.reports import amount_in_words, generate_all_bills, generate_receipt


class ReceiptAndAutomationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name))
        period = self.db.period(2026, 8)
        self.period_id = period["id"]
        self.due = next(row for row in self.db.period_dues(self.period_id)
                        if row["name"] == "Abhimanu Pandit")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_receipt_shows_this_payment_split_and_running_balance(self) -> None:
        first = self.db.record_payment(self.due["id"], 500, 1000, 0, 0, 0, "2026-08-10", "UPI")
        second = self.db.record_payment(self.due["id"], 0, 0, 585, 0, 0, "2026-08-25", "Cash")

        first_details = self.db.receipt_details(first)
        self.assertEqual(first_details["components"], [50_000, 100_000, 0, 0, 0])
        self.assertEqual(first_details["paid_before_paise"], 0)
        self.assertEqual(first_details["balance_after_paise"], 58_500)

        second_details = self.db.receipt_details(second)
        self.assertEqual(second_details["components"], [0, 0, 58_500, 0, 0])
        self.assertEqual(second_details["paid_before_paise"], 150_000)
        self.assertEqual(second_details["balance_after_paise"], 0)

    def test_receipt_uses_due_split_for_payments_saved_by_previous_version(self) -> None:
        transaction_id = self.db.record_payment(self.due["id"], 500, 1000, 585, 0, 0, "2026-08-10", "Cash")
        with self.db.connect() as connection:
            assignments = ", ".join(f"{column} = 0" for column in PAYMENT_COMPONENT_COLUMNS)
            connection.execute(f"UPDATE transactions SET {assignments} WHERE id = ?", (transaction_id,))
        details = self.db.receipt_details(transaction_id)
        self.assertEqual(details["components"], [50_000, 100_000, 58_500, 0, 0])

    def test_existing_database_is_upgraded_in_place(self) -> None:
        with self.db.connect() as connection:
            for column in PAYMENT_COMPONENT_COLUMNS:
                connection.execute(f"ALTER TABLE transactions DROP COLUMN {column}")
        upgraded = Database(Path(self.temp.name))
        with upgraded.connect() as connection:
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(transactions)")}
        self.assertTrue(set(PAYMENT_COMPONENT_COLUMNS).issubset(columns))
        self.assertEqual(len(upgraded.list_members()), 60)

    def test_receipt_and_all_bills_pdfs_are_created(self) -> None:
        transaction_id = self.db.record_payment(self.due["id"], 500, 0, 0, 0, 0, "2026-08-10", "Cash")
        receipt = generate_receipt(self.db, transaction_id)
        self.assertGreater(receipt.stat().st_size, 0)
        bills = generate_all_bills(self.db, self.period_id)
        self.assertGreater(bills.stat().st_size, 0)

    def test_receipt_is_refused_for_loan_disbursement(self) -> None:
        member = self.db.list_members()[0]
        self.db.issue_loan(member["id"], 5000, "2026-08-05", "Fresh", 1000, 1.5)
        disbursement = self.db.transactions(limit=1)[0]
        with self.assertRaises(ValueError):
            generate_receipt(self.db, disbursement["id"])

    def test_amount_in_words_uses_indian_numbering(self) -> None:
        self.assertEqual(amount_in_words(208_500), "Rupees Two Thousand Eighty Five Only")
        self.assertEqual(amount_in_words(15_000_000), "Rupees One Lakh Fifty Thousand Only")
        self.assertEqual(amount_in_words(10_000_050), "Rupees One Lakh and Fifty Paise Only")
        self.assertEqual(
            amount_in_words(1_234_567_800),
            "Rupees One Crore Twenty Three Lakh Forty Five Thousand Six Hundred Seventy Eight Only",
        )

    def test_automatic_backup_runs_once_a_day_and_keeps_recent_copies(self) -> None:
        first = self.db.auto_backup()
        self.assertIsNotNone(first)
        self.assertIsNone(self.db.auto_backup())
        self.assertEqual(self.db.latest_auto_backup(), first)

        folder = self.db.auto_backups_dir
        for day in range(1, 6):
            (folder / f"utthan-auto-202601{day:02d}-090000.db").write_bytes(b"old")
        first.unlink()
        self.db.auto_backup(keep=3)
        remaining = sorted(path.name for path in folder.glob("utthan-auto-*.db"))
        self.assertEqual(len(remaining), 3)
        self.assertNotIn("utthan-auto-20260101-090000.db", remaining)


if __name__ == "__main__":
    unittest.main()
