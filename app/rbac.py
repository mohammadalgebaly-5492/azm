"""الأدوار والصلاحيات. الفحص يتم على الخادم في كل طلب.

الأدوار بيانات في جدول roles يديرها مدير النظام (إنشاء، إعادة تسمية، حذف)، وصلاحيات كل دور في
role_permissions. دور مدير النظام (superadmin) ثابت وله كل الصلاحيات دائمًا.
"""
import re

from flask import g, has_request_context

from .errors import AuthError
from .i18n import _, current_lang

OWNER = "superadmin"
CODE_RE = re.compile(r"^[A-Z]{2,5}$")


def load_roles(db) -> dict:
    """الأدوار مرتبة: المفتاح → صف (key, code, name_ar, name_en, external, system, sort)."""
    return {r["key"]: r for r in db.execute("SELECT * FROM roles ORDER BY sort, created_at, key")}


def roles(db=None) -> dict:
    if db is not None or not has_request_context():
        from .db import get_db
        return load_roles(db or get_db())
    if "roles" not in g:
        from .db import get_db
        g.roles = load_roles(get_db())
    return g.roles


def internal_roles(db=None):
    return [k for k, r in roles(db).items() if not r["external"]]


def external_roles(db=None):
    return [k for k, r in roles(db).items() if r["external"]]


# كتالوج الصلاحيات: كل صلاحية تحمي جزءًا حقيقيًا من المنصة (شاشة أو تبويب أو زر).
# الميزة الجديدة تضيف صلاحيتها هنا مرة واحدة، ومن بعدها توزيعها على الأدوار من الواجهة بدون كود.
# المفتاح: (الاسم، الوصف). الترجمة في i18n_ar.py
PERMISSIONS = {
    "projects.view_all": ("See all projects", "Without this, an account only sees the projects it is assigned to."),
    "analytics.view": ("View analytics", "Open the Analytics page. Each card also follows the role's other permissions."),
    "projects.create": ("Create projects", "Register new projects and their main contract."),
    "projects.manage": ("Edit projects and teams", "Edit project and contract details, assign and remove team members."),
    "boq.manage": ("Manage BOQ and baseline",
                   "Define WBS sections, items and rates, import from Excel, approve the baseline."),
    "changes.approve": ("Approve change orders and allocations",
                        "Approve or reject change orders on the main contract, and approve resource allocations."),
    "users.manage": ("Manage accounts",
                     "Create accounts, change roles and assigned projects, reset passwords, disable accounts."),
    "admin.invites": ("Manage sign-up links", "Create and revoke sign-up links, and turn sign-up on or off."),
    "admin.sessions": ("Manage active sessions", "See who is signed in and end their sessions."),
    "audit.view": ("View audit log", "Read the full history of actions on the platform."),
    "admin.settings": ("Edit platform settings", "Change the platform and company names and the session limits."),
    "documents.manage": ("Record documents and scope of work",
                         "Register project documents and their revisions, and write each item's scope and execution steps."),
    "schedule.manage": ("Prepare the schedule and record progress",
                        "Add and edit schedule activities before approval, record actual dates and finished scope steps."),
    "procurement.request": ("Raise purchase and subcontract requests",
                            "Write the required scope of an item and raise a request for materials, a subcontract or a rental."),
    "procurement.quotes": ("Collect quotes", "Add the quotes of suppliers and subcontractors to a request."),
    "procurement.select": ("Choose the quote", "Review the comparison of quotes and choose one, with a reason when it isn't the lowest."),
    "procurement.approve": ("Approve purchases and subcontracts",
                            "Approve a chosen quote against the item budget. Above 10,000 SAR the Director approves too."),
    "payables.raise": ("Raise certificates and invoices",
                       "Record goods receipts, and raise subcontractor certificates and supplier invoices."),
    "payables.approve": ("Approve certificates and invoices",
                         "Approve certificates and invoices up to 10,000 SAR; above it the Director approves too."),
    "payables.pay": ("Pay and collect", "Record payments of approved certificates and invoices, and collections from the owner."),
    "billing.prepare": ("Prepare owner certificates", "Prepare the company's certificates to the owner, submit them and record their certification."),
    "changes.request": ("Raise and review change requests",
                        "Raise a change request on the project plan, or review one raised by another engineer."),
    "registers.manage": ("Manage shared registers",
                         "Owners, consultants and subcontractors with their addresses and people, and the lookup lists."),
}
PERMISSION_GROUPS = (
    ("Projects", ("projects.view_all", "projects.create", "projects.manage", "boq.manage", "documents.manage",
                  "schedule.manage", "changes.request", "changes.approve")),
    ("Procurement", ("procurement.request", "procurement.quotes", "procurement.select", "procurement.approve")),
    ("Payments", ("payables.raise", "payables.approve", "payables.pay", "billing.prepare")),
    ("Analytics", ("analytics.view",)),
    ("Registers", ("registers.manage",)),
    ("Accounts", ("users.manage", "admin.invites")),
    ("Administration", ("admin.sessions", "audit.view", "admin.settings")),
)
# صلاحيات أي تبويب في قسم الإدارة؛ من يملك واحدة منها يرى قسم الإدارة بالتبويبات المسموح له بها فقط
ADMIN_AREA = ("roles.manage", "admin.sessions", "audit.view", "admin.settings", "admin.invites")

# صلاحيات لمدير النظام فقط ولا تظهر في شاشة الأدوار: تمنع أي دور من رفع صلاحياته بنفسه
OWNER_ONLY = (
    "roles.manage",         # إنشاء الأدوار وتعديلها وتوزيع الصلاحيات
    "users.manage_owners",  # إنشاء حسابات مدير النظام أو تعديلها أو إيقافها
)


def role_label(role: str) -> str:
    r = roles().get(role)
    return (r["name_ar"] if current_lang() == "ar" else r["name_en"]) if r else role


def role_code(db, role: str) -> str:
    r = db.execute("SELECT code FROM roles WHERE key = ?", (role,)).fetchone()
    if r is None:
        raise AuthError(_("Unknown role."))
    return r[0]


def role_exists(db, role: str) -> bool:
    return db.execute("SELECT 1 FROM roles WHERE key = ?", (role or "",)).fetchone() is not None


def load_role_permissions(db) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for role, perm in db.execute("SELECT role, permission FROM role_permissions"):
        out.setdefault(role, set()).add(perm)
    return out


def _role_permissions() -> dict[str, set[str]]:
    from .db import get_db
    if "role_perms" not in g:
        g.role_perms = load_role_permissions(get_db())
    return g.role_perms


def can(user, perm: str) -> bool:
    if user is None or user["status"] != "active":
        return False
    if user["role"] == OWNER:
        return True
    if perm in OWNER_ONLY or not has_request_context():
        return False
    return perm in _role_permissions().get(user["role"], set())


def can_any(user, perms) -> bool:
    return any(can(user, p) for p in perms)


def roles_with(db, perm: str) -> set[str]:
    """الأدوار اللي معاها صلاحية معيّنة، شاملة مدير النظام."""
    return {r for r, perms in load_role_permissions(db).items() if perm in perms} | {OWNER}


def save_role_permissions(db, role: str, wanted: set[str], actor_id: int) -> int:
    """يستبدل صلاحيات دور واحد. يرجع عدد التغييرات."""
    from . import audit
    from .db import tx
    if role == OWNER or not role_exists(db, role):
        raise AuthError(_("This role's permissions can't be changed."))
    want = {p for p in wanted if p in PERMISSIONS}
    have = load_role_permissions(db).get(role, set()) & set(PERMISSIONS)
    added, removed = sorted(want - have), sorted(have - want)
    if not added and not removed:
        return 0
    with tx(db):
        for perm in removed:
            db.execute("DELETE FROM role_permissions WHERE role = ? AND permission = ?", (role, perm))
        for perm in added:
            db.execute("INSERT INTO role_permissions(role, permission) VALUES (?, ?)", (role, perm))
        audit.log(db, actor_id, "permissions_updated", "role", None, role=role, added=added, removed=removed)
    g.pop("role_perms", None)
    return len(added) + len(removed)


def _clean_role(db, form, key=None):
    name_ar, name_en = (form.get("name_ar") or "").strip(), (form.get("name_en") or "").strip()
    code = (form.get("code") or "").strip().upper()
    if not (2 <= len(name_ar) <= 60 and 2 <= len(name_en) <= 60):
        raise AuthError(_("Enter the role name in Arabic and English (2 to 60 characters)."))
    if not CODE_RE.match(code):
        raise AuthError(_("The role code is 2 to 5 English capital letters, e.g. QS."))
    if db.execute("SELECT 1 FROM roles WHERE code = ? AND key != ?", (code, key or "")).fetchone():
        raise AuthError(_("Another role already uses this code."))
    return {"name_ar": name_ar, "name_en": name_en, "code": code, "external": bool(form.get("external"))}


def create_role(db, form, actor_id: int) -> str:
    from . import audit
    from .db import tx
    data = _clean_role(db, form)
    key = data["code"].lower()
    n = 1
    while role_exists(db, key):
        n += 1
        key = f"{data['code'].lower()}{n}"
    sort = (db.execute("SELECT MAX(sort) FROM roles").fetchone()[0] or 0) + 10
    with tx(db):
        db.execute("INSERT INTO roles(key, code, name_ar, name_en, external, system, sort) VALUES (?, ?, ?, ?, ?, FALSE, ?)",
                   (key, data["code"], data["name_ar"], data["name_en"], data["external"], sort))
        audit.log(db, actor_id, "role_created", "role", None, role=key, **data)
    g.pop("roles", None)
    return key


def update_role(db, key: str, form, actor_id: int):
    from . import audit
    from .db import tx
    cur = roles(db).get(key)
    if cur is None or cur["system"]:
        raise AuthError(_("This role can't be edited."))
    data = _clean_role(db, form, key)
    changes = {k: v for k, v in data.items() if (bool(cur[k]) if k == "external" else cur[k]) != v}
    if not changes:
        return
    with tx(db):
        db.execute(f"UPDATE roles SET {', '.join(f'{k} = ?' for k in changes)} WHERE key = ?", (*changes.values(), key))
        audit.log(db, actor_id, "role_updated", "role", None, role=key,
                  **{k: {"from": cur[k], "to": v} for k, v in changes.items()})
    g.pop("roles", None)


def delete_role(db, key: str, actor_id: int):
    from . import audit
    from .db import tx
    cur = roles(db).get(key)
    if cur is None or cur["system"]:
        raise AuthError(_("This role can't be deleted."))
    n = db.execute("SELECT COUNT(*) FROM users WHERE role = ?", (key,)).fetchone()[0]
    if n:
        raise AuthError(_("{n} accounts use this role. Move them to another role first.", n=n))
    with tx(db):
        db.execute("DELETE FROM role_permissions WHERE role = ?", (key,))
        db.execute("DELETE FROM roles WHERE key = ?", (key,))
        audit.log(db, actor_id, "role_deleted", "role", None, role=key, code=cur["code"], name=cur["name_en"])
    g.pop("roles", None)


def can_view_project(db, user, project_id: int) -> bool:
    if can(user, "projects.view_all"):
        return True
    row = db.execute(
        "SELECT 1 FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user["id"]),
    ).fetchone()
    return row is not None
