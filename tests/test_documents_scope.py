"""وثائق المشروع (البند 3.1) ونطاق العمل وخطواته (البند 3.7)، وربط التخصيص بخطوة النطاق (القاعدة 6 في البند 3.6)."""
import unittest

from werkzeug.datastructures import MultiDict

from app import documents as D, registers as R, resources as S, scope as W
from app.boq import approve_baseline, delete_item
from app.errors import AuthError

from test_resources import ResourceBase, person

DOC = {"title": "مخطط القواعد الإنشائي", "doc_type": "DRW", "issuer": "consultant", "issued_on": "2026-11-02"}


class DocBase(ResourceBase):
    def setUp(self):
        super().setUp()
        with self.ctx():
            self.cons, _ = R.create_entity(self.db, "consultant", {"name": "مكتب الرؤية", "email": "a@ruya.sa"}, self.cost)
            self.rep, _ = R.add_person(self.db, self.cons, {"full_name": "م. خالد الدوسري", "job_title": "المهندس المقيم",
                                                            "phone": "0504444444", "email": "k@ruya.sa"}, self.cost)
            self.sub, _ = R.create_entity(self.db, "subcontractor", MultiDict([
                ("name", "مؤسسة الإتقان للحفريات"), ("email", "s@b.sa"), ("cr_no", "1010"), ("vat_no", "3000"),
                ("approval_status", "approved"), ("specialties", "CNC")]), self.cost)
            leader = S.save_person(self.db, person("نديم أحمد", prof="TEC", title="SFX", cost="230"), self.cost)
            self.crew = S.save_crew(self.db, {"name": "طاقم الخرسانة 1", "specialty_code": "CNC", "leader_id": str(leader)},
                                    self.cost)

    def drawing(self, **kw):
        with self.ctx():
            return D.create_document(self.db, self.pid, {**DOC, **kw}, self.cost)

    def steps_for(self, iid):
        with self.ctx():
            W.add_step(self.db, self.pid, iid, {"name": "حفر", "weight_pct": "10", "party": "subcontractor",
                                                "entity_id": str(self.sub)}, self.cost)
            W.add_step(self.db, self.pid, iid, {"name": "صب", "weight_pct": "90", "party": "crew",
                                                "crew_id": str(self.crew)}, self.cost)
        return W.steps(self.db, iid)


class Documents(DocBase):
    def test_codes_revisions_and_responses(self):
        did, code = self.drawing()
        _d2, code2 = self.drawing(title="مخطط الأعمدة")
        _d3, code3 = self.drawing(title="مواصفات الخرسانة", doc_type="SPC")
        self.assertEqual((code, code2, code3), (f"{self.pcode}-DOC-DRW-0001", f"{self.pcode}-DOC-DRW-0002",
                                                f"{self.pcode}-DOC-SPC-0001"))
        with self.ctx():
            with self.assertRaises(AuthError):  # رقم المراجعة يزيد دائمًا
                D.add_revision(self.db, self.pid, did, {"rev_no": "0", "rev_date": "2026-11-10"}, self.cost)
            D.add_revision(self.db, self.pid, did, {"rev_no": "1", "rev_date": "2026-11-10"}, self.cost)
            rid = D.revisions(self.db, did)[0]["id"]
            with self.assertRaises(AuthError):  # الاعتماد بملاحظات يحتاج الملاحظات
                D.decide_revision(self.db, self.pid, rid, {"status": "approved_notes"}, self.cost)
            with self.assertRaises(AuthError):  # الممثل من الجهة المعتمِدة نفسها
                D.decide_revision(self.db, self.pid, rid, {"status": "approved", "approver_person_id": str(self.rep)},
                                  self.cost)
            D.decide_revision(self.db, self.pid, rid, {"status": "approved", "approver_entity_id": str(self.cons),
                                                       "approver_person_id": str(self.rep), "approved_on": "2026-11-12"},
                              self.cost)
            with self.assertRaises(AuthError):  # الرد يُسجَّل مرة واحدة
                D.decide_revision(self.db, self.pid, rid, {"status": "rejected", "notes": "مخالف"}, self.cost)
        latest = [r for r in D.documents(self.db, self.pid) if r["id"] == did][0]
        self.assertEqual((latest["rev_no"], latest["rev_status"]), (1, "approved"))

    def test_review_by_someone_else_and_edits_reset_it(self):
        did, _ = self.drawing()
        with self.ctx():
            with self.assertRaises(AuthError):
                D.review_document(self.db, self.pid, did, self.cost)
            D.review_document(self.db, self.pid, did, self.director)
            self.assertTrue(D.document(self.db, self.pid, did)["reviewed_at"])
            D.update_document(self.db, self.pid, did, {**DOC, "title": "مخطط القواعد الإنشائي - معدل"}, self.cost)
        self.assertIsNone(D.document(self.db, self.pid, did)["reviewed_at"])


class Scope(DocBase):
    def test_scope_needs_a_drawing_and_weights_stop_at_100(self):
        with self.ctx():
            iid = self.item(self.pid)
            spec, _ = self.drawing(doc_type="SPC", title="مواصفات الخرسانة")
            form = MultiDict([("summary", "صب خرسانة القواعد المسلحة"), ("includes", "الشدات والحديد والصب والمعالجة"),
                              ("documents", str(spec))])
            with self.assertRaises(AuthError):  # المواصفات وحدها لا تكفي
                W.save_scope(self.db, self.pid, iid, form, self.cost)
            drw, _ = self.drawing()
            form.add("documents", str(drw))
            W.save_scope(self.db, self.pid, iid, form, self.cost)
            rows = self.steps_for(iid)
            with self.assertRaises(AuthError):
                W.add_step(self.db, self.pid, iid, {"name": "معالجة", "weight_pct": "5", "party": "crew",
                                                    "crew_id": str(self.crew)}, self.cost)
        item_code = self.db.execute("SELECT code FROM boq_items WHERE id = ?", (iid,)).fetchone()[0]
        self.assertEqual([r["code"] for r in rows], [f"{item_code}-ST01", f"{item_code}-ST02"])
        self.assertEqual(W.method(rows), "mixed")
        self.assertTrue(all(ok for ok, _t in W.checks(self.db, iid)))

    def test_review_locks_and_reopening_follows_the_baseline(self):
        with self.ctx():
            iid = self.item(self.pid)
            drw, _ = self.drawing()
            W.save_scope(self.db, self.pid, iid, {"summary": "صب خرسانة القواعد", "includes": "كل أعمال القواعد",
                                                  "documents": [str(drw)]}, self.cost)
            with self.assertRaises(AuthError):  # غير مكتمل: لا خطوات
                W.review_scope(self.db, self.pid, iid, self.director)
            self.steps_for(iid)
            with self.assertRaises(AuthError):  # من أعدّه لا يراجعه
                W.review_scope(self.db, self.pid, iid, self.cost)
            W.review_scope(self.db, self.pid, iid, self.director)
            with self.assertRaises(AuthError):  # مقفول بعد المراجعة
                W.add_step(self.db, self.pid, iid, {"name": "معالجة", "weight_pct": "1", "party": "crew",
                                                    "crew_id": str(self.crew)}, self.cost)
            approve_baseline(self.db, self.pid, self.cost)
            with self.assertRaises(AuthError):  # بعد الميزانية يفتحه المدير التنفيذي فقط
                W.reopen_scope(self.db, self.pid, iid, "تعديل المخططات", self.cost)
            W.reopen_scope(self.db, self.pid, iid, "تعديل المخططات", self.director, may_approve=True)
        self.assertIsNone(W.scope_of(self.db, iid)["reviewed_at"])


class AllocationSteps(DocBase):
    def test_allocation_follows_the_step_party(self):
        with self.ctx():
            s = self.staffed(self.pid)
            dig, pour = self.steps_for(s["item"])
            with self.assertRaises(AuthError):  # للبند خطوات، فالخطوة إلزامية
                self.alloc(self.pid, s, kind="crew", rid=self.crew, position_id="")
            with self.assertRaises(AuthError):  # خطوة مقاول الباطن لا يُخصَّص لها طاقم
                self.alloc(self.pid, s, kind="crew", rid=self.crew, position_id="", step_id=str(dig["id"]))
            with self.assertRaises(AuthError):  # خطوة الطاقم لا يُخصَّص لها مقاول باطن
                self.alloc(self.pid, s, kind="subcontractor", rid=self.sub, unit_rate="15", step_id=str(pour["id"]))
            aid, _, warnings = self.alloc(self.pid, s, kind="crew", rid=self.crew, position_id="", step_id=str(pour["id"]))
            self.assertEqual(warnings, [])
            self.alloc(self.pid, s, kind="subcontractor", rid=self.sub, unit_rate="15", step_id=str(dig["id"]))
            with self.assertRaises(AuthError):  # البند عليه تخصيصات فلا يُحذف
                delete_item(self.db, self.pid, s["item"], self.cost)
            with self.assertRaises(AuthError):  # الخطوة عليها تخصيصات فلا تُحذف
                W.delete_step(self.db, self.pid, pour["id"], self.cost)
        self.assertEqual(self.db.execute("SELECT step_id FROM allocations WHERE id = ?", (aid,)).fetchone()[0], pour["id"])


class Screens(DocBase):
    def test_screens_follow_permissions(self):
        iid = None
        with self.ctx():
            iid = self.item(self.pid)
        did, _ = self.drawing()
        pm, cost = self.client("pm.one", "PmPass12345"), self.client("cost", "CostPass1234")
        for url in (f"/projects/{self.pid}/documents", f"/projects/{self.pid}/documents/{did}",
                    f"/projects/{self.pid}/scope", f"/projects/{self.pid}/scope/{iid}", f"/projects/{self.pid}/documents/new"):
            self.assertEqual(pm.get(url).status_code, 200, url)
            self.assertEqual(cost.get(url).status_code, 200, url)
        r = pm.post(f"/projects/{self.pid}/documents/new", data={**DOC, "title": "مخطط الأعمدة", "csrf_token": self.csrf(pm)})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(pm.post(f"/projects/{self.pid}/documents/{did}/review",
                                 data={"csrf_token": self.csrf(pm)}).status_code, 403)
        self.assertEqual(self.client("dir", "DirPass12345").get(f"/projects/{self.pid}/documents/new").status_code, 403)
        self.assertIn("مخطط الأعمدة", pm.get(f"/projects/{self.pid}/documents").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
