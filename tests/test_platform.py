"""اختبارات المرحلة الأولى: الحسابات والدخول والصلاحيات والمشروعات.

التشغيل: python -m unittest discover -s tests -v
"""
import os
import re
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from app import create_app
from app.auth import AuthError, create_user, password_problems
from app.db import IntegrityError, connect

from _db import fresh_database
from app.projects import fmt_money, parse_money


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({"DATABASE": fresh_database(self.tmp.name, "t.sqlite3"), "TESTING": True,
                               "SESSION_COOKIE_SECURE": False, "SECRET_KEY": "test"})
        self.db = connect(self.app.config["DATABASE"])
        with self.app.app_context():
            self.admin_id, _, _ = create_user(self.db, username="admin", email="admin@co.sa", full_name="مهندس الكوست",
                                              role="admin", password="AdminPass123")
        self.c = self.app.test_client()

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def csrf(self, client=None):
        html = (client or self.c).get("/").get_data(as_text=True)
        m = re.search(r'name="csrf_token" value="([^"]+)"', html)
        return m.group(1) if m else ""

    def login(self, username, password, client=None):
        return (client or self.c).post("/login", data={"username": username, "password": password})

    def make_user(self, username, role, created_by=None):
        with self.app.app_context():
            return create_user(self.db, username=username, email=f"{username}@co.sa", full_name=f"مستخدم {username}",
                               role=role, created_by=created_by or self.admin_id)


class PasswordRules(unittest.TestCase):
    def test_policy(self):
        self.assertTrue(password_problems("short1"))
        self.assertTrue(password_problems("onlyletterslong"))
        self.assertTrue(password_problems("ahmed12345678", "ahmed"))
        self.assertFalse(password_problems("Strong2026Pass"))

    def test_money(self):
        self.assertEqual(parse_money("1,250,000.5"), 125000050)
        self.assertEqual(parse_money("١٠٠٠"), 100000)
        self.assertIsNone(parse_money(""))
        self.assertEqual(fmt_money(125000050), "1,250,000.50")
        with self.assertRaises(AuthError):
            parse_money("12.345")


class LoginTests(Base):
    def test_login_and_logout(self):
        r = self.login("admin", "AdminPass123")
        self.assertEqual(r.status_code, 302)
        self.assertIn("cc_session", r.headers.get("Set-Cookie", ""))
        self.assertIn("HttpOnly", r.headers["Set-Cookie"])
        self.assertEqual(self.c.get("/").status_code, 200)
        self.c.post("/logout", data={"csrf_token": self.csrf()})
        self.assertEqual(self.c.get("/").status_code, 302)

    def test_wrong_password_same_message_as_unknown_user(self):
        a = self.login("admin", "wrong-pass-1").get_data(as_text=True)
        b = self.login("nobody", "wrong-pass-1").get_data(as_text=True)
        self.assertIn("اسم المستخدم أو كلمة المرور غير صحيحة", a)
        self.assertIn("اسم المستخدم أو كلمة المرور غير صحيحة", b)

    def test_lockout_after_five_failures(self):
        for _ in range(5):
            self.login("admin", "wrong-pass-1")
        r = self.login("admin", "AdminPass123")
        self.assertEqual(r.status_code, 401)
        self.assertIn("مقفول مؤقتًا", r.get_data(as_text=True))
        self.db.execute("UPDATE users SET locked_until = ? WHERE username = 'admin'",
                        ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),))
        self.assertEqual(self.login("admin", "AdminPass123").status_code, 302)

    def test_post_without_csrf_rejected(self):
        self.login("admin", "AdminPass123")
        r = self.c.post("/admin/projects/new", data={"name": "مشروع"})
        self.assertEqual(r.status_code, 400)

    def test_idle_session_expires(self):
        self.login("admin", "AdminPass123")
        old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(timespec="seconds")
        self.db.execute("UPDATE sessions SET last_seen = ?", (old,))
        self.assertEqual(self.c.get("/").status_code, 302)

    def test_audit_log_is_append_only(self):
        self.login("admin", "AdminPass123")
        with self.assertRaises(IntegrityError):
            self.db.execute("DELETE FROM audit_log")
        with self.assertRaises(IntegrityError):
            self.db.execute("UPDATE audit_log SET action = 'x'")


class AccountLifecycle(Base):
    def test_admin_creates_account_and_forced_password_change(self):
        self.login("admin", "AdminPass123")
        r = self.c.post("/admin/users/new", data={
            "csrf_token": self.csrf(), "full_name": "أحمد سالم", "username": "a.salem", "email": "a.salem@co.sa",
            "role": "pm"})
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("USR-PM-01", html)
        temp = re.search(r'<span class="secret" id="pw">([^<]+)</span>', html).group(1)
        row = self.db.execute("SELECT password_hash, must_change_password FROM users WHERE username='a.salem'").fetchone()
        self.assertNotIn(temp, row["password_hash"])
        self.assertEqual(row["must_change_password"], 1)

        pm = self.app.test_client()
        self.assertEqual(self.login("a.salem", temp, pm).status_code, 302)
        r = pm.get("/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/account/password", r.headers["Location"])
        tok = re.search(r'name="csrf_token" value="([^"]+)"', pm.get("/account/password").get_data(as_text=True)).group(1)
        r = pm.post("/account/password", data={"csrf_token": tok, "current_password": temp,
                                               "new_password": "Salem2026Site", "confirm_password": "Salem2026Site"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(pm.get("/").status_code, 200)

    def test_user_codes_sequence_per_role(self):
        self.assertEqual(self.make_user("pm.one", "pm")[1], "USR-PM-01")
        self.assertEqual(self.make_user("pm.two", "pm")[1], "USR-PM-02")
        self.assertEqual(self.make_user("acc.one", "accountant")[1], "USR-ACC-01")

    def test_duplicates_rejected(self):
        self.make_user("dup", "pm")
        with self.app.app_context(), self.assertRaises(AuthError):
            create_user(self.db, username="DUP", email="other@co.sa", full_name="مكرر", role="pm")
        with self.app.app_context(), self.assertRaises(AuthError):
            create_user(self.db, username="other", email="dup@co.sa", full_name="مكرر", role="pm")

    def test_disable_kills_sessions_and_blocks_login(self):
        _, _, pw = self.make_user("site.eng", "pm")
        other = self.app.test_client()
        self.login("site.eng", pw, other)
        self.login("admin", "AdminPass123")
        uid = self.db.execute("SELECT id FROM users WHERE username='site.eng'").fetchone()[0]
        self.c.post(f"/admin/users/{uid}/status", data={"csrf_token": self.csrf(), "status": "disabled"})
        self.assertEqual(other.get("/account/password").status_code, 302)
        self.assertEqual(self.login("site.eng", pw, self.app.test_client()).status_code, 401)

    def test_cannot_disable_last_admin_or_self(self):
        self.login("admin", "AdminPass123")
        r = self.c.post(f"/admin/users/{self.admin_id}/status", data={"csrf_token": self.csrf(), "status": "disabled"},
                        follow_redirects=True)
        self.assertIn("لا يمكنك إيقاف حسابك", r.get_data(as_text=True))

    def test_reset_password_invalidates_old(self):
        uid, _, pw = self.make_user("reset.me", "pm")
        self.login("admin", "AdminPass123")
        html = self.c.post(f"/admin/users/{uid}/reset", data={"csrf_token": self.csrf()}).get_data(as_text=True)
        new = re.search(r'id="pw">([^<]+)<', html).group(1)
        self.assertNotEqual(new, pw)
        self.assertEqual(self.login("reset.me", pw, self.app.test_client()).status_code, 401)
        self.assertEqual(self.login("reset.me", new, self.app.test_client()).status_code, 302)


class Permissions(Base):
    def _active_user(self, username, role):
        uid, _, pw = self.make_user(username, role)
        self.db.execute("UPDATE users SET must_change_password = FALSE WHERE id = ?", (uid,))
        cl = self.app.test_client()
        self.login(username, pw, cl)
        return uid, cl

    def test_non_admin_blocked_from_admin_pages(self):
        for role in ("pm", "director", "accountant", "viewer", "consultant"):
            _, cl = self._active_user(f"u.{role}", role)
            self.assertEqual(cl.get("/admin/users").status_code, 403, role)
            self.assertEqual(cl.get("/admin/users/new").status_code, 403, role)
            tok = self.csrf(cl)
            r = cl.post("/admin/users/new", data={"csrf_token": tok, "full_name": "دخيل", "username": "intruder",
                                                   "email": "i@co.sa", "role": "admin"})
            self.assertEqual(r.status_code, 403, role)
            self.assertEqual(cl.get("/admin/projects/new").status_code, 403, role)
        self.assertIsNone(self.db.execute("SELECT 1 FROM users WHERE username='intruder'").fetchone())

    def test_project_visibility_by_assignment(self):
        self.login("admin", "AdminPass123")
        r = self.c.post("/admin/projects/new", data={"csrf_token": self.csrf(), "name": "مستودعات السلي",
                                                     "start_date": "2026-11-01", "end_date": "2027-10-31",
                                                     "contract_value": "12,500,000"})
        pid = int(r.headers["Location"].rsplit("/", 1)[1])
        p = self.db.execute("SELECT code, contract_value FROM projects WHERE id = ?", (pid,)).fetchone()
        self.assertEqual(p["code"], "P-2026-001")
        self.assertEqual(p["contract_value"], 1250000000)

        uid, pm = self._active_user("pm.a", "pm")
        _, pm_other = self._active_user("pm.b", "pm")
        self.assertEqual(pm.get(f"/projects/{pid}").status_code, 404)
        self.c.post(f"/admin/projects/{pid}/members", data={"csrf_token": self.csrf(), "user_id": uid})
        self.assertEqual(pm.get(f"/projects/{pid}").status_code, 200)
        self.assertEqual(pm_other.get(f"/projects/{pid}").status_code, 404)
        self.assertNotIn("مستودعات السلي", pm_other.get("/").get_data(as_text=True))
        # مدير المشروع لا يستطيع إسناد نفسه أو غيره
        r = pm_other.post(f"/admin/projects/{pid}/members", data={"csrf_token": self.csrf(pm_other), "user_id": 1})
        self.assertEqual(r.status_code, 403)

    def test_role_change_ends_sessions(self):
        uid, cl = self._active_user("will.change", "pm")
        self.login("admin", "AdminPass123")
        self.c.post(f"/admin/users/{uid}", data={"csrf_token": self.csrf(), "full_name": "تغيير دور",
                                                  "email": "will.change@co.sa", "role": "viewer"})
        self.assertEqual(self.db.execute("SELECT role FROM users WHERE id = ?", (uid,)).fetchone()[0], "viewer")
        self.assertEqual(cl.get("/").status_code, 302)

    def test_invalid_project_dates_rejected(self):
        self.login("admin", "AdminPass123")
        r = self.c.post("/admin/projects/new", data={"csrf_token": self.csrf(), "name": "مشروع خاطئ",
                                                     "start_date": "2027-01-01", "end_date": "2026-01-01"})
        self.assertIn("تاريخ النهاية يجب أن يكون بعد", r.get_data(as_text=True))


class FirstSetup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({"DATABASE": fresh_database(self.tmp.name, "s.sqlite3"), "SESSION_COOKIE_SECURE": False,
                               "SECRET_KEY": "test"})
        self.c = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def form(self, **kw):
        d = {"full_name": "م. محمد الجبالي", "username": "m.algebaly", "email": "m@co.sa",
             "password": "Admin2026Pass", "confirm_password": "Admin2026Pass"}
        d.update(kw)
        return d

    def test_login_redirects_to_setup_until_admin_exists(self):
        self.assertIn("/setup", self.c.get("/login").headers["Location"])
        r = self.c.post("/setup", data=self.form())
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.c.get("/").status_code, 200)
        # بعد وجود الأدمن الإعداد مقفول
        other = self.app.test_client()
        self.assertIn("/login", other.get("/setup").headers["Location"])
        r = other.post("/setup", data=self.form(username="intruder", email="i@co.sa"))
        self.assertEqual(r.status_code, 302)
        db = connect(self.app.config["DATABASE"])
        self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)
        db.close()

    def test_weak_password_rejected(self):
        r = self.c.post("/setup", data=self.form(password="123", confirm_password="123"))
        self.assertIn("لا تقل عن 10", r.get_data(as_text=True))

    def test_remote_setup_needs_token(self):
        remote = {"REMOTE_ADDR": "203.0.113.5"}
        self.assertEqual(self.c.get("/setup", environ_base=remote).status_code, 403)
        os.environ["CC_SETUP_TOKEN"] = "s3cret-token"
        try:
            self.assertEqual(self.c.get("/setup?token=wrong", environ_base=remote).status_code, 403)
            self.assertEqual(self.c.get("/setup?token=s3cret-token", environ_base=remote).status_code, 200)
        finally:
            del os.environ["CC_SETUP_TOKEN"]


if __name__ == "__main__":
    unittest.main()
