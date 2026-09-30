import io
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from werkzeug.security import generate_password_hash

from src.utthan.web import create_app


class WebPortalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(
            Path(self.temp.name),
            {"TESTING": True, "SECRET_KEY": "test-secret", "SESSION_COOKIE_SECURE": False},
        )
        self.client = self.app.test_client()
        self.db = self.app.extensions["utthan_db"]

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def token(response) -> str:
        match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
        if not match:
            raise AssertionError("CSRF token not found")
        return match.group(1).decode()

    def setup_admin(self) -> None:
        response = self.client.get("/setup")
        response = self.client.post(
            "/setup",
            data={
                "csrf_token": self.token(response),
                "username": "admin",
                "password": "StrongPass123",
                "confirm_password": "StrongPass123",
            },
        )
        self.assertEqual(response.status_code, 302)

    def login(self, username: str, password: str) -> None:
        response = self.client.get("/login")
        response = self.client.post(
            "/login",
            data={"csrf_token": self.token(response), "username": username, "password": password},
        )
        self.assertEqual(response.status_code, 302)

    def test_first_setup_and_admin_login(self) -> None:
        self.assertEqual(self.client.get("/").headers["Location"], "/setup")
        self.setup_admin()
        account = self.db.user_by_username("admin")
        self.assertIsNotNone(account)
        self.assertNotEqual(account["password_hash"], "StrongPass123")

        self.login("admin", "StrongPass123")
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Financial overview", response.data)

    def test_all_admin_pages_render(self) -> None:
        self.setup_admin()
        self.login("admin", "StrongPass123")
        member = self.db.list_members()[0]
        for path in (
            "/admin",
            "/admin/members",
            f"/admin/members/{member['id']}",
            "/admin/users",
            "/admin/loans",
            "/admin/dues",
            "/admin/cashbook",
            "/admin/activity",
            "/admin/reports",
            "/admin/settings",
            "/password",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
        history = self.client.get(f"/admin/members/{member['id']}")
        self.assertIn(b"Complete membership and financial history", history.data)
        self.assertIn(member["name"].encode(), history.data)

    def admin_session(self) -> None:
        self.setup_admin()
        self.login("admin", "StrongPass123")

    def post(self, path: str, data: dict | None = None, page: str = "/admin/users"):
        token = self.token(self.client.get(page))
        return self.client.post(path, data={"csrf_token": token, **(data or {})})

    @staticmethod
    def slip_credentials(response) -> list[tuple[str, str]]:
        values = re.findall(rb'<dd class="credential">([^<]+)</dd>', response.data)
        return [(values[i].decode(), values[i + 1].decode()) for i in range(0, len(values), 2)]

    def test_admin_generates_member_login_and_member_signs_in(self) -> None:
        self.admin_session()
        member = self.db.list_members()[4]
        response = self.post(f"/admin/members/{member['id']}/login", page="/admin/members")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        [(username, password)] = self.slip_credentials(response)
        self.assertEqual(username, f"member{member['member_no']}")
        self.assertIsNone(re.search(r"\s", password))
        self.assertNotEqual(self.db.user_by_username(username)["password_hash"], password)

        again = self.post(f"/admin/members/{member['id']}/login", page="/admin/members")
        self.assertEqual(again.status_code, 302)

        self.client.post("/logout", data={"csrf_token": self.token(self.client.get("/admin"))})
        self.login(username, password)
        self.assertEqual(self.client.get("/portal").headers["Location"], "/password")
        change = self.client.get("/password")
        self.client.post("/password", data={
            "csrf_token": self.token(change), "current_password": password,
            "password": "MyOwnPass123", "confirm_password": "MyOwnPass123",
        })
        portal = self.client.get("/portal")
        self.assertEqual(portal.status_code, 200)
        self.assertIn(member["name"].encode(), portal.data)

    def test_bulk_logins_as_slips_and_csv_and_reset(self) -> None:
        self.admin_session()
        slips = self.post("/admin/users/provision", {"output": "slips"})
        self.assertEqual(slips.status_code, 200)
        self.assertEqual(len(self.slip_credentials(slips)), 60)
        self.assertEqual(self.db.members_without_users(), [])

        new_member = self.db.add_member("New Member")
        csv_response = self.post("/admin/users/provision", {"output": "csv"})
        self.assertEqual(csv_response.mimetype, "text/csv")
        self.assertIn(b"New Member", csv_response.data)

        account = self.db.user_for_member(new_member)
        old_hash = account["password_hash"]
        reset = self.post(f"/admin/users/{account['id']}/reset")
        [(username, _)] = self.slip_credentials(reset)
        self.assertEqual(username, account["username"])
        self.assertNotEqual(self.db.user(account["id"])["password_hash"], old_hash)

    def test_admin_can_create_another_administrator(self) -> None:
        self.admin_session()
        response = self.post("/admin/users", {"role": "admin", "username": "treasurer"})
        [(username, _)] = self.slip_credentials(response)
        self.assertEqual(username, "treasurer")
        self.assertEqual(self.db.user_by_username("treasurer")["role"], "admin")

    def test_remote_setup_requires_setup_token(self) -> None:
        remote = {"REMOTE_ADDR": "203.0.113.9"}
        self.assertEqual(self.client.get("/setup", environ_base=remote).status_code, 403)
        proxied = self.client.get("/setup", headers={"X-Forwarded-For": "203.0.113.9"})
        self.assertEqual(proxied.status_code, 403)
        with mock.patch.dict(os.environ, {"UTTHAN_SETUP_TOKEN": "correct-code"}):
            page = self.client.get("/setup", environ_base=remote)
            self.assertEqual(page.status_code, 200)
            base = {
                "csrf_token": self.token(page), "username": "admin",
                "password": "StrongPass123", "confirm_password": "StrongPass123",
            }
            self.client.post("/setup", data={**base, "setup_token": "wrong"}, environ_base=remote)
            self.assertEqual(self.db.account_count(), 0)
            self.client.post("/setup", data={**base, "setup_token": "correct-code"}, environ_base=remote)
            self.assertEqual(self.db.account_count(), 1)

    def test_payment_shows_receipt_link_and_close_period_backs_up(self) -> None:
        self.admin_session()
        period = self.db.period(2026, 8)
        due = next(row for row in self.db.period_dues(period["id"]) if row["name"] == "Abhimanu Pandit")
        page = self.client.get(f"/admin/dues/{due['id']}/payment")
        response = self.client.post(f"/admin/dues/{due['id']}/payment", data={
            "csrf_token": self.token(page), "contribution": "500", "principal": "1000",
            "interest": "585", "arrears": "0", "late_fee": "0",
            "payment_date": "2026-08-20", "payment_method": "UPI",
        }, follow_redirects=True)
        self.assertIn(b"Download receipt", response.data)
        transaction = self.db.member_transactions(due["member_id"])[0]
        receipt = self.client.get(f"/receipt/{transaction['id']}")
        self.assertEqual(receipt.mimetype, "application/pdf")
        receipt.close()
        bills = self.client.get(f"/admin/reports/all-bills/{period['id']}.pdf")
        self.assertEqual(bills.mimetype, "application/pdf")
        bills.close()

        backups_before = len(list(self.db.backups_dir.glob("utthan-backup-*.db")))
        self.post(f"/admin/periods/{period['id']}/close", page="/admin/dues")
        self.assertEqual(self.db.period(2026, 8)["status"], "Closed")
        self.assertEqual(len(list(self.db.backups_dir.glob("utthan-backup-*.db"))), backups_before + 1)

    def test_admin_can_search_members_and_restore_web_backup(self) -> None:
        self.setup_admin()
        self.login("admin", "StrongPass123")
        members = self.db.list_members()

        search = self.client.get(f"/admin/members?q={members[0]['member_no']}")
        self.assertEqual(search.status_code, 200)
        self.assertIn(members[0]["name"].encode(), search.data)
        self.assertNotIn(members[1]["name"].encode(), search.data)

        original_name = self.db.setting("society_name")
        backup = self.db.backup()
        backup_bytes = backup.read_bytes()
        self.db.save_settings({"society_name": "Temporary test name"})
        cashbook = self.client.get("/admin/reports")
        response = self.client.post(
            "/admin/restore",
            data={
                "csrf_token": self.token(cashbook),
                "backup_file": (io.BytesIO(backup_bytes), "utthan-backup.db"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")
        self.assertEqual(self.db.setting("society_name"), original_name)

    def test_member_can_only_access_own_records(self) -> None:
        self.setup_admin()
        members = self.db.list_members()
        own_member, other_member = members[0], members[1]
        self.db.create_user(
            "member1",
            generate_password_hash("MemberPass123"),
            "member",
            own_member["id"],
            must_change_password=False,
        )
        self.login("member1", "MemberPass123")

        portal = self.client.get("/portal")
        self.assertEqual(portal.status_code, 200)
        self.assertIn(own_member["name"].encode(), portal.data)
        self.assertIn(b"My membership details", portal.data)
        self.assertIn(b"Complete monthly dues ledger", portal.data)
        self.assertIn(b"Complete loan history", portal.data)
        self.assertIn(b"Complete transaction and payment history", portal.data)
        self.assertNotIn(other_member["name"].encode(), portal.data)
        self.assertEqual(self.client.get("/admin").status_code, 403)
        self.assertEqual(
            self.client.get(f"/admin/members/{own_member['id']}").status_code, 403
        )

        own_due = self.db.member_dues(own_member["id"])[0]
        other_due = self.db.member_dues(other_member["id"])[0]
        own_bill = self.client.get(f"/bill/{own_due['id']}")
        self.assertEqual(own_bill.status_code, 200)
        own_bill.close()
        self.assertEqual(self.client.get(f"/bill/{other_due['id']}").status_code, 403)

    def test_post_without_csrf_is_rejected(self) -> None:
        self.setup_admin()
        response = self.client.post(
            "/login", data={"username": "admin", "password": "StrongPass123"}
        )
        self.assertEqual(response.status_code, 400)

    def test_temporary_password_requires_change(self) -> None:
        self.setup_admin()
        member = self.db.list_members()[0]
        self.db.create_user(
            "member1",
            generate_password_hash("MemberPass123"),
            "member",
            member["id"],
            must_change_password=True,
        )
        self.login("member1", "MemberPass123")
        response = self.client.get("/portal")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/password")


if __name__ == "__main__":
    unittest.main()
