"""تجربة كل دور كما يراه صاحبه: كل رابط في قائمته يعمل، ولا يرى ما لا يملك صلاحيته."""
import re
import tempfile
import unittest

from app import create_app
from app.auth import create_user
from app.db import connect
from app.projects import add_member, create_project

from _db import fresh_database

ROLES = ("superadmin", "admin", "pm", "director", "accountant", "viewer", "owner_rep", "consultant")
NAV_LINK = re.compile(r'<nav class="nav".*?</nav>', re.S)
HREF = re.compile(r'href="(/[^"#?]*)"')


class RoleBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({"DATABASE": fresh_database(self.tmp.name, "r.sqlite3"), "SESSION_COOKIE_SECURE": False,
                               "SECRET_KEY": "t"})
        self.db = connect(self.app.config["DATABASE"])
        with self.app.test_request_context():
            self.ids = {}
            for i, role in enumerate(ROLES):
                self.ids[role] = create_user(self.db, username=f"user.{role.replace('_', '')}", email=f"{role}@co.sa",
                                             full_name=f"حساب {role}", role=role, password="GoodPass2026")[0]
            self.pid = create_project(self.db, {"name": "مشروع مشترك", "contract_value": "1000",
                                                "start_date": "2026-01-01"}, self.ids["admin"])[0]
            create_project(self.db, {"name": "مشروع آخر"}, self.ids["admin"])
            for role in ("pm", "accountant", "owner_rep", "consultant"):
                add_member(self.db, self.pid, self.ids[role], self.ids["admin"])

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def client(self, role):
        c = self.app.test_client()
        r = c.post("/login", data={"username": f"user.{role.replace('_', '')}", "password": "GoodPass2026"})
        self.assertEqual(r.status_code, 302)
        return c


class EveryRole(RoleBase):
    def test_every_menu_link_works_for_every_role(self):
        for lang in ("ar", "en"):
            for role in ROLES:
                c = self.client(role)
                c.set_cookie("lang", lang)
                home = c.get("/")
                self.assertEqual(home.status_code, 200, (role, lang))
                nav = NAV_LINK.search(home.get_data(as_text=True)).group(0)
                links = set(HREF.findall(nav))
                self.assertIn("/", links, role)
                for href in links:
                    r = c.get(href)
                    self.assertEqual(r.status_code, 200, (role, lang, href))
                # المشروع المسند له يفتح، وجدول كمياته يُقرأ
                if role in ("pm", "accountant", "owner_rep", "consultant", "admin", "superadmin", "director", "viewer"):
                    self.assertEqual(c.get(f"/projects/{self.pid}").status_code, 200, role)
                    self.assertEqual(c.get(f"/projects/{self.pid}/boq").status_code, 200, role)

    def test_menu_matches_permissions(self):
        expect = {
            "pm": {"admin": False, "accounts": False, "analytics": False, "projects_all": False},
            "director": {"admin": False, "accounts": False, "analytics": True, "projects_all": True},
            "viewer": {"admin": False, "accounts": False, "analytics": True, "projects_all": True},
            "admin": {"admin": True, "accounts": True, "analytics": True, "projects_all": True},
            "superadmin": {"admin": True, "accounts": True, "analytics": True, "projects_all": True},
        }
        for role, e in expect.items():
            html = self.client(role).get("/").get_data(as_text=True)
            nav = NAV_LINK.search(html).group(0)
            self.assertEqual('href="/admin"' in nav, e["admin"], role)
            self.assertEqual('href="/admin/users"' in nav, e["accounts"], role)
            self.assertEqual('href="/analytics"' in nav, e["analytics"], role)
            self.assertEqual("مشروع آخر" in html, e["projects_all"], role)
        # من لا يرى كل المشروعات يرى مشروعه المسند فقط
        pm_home = self.client("pm").get("/").get_data(as_text=True)
        self.assertIn("مشروع مشترك", pm_home)
        self.assertEqual(self.client("pm").get(f"/projects/{self.pid + 1}").status_code, 404)

    def test_temporary_password_is_one_focused_step(self):
        self.db.execute("UPDATE users SET must_change_password = TRUE WHERE id = ?", (self.ids["pm"],))
        c = self.client("pm")
        for path in ("/", "/analytics", f"/projects/{self.pid}", "/account"):
            self.assertIn("/account/password", c.get(path).headers["Location"], path)
        page = c.get("/account/password").get_data(as_text=True)
        self.assertNotIn('class="sidebar"', page)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        r = c.post("/account/password", data={"csrf_token": token, "current_password": "GoodPass2026",
                                              "new_password": "NewSecret2027", "confirm_password": "NewSecret2027"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(c.get("/").status_code, 200)
        self.assertIn('class="sidebar"', c.get("/account/password").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()


class Explanations(RoleBase):
    def test_show_explanations_preference(self):
        c = self.client("pm")
        html = c.get("/account").get_data(as_text=True)
        self.assertIn('class="hide-guide"', html)                       # مطفأة افتراضيًا
        self.assertIn('name="show_guide"', html)                        # المفتاح في التفضيلات
        token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
        self.assertEqual(c.post("/account/preferences", data={"csrf_token": token, "show_guide": "1"}).status_code, 302)
        for path in ("/", "/account", f"/projects/{self.pid}"):
            self.assertNotIn('class="hide-guide"', c.get(path).get_data(as_text=True), path)
        # يتبع الحساب لا المتصفح: جلسة جديدة على جهاز آخر ترى نفس التفضيل
        self.assertNotIn('class="hide-guide"', self.client("pm").get("/").get_data(as_text=True))
        c.post("/account/preferences", data={"csrf_token": token})
        self.assertIn('class="hide-guide"', c.get("/").get_data(as_text=True))
        # صفحات الدخول (بدون حساب) تعرض الشروح دائمًا
        self.assertNotIn('class="hide-guide"', self.app.test_client().get("/login").get_data(as_text=True))
