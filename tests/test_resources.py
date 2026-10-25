"""الموارد (الدستور، البند 3.6): السجلات وأكوادها، والهيكل التنظيمي، والتخصيص وحوكمته ومنع التعارض بين المشاريع."""
import re
import tempfile
import unittest

from werkzeug.datastructures import MultiDict

from app import create_app, registers as R, resources as S
from app.auth import create_user
from app.boq import add_item, add_wbs, approve_baseline
from app.db import connect
from app.errors import AuthError
from app.projects import add_member, create_project

from _db import fresh_database


def person(name, prof="ENG", title="STE", cost="500", **kw):
    return {"full_name": name, "profession_code": prof, "job_title_code": title, "id_no": "1012345678",
            "phone": "0551234567", "daily_cost": cost, "status": "active", **kw}


def equipment(code="EXC", **kw):
    return {"catalog_code": code, "plate_serial": "ABC-1234", "ownership": "owned", "daily_cost": "1200",
            "status": "working", **kw}


class ResourceBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({"DATABASE": fresh_database(self.tmp.name, "r.sqlite3"), "SESSION_COOKIE_SECURE": False,
                               "SECRET_KEY": "t"})
        self.db = connect(self.app.config["DATABASE"])
        with self.app.app_context():
            self.cost, _, _ = create_user(self.db, username="cost", email="c@co.sa", full_name="مهندس تحكم تكلفة",
                                          role="admin", password="CostPass1234")
            self.director, _, _ = create_user(self.db, username="dir", email="d@co.sa", full_name="المدير التنفيذي",
                                              role="director", password="DirPass12345")
            self.pm, _, _ = create_user(self.db, username="pm.one", email="p@co.sa", full_name="مدير مشروع",
                                        role="pm", password="PmPass12345")
            self.pid, self.pcode = create_project(self.db, {"name": "مبنى إداري", "start_date": "2026-11-01"}, self.cost)
            self.pid2, self.pcode2 = create_project(self.db, {"name": "فيلا سكنية", "start_date": "2026-11-01"}, self.cost)
            for pid in (self.pid, self.pid2):
                add_member(self.db, pid, self.pm, self.cost)
                add_member(self.db, pid, self.director, self.cost)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def ctx(self):
        return self.app.test_request_context()

    def item(self, pid, qty="100", rate="100"):
        wid, _ = add_wbs(self.db, pid, "الهيكل الخرساني", None, self.cost)
        iid, _ = add_item(self.db, pid, wid, {"description": "صب خرسانة القواعد", "item_type": "both", "unit": "م3",
                                              "qty": qty, "unit_rate": rate}, self.cost)
        return iid

    def staffed(self, pid):
        """مشروع فيه مدير مشروع ومهندس موقع يتبعه، وبند واحد."""
        pm = S.save_person(self.db, person("أحمد علي", title="PJM", cost="900"), self.cost)
        eng = S.save_person(self.db, person("خالد سالم"), self.cost)
        top = S.add_position(self.db, pid, {"job_title_code": "PJM", "person_id": pm, "from_date": "2026-11-01"}, self.cost)
        site = S.add_position(self.db, pid, {"job_title_code": "STE", "person_id": eng, "reports_to": top,
                                             "from_date": "2026-11-01"}, self.cost)
        return {"pm": pm, "eng": eng, "top": top, "site": site, "item": self.item(pid)}

    def alloc(self, pid, s, kind="person", rid=None, **kw):
        form = {"resource_kind": kind, f"resource_id_{kind}": rid or s["eng"], "boq_item_id": s["item"],
                "supervisor_id": s["top"], "position_id": s["site"], "from_date": "2026-11-01", "to_date": "2026-11-14",
                "days_per_week": "6", "hours_per_day": "8", "allocation_pct": "100", "productivity": "10", **kw}
        return S.add_allocation(self.db, pid, form, self.cost)

    def client(self, username, password):
        c = self.app.test_client()
        self.assertEqual(c.post("/login", data={"username": username, "password": password}).status_code, 302)
        return c

    def csrf(self, c):
        return re.search(r'name="csrf_token" value="([^"]+)"', c.get("/").get_data(as_text=True)).group(1)


class Registers(ResourceBase):
    def test_people_crews_and_equipment_get_permanent_codes(self):
        with self.ctx():
            a = S.save_person(self.db, person("أحمد علي"), self.cost)
            b = S.save_person(self.db, person("خالد سالم"), self.cost)
            c = S.save_person(self.db, person("محمد حسن", prof="LAB", title="INS", cost="150"), self.cost)
            crew = S.save_crew(self.db, MultiDict([("name", "طاقم الخرسانة 1"), ("specialty_code", "CNC"),
                                                   ("leader_id", str(b)), ("members", str(c))]), self.cost)
            eq = S.save_equipment(self.db, equipment(), self.cost)
            with self.assertRaises(AuthError):  # المستأجرة تحتاج المؤجر
                S.save_equipment(self.db, equipment(ownership="rented"), self.cost)
            with self.assertRaises(AuthError):  # كود الدليل لا يتغير
                S.save_equipment(self.db, equipment("LDR"), self.cost, eq)
            S.save_person(self.db, person("أحمد علي", user_id=str(self.pm)), self.cost, a)
            with self.assertRaises(AuthError):  # الحساب الواحد لفرد واحد
                S.save_person(self.db, person("خالد سالم", user_id=str(self.pm)), self.cost, b)
        codes = [r["code"] for r in S.people(self.db)]
        self.assertEqual(codes, ["EMP-ENG-0001", "EMP-ENG-0002", "EMP-LAB-0001"])
        row = self.db.execute("SELECT * FROM crews WHERE id = ?", (crew,)).fetchone()
        self.assertEqual(row["code"], "CRW-CNC-001")
        self.assertEqual({m["id"] for m in S.crew_members(self.db, crew)}, {b, c})  # رئيس الطاقم عضو تلقائيًا
        self.assertEqual(S.crew_daily_cost(self.db, row), 65000)  # 500 + 150 ريال
        self.assertEqual(S.equipment(self.db)[0]["code"], "EQP-EXC-0001")

    def test_validation(self):
        with self.ctx():
            for bad in ({"full_name": "أح"}, {"profession_code": "XXX"}, {"id_no": "12"}, {"daily_cost": ""},
                        {"email": "not-an-email"}, {"status": "x"}):
                with self.assertRaises(AuthError, msg=bad):
                    S.save_person(self.db, {**person("أحمد علي"), **bad}, self.cost)
            with self.assertRaises(AuthError):
                S.save_crew(self.db, {"name": "طاقم", "specialty_code": "CNC", "leader_id": ""}, self.cost)


class OrgChart(ResourceBase):
    def test_tree_codes_and_ending_a_position(self):
        with self.ctx():
            s = self.staffed(self.pid)
            with self.assertRaises(AuthError):  # لا تنتهي وظيفة يتبعها غيرها
                S.end_position(self.db, self.pid, s["top"], "2026-12-01", self.cost)
            with self.assertRaises(AuthError):  # المدير المباشر من نفس المشروع
                S.add_position(self.db, self.pid2, {"job_title_code": "STE", "person_id": s["eng"],
                                                    "reports_to": s["top"], "from_date": "2026-11-01"}, self.cost)
            tree = S.org_tree(self.db, self.pid)
            self.assertEqual([(r["code"], [k["code"] for k, _ in kids]) for r, kids in tree],
                             [(f"{self.pcode}-ORG-01", [f"{self.pcode}-ORG-02"])])
            S.end_position(self.db, self.pid, s["site"], "2026-12-01", self.cost)
        self.assertEqual([k for _, k in S.org_tree(self.db, self.pid)], [[]])


class Allocation(ResourceBase):
    def test_working_days_and_cost(self):
        self.assertEqual(S.working_days("2026-11-01", "2026-11-14", 7), 14)
        self.assertEqual(S.working_days("2026-11-01", "2026-11-14", 6), 12)  # بدون يومي الجمعة
        self.assertEqual(S.working_days("2026-11-01", "2026-11-14", 5), 10)  # بدون الجمعة والسبت
        with self.ctx():
            s = self.staffed(self.pid)
            aid, code, warnings = self.alloc(self.pid, s, allocation_pct="50", productivity="5")
        self.assertEqual(code, f"{self.pcode}-ALC-0001")
        a = self.db.execute("SELECT * FROM allocations WHERE id = ?", (aid,)).fetchone()
        self.assertEqual((a["qty_milli"], a["allocation_bp"], a["status"]), (100000, 5000, "planned"))
        self.assertIsNotNone(a["wbs_id"])  # عنصر الهيكل يؤخذ من البند
        ev = S.evaluate(self.db, a)
        self.assertEqual((ev["days"], ev["needed"], ev["cost"], ev["unit_cost"]), (12, 20, 300000, 3000))
        self.assertEqual(len(warnings), 1)  # الفترة أقصر من اللازم لمعدل الإنتاج

    def test_no_resource_is_booked_above_capacity_across_projects(self):
        with self.ctx():
            s1, s2 = self.staffed(self.pid), self.staffed(self.pid2)
            first, _, _ = self.alloc(self.pid, s1, allocation_pct="60")
            with self.assertRaises(AuthError) as e:
                self.alloc(self.pid2, s2, rid=s1["eng"], allocation_pct="50", from_date="2026-11-10", to_date="2026-11-30")
            self.assertIn(self.pcode, str(e.exception))
            self.alloc(self.pid2, s2, rid=s1["eng"], allocation_pct="40", from_date="2026-11-10", to_date="2026-11-30")
            self.alloc(self.pid2, s2, rid=s1["eng"], allocation_pct="100", from_date="2026-12-01", to_date="2026-12-10")
            with self.assertRaises(AuthError):  # الإلغاء يحتاج سببًا
                S.cancel_allocation(self.db, self.pid, first, "", self.cost)
            S.cancel_allocation(self.db, self.pid, first, "تغيير خطة التنفيذ", self.cost)
            self.alloc(self.pid2, s2, rid=s1["eng"], allocation_pct="60", from_date="2026-11-10", to_date="2026-11-30")

    def test_unavailable_resources_are_rejected(self):
        with self.ctx():
            s = self.staffed(self.pid)
            gone = S.save_person(self.db, person("سعيد عمر", status="terminated"), self.cost)
            broken = S.save_equipment(self.db, equipment(status="out"), self.cost)
            sub, _ = R.create_entity(self.db, "subcontractor", MultiDict([
                ("name", "مؤسسة البناء"), ("email", "s@b.sa"), ("cr_no", "1010"), ("vat_no", "3000"),
                ("approval_status", "review"), ("specialties", "CNC")]), self.cost)
            for kind, rid in (("person", gone), ("equipment", broken), ("subcontractor", sub)):
                with self.assertRaises(AuthError, msg=kind):
                    self.alloc(self.pid, s, kind=kind, rid=rid, unit_rate="80")
            with self.assertRaises(AuthError):  # البند من مشروع آخر
                self.alloc(self.pid, s, boq_item_id=self.item(self.pid2))
            with self.assertRaises(AuthError):  # الفرد يحتاج وظيفته في الهيكل
                self.alloc(self.pid, s, position_id="")
            ok = S.save_equipment(self.db, equipment(), self.cost)
            aid, _, _ = self.alloc(self.pid, s, kind="equipment", rid=ok, position_id="")
        a = self.db.execute("SELECT * FROM allocations WHERE id = ?", (aid,)).fetchone()
        self.assertEqual(S.evaluate(self.db, a)["cost"], 12 * 120000)

    def test_preparer_cannot_approve(self):
        with self.ctx():
            s = self.staffed(self.pid)
            aid, _, _ = self.alloc(self.pid, s)
            with self.assertRaises(AuthError):
                S.approve_allocation(self.db, self.pid, aid, self.cost)
            S.approve_allocation(self.db, self.pid, aid, self.director)
            with self.assertRaises(AuthError):  # لا يُعتمد مرتين
                S.approve_allocation(self.db, self.pid, aid, self.director)
        row = self.db.execute("SELECT status, approved_by FROM allocations WHERE id = ?", (aid,)).fetchone()
        self.assertEqual((row[0], row[1]), ("approved", self.director))

    def test_maintenance_warns_and_baseline_locks_cancelling_to_the_director(self):
        with self.ctx():
            s = self.staffed(self.pid)
            eq = S.save_equipment(self.db, equipment(status="maintenance"), self.cost)
            aid, _, warnings = self.alloc(self.pid, s, kind="equipment", rid=eq, position_id="", productivity="100")
            self.assertEqual(len(warnings), 2)  # في الصيانة، وتكلفة الوحدة أعلى من سعر البند
            approve_baseline(self.db, self.pid, self.cost)
            with self.assertRaises(AuthError):
                S.cancel_allocation(self.db, self.pid, aid, "تغيير خطة التنفيذ", self.cost)
            S.cancel_allocation(self.db, self.pid, aid, "تغيير خطة التنفيذ", self.director, may_approve=True)
        self.assertEqual(self.db.execute("SELECT status FROM allocations WHERE id = ?", (aid,)).fetchone()[0], "cancelled")

    def test_screens_follow_permissions(self):
        with self.ctx():
            s = self.staffed(self.pid)
            aid, _, _ = self.alloc(self.pid, s)
        pm, director, cost = (self.client("pm.one", "PmPass12345"), self.client("dir", "DirPass12345"),
                              self.client("cost", "CostPass1234"))
        page = pm.get(f"/projects/{self.pid}/resources").get_data(as_text=True)
        self.assertIn(f"{self.pcode}-ALC-0001", page)
        self.assertIn("خالد سالم", page)
        for url in ("/registers/people", "/registers/crews", "/registers/equipment/new"):
            self.assertEqual(pm.get(url).status_code, 403, url)
            self.assertEqual(cost.get(url).status_code, 200, url)
        self.assertEqual(cost.get(f"/projects/{self.pid}/resources").status_code, 200)
        url = f"/projects/{self.pid}/allocations/{aid}/approve"
        self.assertEqual(pm.post(url, data={"csrf_token": self.csrf(pm)}).status_code, 403)
        self.assertEqual(pm.post(f"/projects/{self.pid}/allocations", data={"csrf_token": self.csrf(pm)}).status_code, 403)
        self.assertEqual(director.post(url, data={"csrf_token": self.csrf(director)}).status_code, 302)
        self.assertEqual(self.db.execute("SELECT status FROM allocations WHERE id = ?", (aid,)).fetchone()[0], "approved")


if __name__ == "__main__":
    unittest.main()
