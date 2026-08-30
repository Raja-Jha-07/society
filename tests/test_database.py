import tempfile
import unittest
from pathlib import Path

from src.utthan.database import Database, from_paise


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_pdf_opening_balances_match_source_totals(self) -> None:
        members = self.db.list_members()
        self.assertEqual(len(members), 60)
        self.assertEqual(sum(row["opening_contribution_paise"] for row in members), 159_000_000)
        self.assertEqual(sum(row["loan_outstanding_paise"] for row in members), 107_700_000)

        period = self.db.period(2026, 8)
        self.assertIsNotNone(period)
        dues = self.db.period_dues(period["id"])
        self.assertEqual(sum(row["contribution_due_paise"] for row in dues), 3_000_000)
        self.assertEqual(sum(row["emi_due_paise"] for row in dues), 3_700_000)
        self.assertEqual(sum(row["interest_due_paise"] for row in dues), 1_615_500)
        self.assertEqual(sum(row["arrears_due_paise"] for row in dues), 703_000)
        self.assertEqual(sum(row["late_fee_paise"] for row in dues), 27_000)

    def test_interest_is_one_and_half_percent_of_opening_balance(self) -> None:
        period = self.db.period(2026, 8)
        rows = self.db.period_dues(period["id"])
        abhimanu = next(row for row in rows if row["name"] == "Abhimanu Pandit")
        self.assertEqual(from_paise(abhimanu["opening_loan_paise"]), 39_000)
        self.assertEqual(from_paise(abhimanu["interest_due_paise"]), 585)
        self.assertEqual(from_paise(abhimanu["total_due_paise"]), 2_085)

    def test_full_payment_updates_savings_and_loan(self) -> None:
        period = self.db.period(2026, 8)
        row = next(row for row in self.db.period_dues(period["id"])
                   if row["name"] == "Abhimanu Pandit")
        transaction_id = self.db.record_payment(
            row["id"], 500, 1000, 585, 0, 0, "2026-08-30", "Cash"
        )
        self.assertGreater(transaction_id, 0)
        updated_due = self.db.due(row["id"])
        self.assertEqual(updated_due["status"], "Paid")
        member = self.db.member(row["member_id"])
        self.assertEqual(from_paise(member["contribution_balance_paise"]), 27_000)
        self.assertEqual(from_paise(member["loan_outstanding_paise"]), 38_000)

    def test_unpaid_amount_carries_to_next_period(self) -> None:
        august = self.db.period(2026, 8)
        siddharth = next(row for row in self.db.period_dues(august["id"])
                         if row["name"] == "Siddharth Kumar")
        september_id = self.db.generate_period(2026, 9)
        september = next(row for row in self.db.period_dues(september_id)
                         if row["name"] == "Siddharth Kumar")
        self.assertEqual(september["arrears_due_paise"], siddharth["total_due_paise"])

    def test_backup_creates_valid_copy(self) -> None:
        path = self.db.backup()
        self.assertTrue(path.exists())
        copy = Database(path.parent / "verify")
        copy.restore(path)
        self.assertEqual(len(copy.list_members()), 60)


if __name__ == "__main__":
    unittest.main()
