"""الحسابات الفعّالة حسب الدور."""
from ..rbac import roles

KEY = "accounts_by_role"
TITLE = "Active accounts by role"
PERMISSION = "users.manage"
SIZE = "half"


def data(db, user, scope):
    counts = {r: n for r, n in db.execute("SELECT role, COUNT(*) FROM users WHERE status = 'active' GROUP BY role")}
    rows = [{"role": k, "n": counts.get(k, 0)} for k in roles()]
    top = max((r["n"] for r in rows), default=0)
    for r in rows:
        r["pct"] = round(100 * r["n"] / top, 1) if top else 0
    return {"rows": rows, "total": sum(counts.values())}
