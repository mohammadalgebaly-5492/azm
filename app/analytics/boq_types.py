"""توزيع إجمالي جداول الكميات حسب نوع البند (توريد / تنفيذ / توريد وتنفيذ)."""
from ..boq import TYPES

KEY = "boq_types"
TITLE = "BOQ value by item type"
PERMISSION = None
SIZE = "half"


def data(db, user, scope):
    ids = [p["id"] for p in scope["projects"]]
    by = {t: 0 for t in TYPES}
    if ids:
        marks = ",".join("?" * len(ids))
        for t, v in db.execute(f"SELECT item_type, CAST(SUM(amount) AS BIGINT) FROM boq_items WHERE project_id IN ({marks}) "
                               "GROUP BY item_type", ids):
            by[t] = v or 0
    total = sum(by.values())
    x, segs = 0.0, []
    for t in TYPES:
        w = 100 * by[t] / total if total else 0
        segs.append({"type": t, "value": by[t], "pct": round(w, 1), "x": round(x, 3), "w": round(w, 3)})
        x += w
    return {"total": total, "segs": segs}
