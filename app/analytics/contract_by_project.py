"""قيمة العقد لكل مشروع، مرتبة من الأكبر."""
KEY = "contract_by_project"
TITLE = "Contract value by project"
PERMISSION = None
SIZE = "half"
LIMIT = 8


def data(db, user, scope):
    rows = sorted((p for p in scope["projects"] if p["contract_value"]), key=lambda p: -p["contract_value"])
    top = max((p["contract_value"] for p in rows), default=0)
    return {"rows": [{"id": p["id"], "code": p["code"], "name": p["name"], "value": p["contract_value"],
                      "pct": round(100 * p["contract_value"] / top, 1) if top else 0} for p in rows[:LIMIT]],
            "more": max(0, len(rows) - LIMIT)}
