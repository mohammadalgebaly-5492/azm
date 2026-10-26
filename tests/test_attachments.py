"""تقارير المهندس: نص و/أو ملف PDF على ما يرفعه المهندس (قرار م. محمد 2026-10-26)."""
import io
import os
import re
import unittest

from app import attachments as A
from app.errors import AuthError
from app.projects import add_member

from test_payables import PayBase

PDF = b"%PDF-1.4\n% engineer report\n"


class EngineerReports(PayBase):
    def setUp(self):
        super().setUp()
        self.app.config["UPLOAD_DIR"] = os.path.join(self.tmp.name, "uploads")

    def test_text_and_pdf_reports_are_added_never_empty(self):
        rid, code = self.request()
        with self.ctx():
            with self.assertRaises(AuthError):  # لا تقرير فارغ
                A.add(self.db, self.pid, "pr", rid, "  ", None, None, self.pm)
            with self.assertRaises(AuthError):  # ملف PDF فقط
                A.add(self.db, self.pid, "pr", rid, "", io.BytesIO(b"hello"), "x.pdf", self.pm)
            with self.assertRaises(AuthError):  # مستند من مشروع آخر أو غير موجود
                A.add(self.db, self.pid, "pr", 999, "نص", None, None, self.pm)
            A.add(self.db, self.pid, "pr", rid, "تم حصر الكمية من المخطط S-201.", None, None, self.pm)
            A.add(self.db, self.pid, "pr", rid, "", io.BytesIO(PDF), "survey.pdf", self.pm)
        rows = A.entries(self.db, self.pid, "pr", rid)
        self.assertEqual([(r["body"], r["storage_key"]) for r in rows],
                         [("تم حصر الكمية من المخطط S-201.", None), (None, f"{self.pcode}/reports/{code}-R01.pdf")])
        self.assertEqual(A.counts(self.db, self.pid, "pr"), {rid: 2})
        pm = self.client("pm.one", "PmPass12345")
        page = pm.get(f"/projects/{self.pid}/procurement/{rid}").get_data(as_text=True)
        self.assertIn("survey.pdf", page.replace(f"{code}-R01.pdf", "survey.pdf"))
        r = pm.get(f"/projects/{self.pid}/engineer-reports/file/{rows[1]['id']}")
        self.assertEqual((r.mimetype, r.data), ("application/pdf", PDF))

    def test_only_who_can_raise_the_document_adds_a_report(self):
        rid, _ = self.request()
        with self.app.app_context():
            add_member(self.db, self.pid, self.acc, self.cost)
        acc = self.client("acc", "AccPass12345")
        url = f"/projects/{self.pid}/engineer-reports/pr/{rid}"
        self.assertEqual(acc.get(url).status_code, 200)
        token = re.search(r'name="csrf_token" value="([^"]+)"', acc.get(url).get_data(as_text=True)).group(1)
        self.assertEqual(acc.post(url, data={"csrf_token": token, "body": "تقرير"}).status_code, 403)
        pm = self.client("pm.one", "PmPass12345")
        token = re.search(r'name="csrf_token" value="([^"]+)"', pm.get(url).get_data(as_text=True)).group(1)
        r = pm.post(url, data={"csrf_token": token, "body": "الطلب لتوريد حديد القواعد.",
                               "file": (io.BytesIO(PDF), "takeoff.pdf")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(len(A.entries(self.db, self.pid, "pr", rid)), 1)
        self.assertEqual(pm.get(f"/projects/{self.pid}/engineer-reports/memo/{rid}").status_code, 404)
        for path in ("changes", "payables"):
            self.assertEqual(pm.get(f"/projects/{self.pid}/{path}").status_code, 200)


if __name__ == "__main__":
    unittest.main()
