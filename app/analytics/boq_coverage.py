"""تغطية جدول الكميات لقيمة العقد في كل مشروع (إجمالي البنود ÷ قيمة العقد)."""
KEY = "boq_coverage"
TITLE = "BOQ coverage of contract value"
PERMISSION = None
SIZE = "half"


def data(db, user, scope):
    ids = [p["id"] for p in scope["projects"]]
    if not ids:
        return {"rows": []}
    marks = ",".join("?" * len(ids))
    totals = {r[0]: r[1] for r in db.execute(
        f"SELECT project_id, CAST(SUM(amount) AS BIGINT) FROM boq_items WHERE project_id IN ({marks}) GROUP BY project_id", ids)}
    rows = []
    for p in scope["projects"]:
        if not p["contract_value"]:
            continue
        boq = totals.get(p["id"], 0) or 0
        pct = 100 * boq / p["contract_value"]
        rows.append({"id": p["id"], "code": p["code"], "name": p["name"], "boq": boq, "contract": p["contract_value"],
                     "pct": round(pct, 1), "bar": round(min(pct, 100), 1), "locked": bool(p["baseline_approved_at"])})
    return {"rows": sorted(rows, key=lambda r: -r["pct"])}
