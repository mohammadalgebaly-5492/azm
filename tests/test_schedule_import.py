"""استيراد الجدول الزمني من Excel أو تصدير Primavera P6 أو Microsoft Project (البند 3.4)."""
import io
import unittest

from app import schedule as T
from app.boq import read_rows

from test_schedule import ScheduleBase, day


class Import(ScheduleBase):
    def codes(self):
        i = {r[0]: r[1] for r in self.db.execute("SELECT id, code FROM boq_items WHERE project_id = ?", (self.pid,))}
        w = {r[0]: r[1] for r in self.db.execute("SELECT id, code FROM wbs_nodes WHERE project_id = ?", (self.pid,))}
        return i, w

    def test_all_or_nothing_with_predecessors(self):
        i, w = self.codes()
        csv = ("Activity ID,Activity Name,Item,Start,Finish,Predecessors\n"
               f"A10,حفر,{i[self.i1]},{day(0)},{day(9)},\n"
               f"A20,خرسانة,{i[self.i2]},{day(10)},{day(29)},A10FS\n"
               f"A30,تشطيبات,{w[self.w2]},{day(30)},{day(39)},A20\n")
        bad = csv.replace(",A10FS", ",A99")
        with self.ctx():
            n, errors = T.import_rows(self.db, self.pid, read_rows("x.csv", io.BytesIO(bad.encode())), self.pm)
            self.assertEqual((n, len(errors)), (0, 1))  # سابق غير موجود: لا يُستورد شيء
            self.assertEqual(T.activities(self.db, self.pid), [])
            n, errors = T.import_rows(self.db, self.pid, read_rows("x.csv", io.BytesIO(csv.encode())), self.pm)
        self.assertEqual((n, errors), (3, []))
        rows = {r["a"]["name"]: r for r in T.compute(self.db, self.pid)}
        self.assertEqual(len(rows["خرسانة"]["preds"]), 1)
        self.assertEqual(rows["تشطيبات"]["a"]["boq_item_id"], None)


if __name__ == "__main__":
    unittest.main()
