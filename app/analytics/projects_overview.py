"""ملخص المشروعات: العدد، قيد التنفيذ، إجمالي قيم العقود، الميزانيات المعتمدة."""
KEY = "projects_overview"
TITLE = "Projects at a glance"
PERMISSION = None   # يكفي صلاحية صفحة التحليلات؛ الأرقام من المشروعات المرئية للمستخدم فقط
SIZE = "full"


def data(db, user, scope):
    rows = scope["projects"]
    return {
        "count": len(rows),
        "active": sum(1 for p in rows if p["status"] == "active"),
        "setup": sum(1 for p in rows if p["status"] == "setup"),
        "contract_total": sum(p["contract_value"] or 0 for p in rows),
        "baselines": sum(1 for p in rows if p["baseline_approved_at"]),
    }
