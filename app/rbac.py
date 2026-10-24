"""الأدوار والصلاحيات. الفحص يتم على الخادم في كل طلب."""

ROLES = {
    "admin": ("الكوست كنترول (أدمن)", "ADM"),
    "pm": ("مدير مشروع", "PM"),
    "director": ("الدايركتور", "DIR"),
    "accountant": ("المحاسب", "ACC"),
    "viewer": ("مشاهد (إدارة عليا)", "VWR"),
    "owner_rep": ("ممثل المالك", "OWN"),
    "consultant": ("الاستشاري", "CON"),
}

INTERNAL = ("admin", "pm", "director", "accountant", "viewer")
EXTERNAL = ("owner_rep", "consultant")

# الصلاحيات العامة (غير المرتبطة بمشروع)
PERMS = {
    "users.manage": {"admin"},
    "projects.create": {"admin"},
    "projects.manage": {"admin"},          # تعديل بيانات المشروع وطاقمه
    "projects.view_all": {"admin", "director", "viewer"},
    "audit.view": {"admin"},
    "boq.manage": {"admin"},               # تعريف البنود والأسعار والـ WBS واعتماد خط الأساس
}


def role_label(role: str) -> str:
    return ROLES.get(role, (role, ""))[0]


def role_code(role: str) -> str:
    return ROLES[role][1]


def can(user, perm: str) -> bool:
    if user is None or user["status"] != "active":
        return False
    return user["role"] in PERMS.get(perm, set())


def can_view_project(db, user, project_id: int) -> bool:
    if can(user, "projects.view_all"):
        return True
    row = db.execute(
        "SELECT 1 FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user["id"]),
    ).fetchone()
    return row is not None
