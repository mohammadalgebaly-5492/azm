"""مستويات صلاحية مهندس المشروع وتقييمه الآلي (البند 4.4)."""
import unittest

from app import authority as A, daily as Y, tasks as TK
from app.auth import create_user
from app.errors import AuthError
from app.projects import add_member

from test_daily import DailyBase


class Authority(DailyBase):
    def test_levels_route_reports_through_the_project_manager(self):
        with self.app.app_context():
            pm2, _, _ = create_user(self.db, username="pm.two", email="p2@co.sa", full_name="مدير مشروع ثان", role="pm",
                                    password="PmPass12345")
            add_member(self.db, self.pid, pm2, self.cost)
        with self.ctx():
            with self.assertRaises(AuthError):  # السبب إلزامي
                A.set_level(self.db, self.pm, "restricted", "", self.cost)
            with self.assertRaises(AuthError):  # لا أحد يغيّر صلاحيته بنفسه
                A.set_level(self.db, self.cost, "restricted", "تجربة", self.cost)
            A.set_level(self.db, self.pm, "restricted", "تأخر التقارير ثلاث مرات", self.cost)
            rid, _c, _w = Y.create_report(self.db, self.pid, self.form(2, [self.st1]), self.pm)
            with self.assertRaises(AuthError):  # يفحصه مدير المشروع أولًا
                Y.approve_report(self.db, self.pid, rid, self.cost)
            user2 = self.db.execute("SELECT * FROM users WHERE id = ?", (pm2,)).fetchone()
            self.assertTrue(any(t["code"].endswith("DSR-0001") for t in TK.collect(self.db, user2)))
            Y.pm_check(self.db, self.pid, rid, pm2)
            Y.approve_report(self.db, self.pid, rid, self.cost)
            A.set_level(self.db, self.pm, "suspended", "بيانات غير دقيقة متكررة", self.cost)
            from app import changes as CH
            with self.assertRaises(AuthError):  # الموقوف لا يرفع طلبات بنفسه
                CH.create(self.db, self.pid, {"kind": "internal", "source": "company", "description": "تعديل طريقة التنفيذ",
                                              "items": [str(self.iid)]}, self.pm)
            director = self.db.execute("SELECT * FROM users WHERE id = ?", (self.director,)).fetchone()
            self.assertTrue(any(t["code"] == "suspended" for t in TK.collect(self.db, director)))
        card = [c for c in A.scorecards(self.db) if c["user"]["id"] == self.pm][0]
        self.assertEqual((card["reports"], card["accuracy"], card["level"]), (1, 10000, "suspended"))
        for user, pw in (("cost", "CostPass1234"), ("dir", "DirPass12345")):
            self.assertEqual(self.client(user, pw).get("/engineers").status_code, 200)
        self.assertEqual(self.client("pm.one", "PmPass12345").get("/engineers").status_code, 403)


if __name__ == "__main__":
    unittest.main()
