import io
import re
import tempfile
import unittest
from pathlib import Path

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
        self.assertIn(b"Society overview", response.data)

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
            "/admin/settings",
            "/password",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
        history = self.client.get(f"/admin/members/{member['id']}")
        self.assertIn(b"Complete membership and financial history", history.data)
        self.assertIn(member["name"].encode(), history.data)

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
        cashbook = self.client.get("/admin/cashbook")
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
