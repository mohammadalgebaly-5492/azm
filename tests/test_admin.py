"""مدير النظام، مصفوفة الصلاحيات، الجلسات، الإعدادات، واللغتان."""
import os
import re
import shutil
import tempfile
import unittest
from unittest import mock

from app import create_app, db as dbmod
from app.auth import AuthError, create_user
from app.db import connect, migrate
from app.i18n_ar import AR

from _db import fresh_database
from _strings import all_strings


class AdminBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({"DATABASE": fresh_database(self.tmp.name, "a.sqlite3"), "SESSION_COOKIE_SECURE": False,
                               "SECRET_KEY": "t"})
        self.db = connect(self.app.config["DATABASE"])
        with self.app.app_context():
            self.owner, _, _ = create_user(self.db, username="owner", email="o@co.sa", full_name="مدير النظام",
                                           role="superadmin", password="OwnerPass123")
            self.admin, _, _ = create_user(self.db, username="cost", email="c@co.sa", full_name="الكوست كنترول",
                                           role="admin", password="AdminPass123")
            self.pm, _, _ = create_user(self.db, username="pm.one", email="p@co.sa", full_name="مدير مشروع",
                                        role="pm", password="PmPass12345")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def client(self, username, password):
        c = self.app.test_client()
        r = c.post("/login", data={"username": username, "password": password})
        self.assertEqual(r.status_code, 302, r.get_data(as_text=True)[:300])
        return c

    def csrf(self, c):
        return re.search(r'name="csrf_token" value="([^"]+)"', c.get("/").get_data(as_text=True)).group(1)


class OwnerRole(AdminBase):
    def test_owner_code_and_console_access(self):
        code = self.db.execute("SELECT code FROM users WHERE id = ?", (self.owner,)).fetchone()[0]
        self.assertEqual(code, "USR-SYS-01")
        owner = self.client("owner", "OwnerPass123")
        for path in ("/admin", "/admin/roles", "/admin/roles/new", "/admin/roles/pm", "/admin/invites", "/admin/sessions",
                     "/admin/settings", "/admin/users", "/admin/audit"):
            self.assertEqual(owner.get(path).status_code, 200, path)
        # الكوست كنترول: يملك إدارة الحسابات وسجل العمليات افتراضيًا، فيرى الإدارة بهذه التبويبات فقط
        admin = self.client("cost", "AdminPass123")
        for path in ("/admin", "/admin/users", "/admin/audit"):
            self.assertEqual(admin.get(path).status_code, 200, path)
        for path in ("/admin/roles", "/admin/roles/pm", "/admin/invites", "/admin/sessions", "/admin/settings"):
            self.assertEqual(admin.get(path).status_code, 403, path)
        html = admin.get("/admin").get_data(as_text=True)
        self.assertNotIn("/admin/roles", html)
        self.assertNotIn("/admin/settings", html)
        pm = self.client("pm.one", "PmPass12345")
        self.assertEqual(pm.get("/admin").status_code, 403)
        self.assertNotIn('href="/admin"', pm.get("/").get_data(as_text=True))

    def test_admin_cannot_touch_owner_accounts(self):
        admin = self.client("cost", "AdminPass123")
        token = self.csrf(admin)
        self.assertEqual(admin.get(f"/admin/users/{self.owner}").status_code, 403)
        self.assertEqual(admin.post(f"/admin/users/{self.owner}/reset", data={"csrf_token": token}).status_code, 403)
        self.assertEqual(admin.post(f"/admin/users/{self.owner}/status",
                                    data={"csrf_token": token, "status": "disabled"}).status_code, 403)
        # ولا يمنح دور مدير النظام لنفسه أو لغيره
        r = admin.post(f"/admin/users/{self.pm}", data={"csrf_token": token, "full_name": "مدير مشروع",
                                                       "email": "p@co.sa", "role": "superadmin"})
        self.assertIn(AR["Only a System Owner can give the System Owner role."], r.get_data(as_text=True))
        self.assertEqual(self.db.execute("SELECT role FROM users WHERE id = ?", (self.pm,)).fetchone()[0], "pm")
        self.assertNotIn('value="superadmin"', admin.get("/admin/users/new").get_data(as_text=True))

    def test_last_owner_is_protected(self):
        owner = self.client("owner", "OwnerPass123")
        with self.app.test_request_context():
            from app import auth
            with self.assertRaises(AuthError):
                auth.update_user(self.db, self.owner, self.admin, full_name="مدير النظام", email="o@co.sa",
                                 role="admin", phone=None, job_title=None)
            with self.assertRaises(AuthError):
                auth.set_status(self.db, self.owner, "disabled", self.admin)
        # بعد وجود مدير نظام ثانٍ يصبح التغيير ممكنًا
        token = self.csrf(owner)
        r = owner.post("/admin/users/new", data={"csrf_token": token, "full_name": "مدير ثان", "username": "owner2",
                                                 "email": "o2@co.sa", "role": "superadmin"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.db.execute("SELECT code FROM users WHERE username = 'owner2'").fetchone()[0], "USR-SYS-02")


class Roles(AdminBase):
    def test_role_permissions_take_effect(self):
        pm = self.client("pm.one", "PmPass12345")
        self.assertEqual(pm.get("/admin/users").status_code, 403)
        owner = self.client("owner", "OwnerPass123")
        token = self.csrf(owner)
        form = {"csrf_token": token, "name_ar": "مدير المشروع", "name_en": "Project Manager", "code": "PM",
                "perm": ["users.manage"]}
        self.assertEqual(owner.post("/admin/roles/pm", data=form).status_code, 302)
        self.assertEqual(pm.get("/admin/users").status_code, 200)
        # صلاحيات مدير النظام وحده لا تُمنح لأي دور
        form["perm"] = ["users.manage", "roles.manage", "users.manage_owners"]
        owner.post("/admin/roles/pm", data=form)
        self.assertEqual(pm.get("/admin/roles").status_code, 403)
        self.assertIn("permissions_updated", {r[0] for r in self.db.execute("SELECT action FROM audit_log")})
        # ودور مدير النظام نفسه لا يُعدّل
        self.assertEqual(owner.post("/admin/roles/superadmin", data=form).status_code, 403)

    def test_create_rename_and_delete_role(self):
        owner = self.client("owner", "OwnerPass123")
        token = self.csrf(owner)
        r = owner.post("/admin/roles/new", data={"csrf_token": token, "name_ar": "مهندس كميات", "name_en": "Quantity Surveyor",
                                                 "code": "qs", "perm": ["projects.view_all"]})
        self.assertEqual(r.status_code, 302)
        row = self.db.execute("SELECT key, code, external FROM roles WHERE code = 'QS'").fetchone()
        self.assertEqual((row[0], row[1]), ("qs", "QS"))
        # الكود مكرر مرفوض
        r = owner.post("/admin/roles/new", data={"csrf_token": token, "name_ar": "آخر", "name_en": "Other", "code": "QS"})
        self.assertIn(AR["Another role already uses this code."], r.get_data(as_text=True))
        # حساب بالدور الجديد يأخذ كوده
        owner.post("/admin/users/new", data={"csrf_token": token, "full_name": "مهندس الكميات", "username": "qs.one",
                                             "email": "qs@co.sa", "role": "qs"})
        self.assertEqual(self.db.execute("SELECT code FROM users WHERE username = 'qs.one'").fetchone()[0], "USR-QS-01")
        # إعادة التسمية تظهر فورًا، والكود القديم للحساب لا يتغير
        owner.post("/admin/roles/qs", data={"csrf_token": token, "name_ar": "مهندس حصر", "name_en": "QS Engineer", "code": "QSE"})
        self.assertIn("مهندس حصر", owner.get("/admin/users").get_data(as_text=True))
        self.assertEqual(self.db.execute("SELECT code FROM users WHERE username = 'qs.one'").fetchone()[0], "USR-QS-01")
        # لا يُحذف دور عليه حسابات
        owner.post("/admin/roles/qs/delete", data={"csrf_token": token})
        self.assertIsNotNone(self.db.execute("SELECT 1 FROM roles WHERE key = 'qs'").fetchone())
        qs_id = self.db.execute("SELECT id FROM users WHERE username = 'qs.one'").fetchone()[0]
        owner.post(f"/admin/users/{qs_id}", data={"csrf_token": token, "full_name": "مهندس الكميات", "email": "qs@co.sa", "role": "pm"})
        owner.post("/admin/roles/qs/delete", data={"csrf_token": token})
        self.assertIsNone(self.db.execute("SELECT 1 FROM roles WHERE key = 'qs'").fetchone())
        self.assertEqual(owner.post("/admin/roles/superadmin/delete", data={"csrf_token": token}).status_code, 302)
        self.assertIsNotNone(self.db.execute("SELECT 1 FROM roles WHERE key = 'superadmin'").fetchone())

    def test_permission_catalog_is_clean(self):
        """كل صلاحية مستخدمة في الكود موجودة في الكتالوج، وكل صلاحية في الكتالوج لها مجموعة واحدة بالضبط."""
        import pathlib
        from app.rbac import ADMIN_AREA, OWNER_ONLY, PERMISSION_GROUPS, PERMISSIONS
        root = pathlib.Path(__file__).resolve().parent.parent / "app"
        used = set()
        pattern = re.compile(r"""(?:can|permission_required)\(\s*(?:[\w.\[\]"']+,\s*)?["']([a-z_]+\.[a-z_]+)["']""")
        for f in [*root.rglob("*.py"), *root.rglob("*.html")]:
            used |= set(pattern.findall(f.read_text(encoding="utf-8")))
        known = set(PERMISSIONS) | set(OWNER_ONLY)
        self.assertEqual(sorted(used - known), [], "Add these to PERMISSIONS in app/rbac.py")
        grouped = [k for _, keys in PERMISSION_GROUPS for k in keys]
        self.assertEqual(sorted(grouped), sorted(PERMISSIONS), "Every permission must be in exactly one group")
        self.assertTrue(set(ADMIN_AREA) <= known)


class SignupLinks(AdminBase):
    def test_links_need_switch_and_respect_limits(self):
        owner = self.client("owner", "OwnerPass123")
        token = self.csrf(owner)
        # المفتاح مطفأ افتراضيًا: الروابط لا تعمل
        with self.app.test_request_context():
            from app import invites
            link = invites.create(self.db, "pm", 3, 1, "", self.owner)
        guest = self.app.test_client()
        self.assertEqual(guest.get(f"/join/{link}").status_code, 404)
        owner.post("/admin/invites/toggle", data={"csrf_token": token, "enabled": "1"})
        self.assertEqual(guest.get(f"/join/{link}").status_code, 200)
        form = {"full_name": "مهندس موقع", "username": "site.eng", "email": "s@co.sa",
                "password": "SitePass2026", "confirm_password": "SitePass2026"}
        r = guest.post(f"/join/{link}", data=form)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(guest.get("/").status_code, 200)
        row = self.db.execute("SELECT role, must_change_password FROM users WHERE username = 'site.eng'").fetchone()
        self.assertEqual((row[0], bool(row[1])), ("pm", False))
        # الرابط لشخص واحد: الاستخدام الثاني مرفوض
        self.assertEqual(self.app.test_client().get(f"/join/{link}").status_code, 404)
        # لا روابط لدور مدير النظام، والإلغاء يعمل فورًا
        r = owner.post("/admin/invites", data={"csrf_token": token, "role": "superadmin", "days": "3", "max_uses": "1"})
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM invites WHERE role = 'superadmin'").fetchone()[0], 0)
        owner.post("/admin/invites", data={"csrf_token": token, "role": "viewer", "days": "1", "max_uses": "5"})
        iid, link2 = self.db.execute("SELECT id, token FROM invites WHERE role = 'viewer'").fetchone()
        self.assertEqual(guest.get(f"/join/{link2}").status_code, 302)  # مسجّل الدخول بالفعل
        fresh = self.app.test_client()
        self.assertEqual(fresh.get(f"/join/{link2}").status_code, 200)
        owner.post(f"/admin/invites/{iid}/revoke", data={"csrf_token": token})
        self.assertEqual(fresh.get(f"/join/{link2}").status_code, 404)
        # إطفاء المفتاح يوقف كل الروابط
        owner.post("/admin/invites", data={"csrf_token": token, "role": "viewer", "days": "1", "max_uses": "5"})
        link3 = self.db.execute("SELECT token FROM invites ORDER BY id DESC LIMIT 1").fetchone()[0]
        owner.post("/admin/invites/toggle", data={"csrf_token": token})
        self.assertEqual(fresh.get(f"/join/{link3}").status_code, 404)

    def test_bad_password_does_not_consume_link(self):
        owner = self.client("owner", "OwnerPass123")
        owner.post("/admin/invites/toggle", data={"csrf_token": self.csrf(owner), "enabled": "1"})
        with self.app.test_request_context():
            from app import invites
            link = invites.create(self.db, "pm", 3, 1, "", self.owner)
        guest = self.app.test_client()
        r = guest.post(f"/join/{link}", data={"full_name": "مهندس", "username": "eng.x", "email": "x@co.sa",
                                              "password": "short", "confirm_password": "short"})
        self.assertIn(AR["The password must be at least 10 characters."], r.get_data(as_text=True))
        self.assertEqual(self.db.execute("SELECT uses FROM invites").fetchone()[0], 0)


class SessionsAndSettings(AdminBase):
    def test_revoke_sessions(self):
        pm = self.client("pm.one", "PmPass12345")
        owner = self.client("owner", "OwnerPass123")
        self.assertIn("مدير مشروع", owner.get("/admin/sessions").get_data(as_text=True))
        sid = self.db.execute("SELECT id FROM sessions WHERE user_id = ?", (self.pm,)).fetchone()[0]
        owner.post(f"/admin/sessions/{sid}/revoke", data={"csrf_token": self.csrf(owner)})
        self.assertEqual(pm.get("/").status_code, 302)
        self.client("cost", "AdminPass123")
        owner.post("/admin/sessions/revoke-others", data={"csrf_token": self.csrf(owner)})
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 1)
        self.assertEqual(owner.get("/").status_code, 200)

    def test_settings_validate_and_apply(self):
        owner = self.client("owner", "OwnerPass123")
        token = self.csrf(owner)
        form = {"csrf_token": token, "platform_name_ar": "عزم", "platform_name_en": "AZM Pro",
                "company_name_ar": "الإنماء الحر للمقاولات", "company_name_en": "Alenmaa Alhor Construction",
                "session_idle_minutes": "300", "session_absolute_hours": "2"}
        r = owner.post("/admin/settings", data=form)
        self.assertIn(AR["The idle timeout can't be longer than the maximum session length."], r.get_data(as_text=True))
        form["session_idle_minutes"] = "60"
        self.assertEqual(owner.post("/admin/settings", data=form).status_code, 302)
        owner.set_cookie("lang", "en")
        self.assertIn("AZM Pro", owner.get("/").get_data(as_text=True))


class Languages(AdminBase):
    def test_every_interface_string_has_arabic(self):
        missing = sorted(s for s in all_strings() if s not in AR)
        self.assertEqual(missing, [], "Add these to app/i18n_ar.py")

    def test_arabic_default_and_english_switch(self):
        c = self.app.test_client()
        html = c.get("/login").get_data(as_text=True)
        self.assertIn('lang="ar" dir="rtl"', html)
        self.assertIn("تسجيل الدخول", html)
        r = c.get("/lang/en?next=/login")
        self.assertEqual(r.status_code, 302)
        html = c.get("/login").get_data(as_text=True)
        self.assertIn('lang="en" dir="ltr"', html)
        self.assertIn("Sign in to AZM", html)
        self.assertIn("Incorrect username or password.",
                      c.post("/login", data={"username": "x", "password": "y"}).get_data(as_text=True))
        # next خارجي يُتجاهل
        self.assertNotIn("evil", c.get("/lang/ar?next=//evil.example").headers["Location"])

    def test_pages_render_in_both_languages(self):
        owner = self.client("owner", "OwnerPass123")
        pid = owner.post("/admin/projects/new", data={"csrf_token": self.csrf(owner), "name": "مشروع الاختبار",
                                                      "start_date": "2026-01-01"}).headers["Location"].rsplit("/", 1)[1]
        paths = ["/", "/account", "/account/password", "/admin", "/admin/users", "/admin/users/new",
                 f"/admin/users/{self.pm}", "/admin/roles", "/admin/roles/new", "/admin/roles/pm", "/admin/roles/superadmin",
                 "/admin/invites", "/admin/sessions", "/admin/settings", "/admin/audit",
                 f"/projects/{pid}", f"/projects/{pid}/boq", f"/projects/{pid}/boq/import", "/admin/projects/new",
                 f"/admin/projects/{pid}/edit", "/nope"]
        for lang in ("ar", "en"):
            owner.set_cookie("lang", lang)
            for path in paths:
                r = owner.get(path)
                self.assertIn(r.status_code, (200, 302, 404), (lang, path))
                self.assertIn(f'lang="{lang}"', r.get_data(as_text=True), (lang, path))


class OwnerMigration(unittest.TestCase):
    """المهاجرة 004 ترقّي أقدم أدمن فعّال لمدير النظام في المنصات القائمة."""

    def test_oldest_active_admin_is_promoted(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        target = fresh_database(tmp.name, "m.sqlite3")
        pg = dbmod.is_postgres_url(target)
        source = dbmod.PG_MIGRATIONS if pg else dbmod.MIGRATIONS
        old = os.path.join(tmp.name, "old")
        os.makedirs(old)
        for f in sorted(source.iterdir()):
            if f.is_file() and f.name[:3] in ("001", "002", "003"):
                shutil.copy(f, old)
        conn = connect(target)
        self.addCleanup(conn.close)
        import pathlib
        with mock.patch.object(dbmod, "PG_MIGRATIONS" if pg else "MIGRATIONS", pathlib.Path(old)):
            migrate(conn)
        for i, (name, status) in enumerate((("first", "disabled"), ("second", "active"), ("third", "active"))):
            conn.execute("INSERT INTO users(code, username, email, full_name, role, status, password_hash, created_at) "
                         "VALUES (?, ?, ?, ?, 'admin', ?, 'x', '2026-01-01T00:00:00+00:00')",
                         (f"USR-ADM-0{i + 1}", name, f"{name}@co.sa", name, status))
        self.assertIn("004_owner_settings_permissions" + (".sql" if pg else ".py"), migrate(conn))
        roles = dict(conn.execute("SELECT username, role FROM users").fetchall())
        self.assertEqual(roles, {"first": "admin", "second": "superadmin", "third": "admin"})
        # 7 من المهاجرات الأولى، والثامنة إدارة السجلات المشتركة (المهاجرة 011)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM role_permissions WHERE role = 'admin'").fetchone()[0], 15)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM roles").fetchone()[0], 9)
        with self.assertRaises(dbmod.IntegrityError):  # الدور لازم يكون موجودًا في جدول الأدوار
            conn.execute("UPDATE users SET role = 'ghost' WHERE username = 'first'")


if __name__ == "__main__":
    unittest.main()
