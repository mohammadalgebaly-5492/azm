"""السجلات المشتركة (الدستور، المادة 2 والبند 3.9): الأدلة، والجهات وأشخاصها، وأطراف المشروع."""
import re
import tempfile
import unittest

from werkzeug.datastructures import MultiDict

from app import create_app, registers as R
from app.auth import create_user
from app.db import connect
from app.errors import AuthError
from app.projects import create_project

from _db import fresh_database


class RegistersBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({"DATABASE": fresh_database(self.tmp.name, "r.sqlite3"), "SESSION_COOKIE_SECURE": False,
                               "SECRET_KEY": "t"})
        self.db = connect(self.app.config["DATABASE"])
        with self.app.app_context():
            self.cost, _, _ = create_user(self.db, username="cost", email="c@co.sa", full_name="مهندس تحكم تكلفة",
                                          role="admin", password="CostPass1234")
            self.pm, _, _ = create_user(self.db, username="pm.one", email="p@co.sa", full_name="مدير مشروع",
                                        role="pm", password="PmPass12345")
            self.pid, _ = create_project(self.db, {"name": "مبنى إداري"}, self.cost)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def owner_with_people(self, n=2):
        with self.app.test_request_context():
            eid, code = R.create_entity(self.db, "owner", {"name": "شركة التطوير", "email": "info@dev.sa"}, self.cost)
            people = [R.add_person(self.db, eid, {"full_name": f"ممثل {i}", "job_title": "مهندس", "phone": "0500000000",
                                                  "email": f"r{i}@dev.sa"}, self.cost)[0] for i in range(n)]
        return eid, code, people

    def client(self, username, password):
        c = self.app.test_client()
        self.assertEqual(c.post("/login", data={"username": username, "password": password}).status_code, 302)
        return c

    def csrf(self, c):
        return re.search(r'name="csrf_token" value="([^"]+)"', c.get("/").get_data(as_text=True)).group(1)


class Catalogs(RegistersBase):
    def test_lists_are_seeded_from_the_constitution(self):
        ssl = self.db.execute("SELECT * FROM catalog_items WHERE kind = 'equipment' AND code = 'SSL'").fetchone()
        self.assertEqual((ssl["name_ar"], ssl["parent_code"], ssl["cost_unit"]), ("محمّلة صغيرة", "LGT", "day"))
        types = {r["code"] for r in R.catalog(self.db, "equipment_type")}
        self.assertEqual(types, {"HVY", "LGT", "TRN", "PWR", "TLS"})
        self.assertIn("CCE", {r["code"] for r in R.catalog(self.db, "job_title")})

    def test_codes_are_validated_permanent_and_entries_are_stopped_not_deleted(self):
        with self.app.test_request_context():
            with self.assertRaises(AuthError):
                R.add_catalog_item(self.db, "equipment", {"code": "BO", "name_ar": "بوب", "name_en": "Bob",
                                                          "parent_code": "LGT", "cost_unit": "day"}, self.cost)
            with self.assertRaises(AuthError):  # الكود مستخدم في نفس الدليل
                R.add_catalog_item(self.db, "equipment", {"code": "ssl", "name_ar": "مكرر", "name_en": "Dup",
                                                          "parent_code": "LGT", "cost_unit": "day"}, self.cost)
            with self.assertRaises(AuthError):  # المعدة تحتاج نوعًا صحيحًا
                R.add_catalog_item(self.db, "equipment", {"code": "FRK", "name_ar": "رافعة شوكية",
                                                          "name_en": "Forklift", "parent_code": "XXX",
                                                          "cost_unit": "day"}, self.cost)
            iid = R.add_catalog_item(self.db, "equipment", {"code": "frk", "name_ar": "رافعة شوكية",
                                                            "name_en": "Forklift", "parent_code": "LGT",
                                                            "cost_unit": "hour"}, self.cost)
            with self.assertRaises(AuthError):
                R.update_catalog_item(self.db, iid, {"code": "FRX", "name_ar": "رافعة", "name_en": "Lift",
                                                     "parent_code": "LGT", "cost_unit": "hour"}, self.cost)
            R.set_catalog_active(self.db, iid, False, self.cost)
        self.assertNotIn("FRK", {r["code"] for r in R.catalog(self.db, "equipment", active_only=True)})
        self.assertIn("FRK", {r["code"] for r in R.catalog(self.db, "equipment")})


class Entities(RegistersBase):
    def test_codes_follow_the_constitution(self):
        _eid, code, people = self.owner_with_people()
        self.assertEqual(code, "ENT-OWN-0001")
        codes = [r[0] for r in self.db.execute("SELECT code FROM entity_people ORDER BY id")]
        self.assertEqual(codes, ["ENT-OWN-0001-R01", "ENT-OWN-0001-R02"])
        with self.app.test_request_context():
            _e, c2 = R.create_entity(self.db, "consultant", {"name": "مكتب الرؤية", "email": "a@b.sa"}, self.cost)
        self.assertEqual(c2, "ENT-CNS-0001")

    def test_subcontractor_needs_registration_status_and_specialties(self):
        base = {"name": "مقاول الحفر", "email": "x@sub.sa"}
        with self.app.test_request_context():
            with self.assertRaises(AuthError):
                R.create_entity(self.db, "subcontractor", base, self.cost)
            with self.assertRaises(AuthError):  # تخصص غير موجود في الدليل لا يُقبل
                R.create_entity(self.db, "subcontractor", MultiDict({**base, "cr_no": "1010", "vat_no": "3000",
                                                                     "approval_status": "approved",
                                                                     "specialties": "XYZ"}), self.cost)
            eid, code = R.create_entity(self.db, "subcontractor", MultiDict([
                *{**base, "cr_no": "1010", "vat_no": "3000", "approval_status": "review"}.items(),
                ("specialties", "CNC"), ("specialties", "STL")]), self.cost)
        self.assertEqual(code, "ENT-SUB-0001")
        self.assertEqual(R.specialties_of(self.db, eid), ["CNC", "STL"])


class ProjectParties(RegistersBase):
    def test_owner_is_required_with_at_least_two_representatives(self):
        eid, _code, people = self.owner_with_people(3)
        with self.app.test_request_context():
            with self.assertRaises(AuthError):
                R.set_project_parties(self.db, self.pid, MultiDict(), self.cost)
            with self.assertRaises(AuthError):  # ممثل واحد لا يكفي
                R.set_project_parties(self.db, self.pid, MultiDict([("owner_entity_id", str(eid)),
                                                                    ("owner_reps", str(people[0]))]), self.cost)
            R.set_project_parties(self.db, self.pid, MultiDict([("owner_entity_id", str(eid)),
                                                                ("owner_reps", str(people[0])),
                                                                ("owner_reps", str(people[1]))]), self.cost)
        p = self.db.execute("SELECT owner_entity_id, client FROM projects WHERE id = ?", (self.pid,)).fetchone()
        self.assertEqual((p["owner_entity_id"], p["client"]), (eid, "شركة التطوير"))
        self.assertTrue(R.parties_complete(self.db, self.pid))
        with self.app.test_request_context():
            with self.assertRaises(AuthError):  # لا يُوقف ممثل في مشروع مفتوح
                R.update_person(self.db, eid, people[0], {"full_name": "ممثل 0", "job_title": "مهندس",
                                                          "phone": "0500000000", "email": "r0@dev.sa"}, self.cost)

    def test_representatives_must_belong_to_the_chosen_entity(self):
        eid, _code, _people = self.owner_with_people(2)
        _other, _c, others = self.owner_with_people(2)
        with self.app.test_request_context():
            with self.assertRaises(AuthError):
                R.set_project_parties(self.db, self.pid, MultiDict([("owner_entity_id", str(eid)),
                                                                    ("owner_reps", str(others[0])),
                                                                    ("owner_reps", str(others[1]))]), self.cost)


class Screens(RegistersBase):
    def test_registers_follow_permissions(self):
        cost, pm = self.client("cost", "CostPass1234"), self.client("pm.one", "PmPass12345")
        for url in ("/registers/entities", "/registers/entities/new?kind=subcontractor", "/registers/lists?kind=equipment"):
            self.assertEqual(cost.get(url).status_code, 200, url)
            self.assertEqual(pm.get(url).status_code, 403, url)
        self.assertEqual(cost.get(f"/projects/{self.pid}/parties").status_code, 200)
        self.assertEqual(pm.get(f"/projects/{self.pid}/parties").status_code, 403)

    def test_entity_flow_through_the_screens(self):
        cost = self.client("cost", "CostPass1234")
        token = self.csrf(cost)
        r = cost.post("/registers/entities/new?kind=owner", data={"csrf_token": token, "kind": "owner",
                                                                  "name": "شركة النخبة", "email": "info@nk.sa"})
        self.assertEqual(r.status_code, 302)
        eid = self.db.execute("SELECT id FROM entities WHERE code = 'ENT-OWN-0001'").fetchone()[0]
        cost.post(f"/registers/entities/{eid}/addresses", data={"csrf_token": token, "label": "main", "city": "الرياض",
                                                               "details": "طريق الملك فهد"})
        for i in range(2):
            cost.post(f"/registers/entities/{eid}/people", data={"csrf_token": token, "full_name": f"ممثل {i}",
                                                                "job_title": "مهندس", "phone": "0550000000",
                                                                "email": f"m{i}@nk.sa"})
        page = cost.get(f"/registers/entities/{eid}").get_data(as_text=True)
        self.assertIn("طريق الملك فهد", page)
        self.assertIn("ENT-OWN-0001-R02", page)
        ids = [str(r[0]) for r in self.db.execute("SELECT id FROM entity_people WHERE entity_id = ?", (eid,))]
        r = cost.post(f"/projects/{self.pid}/parties", data={"csrf_token": token, "owner_entity_id": str(eid),
                                                             "owner_reps": ids, "consultant_entity_id": ""})
        self.assertEqual(r.status_code, 302)
        project = cost.get(f"/projects/{self.pid}").get_data(as_text=True)
        self.assertIn("شركة النخبة", project)
        self.assertIn("ENT-OWN-0001-R01", project)


if __name__ == "__main__":
    unittest.main()
