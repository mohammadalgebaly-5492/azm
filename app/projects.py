"""منطق المشروعات وطاقمها."""
import re
from datetime import date

from . import audit
from .auth import AuthError
from .db import next_counter, tx, utcnow


def parse_money(v) -> int | None:
    """يحوّل '1,250,000.50' إلى هللات (125000050). الفراغ = None."""
    s = (v or "").strip().replace(",", "").replace("٬", "")
    s = s.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")).replace("٫", ".")
    if not s:
        return None
    if not re.fullmatch(r"\d+(\.\d{1,2})?", s):
        raise AuthError("صيغة المبلغ غير صحيحة.")
    whole, _, frac = s.partition(".")
    return int(whole) * 100 + int((frac + "00")[:2])


def fmt_money(h) -> str:
    if h is None:
        return "—"
    sign = "-" if h < 0 else ""
    h = abs(int(h))
    return f"{sign}{h // 100:,}.{h % 100:02d}"


def _date(v):
    v = (v or "").strip()
    if not v:
        return None
    try:
        return date.fromisoformat(v).isoformat()
    except ValueError:
        raise AuthError("صيغة التاريخ غير صحيحة.")


def _validate(f):
    name = (f.get("name") or "").strip()
    if len(name) < 3:
        raise AuthError("أدخل اسم المشروع.")
    start, end = _date(f.get("start_date")), _date(f.get("end_date"))
    if start and end and end <= start:
        raise AuthError("تاريخ النهاية يجب أن يكون بعد تاريخ البداية.")
    return {
        "name": name,
        "client": (f.get("client") or "").strip() or None,
        "consultant": (f.get("consultant") or "").strip() or None,
        "location": (f.get("location") or "").strip() or None,
        "contract_no": (f.get("contract_no") or "").strip() or None,
        "contract_value": parse_money(f.get("contract_value")),
        "start_date": start,
        "end_date": end,
    }


def create_project(db, form, actor_id) -> tuple[int, str]:
    data = _validate(form)
    year = (data["start_date"] or utcnow())[:4]
    with tx(db):
        n = next_counter(db, f"project-{year}")
        code = f"P-{year}-{n:03d}"
        cur = db.execute(
            "INSERT INTO projects(code, name, client, consultant, location, contract_no, contract_value, "
            "start_date, end_date, created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?) RETURNING id",
            (code, data["name"], data["client"], data["consultant"], data["location"], data["contract_no"],
             data["contract_value"], data["start_date"], data["end_date"], utcnow(), actor_id))
        pid = cur.fetchone()[0]
        audit.log(db, actor_id, "project_created", "project", pid, pid, code=code, name=data["name"])
    return pid, code


def update_project(db, pid, form, actor_id):
    data = _validate(form)
    status = form.get("status") or "setup"
    if status not in ("setup", "active", "closed"):
        raise AuthError("حالة المشروع غير معروفة.")
    data["status"] = status
    cur = db.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    changes = {k: v for k, v in data.items() if cur[k] != v}
    if not changes:
        return
    with tx(db):
        db.execute(f"UPDATE projects SET {', '.join(f'{k} = ?' for k in changes)} WHERE id = ?",
                   (*changes.values(), pid))
        audit.log(db, actor_id, "project_updated", "project", pid, pid,
                  **{k: {"from": cur[k], "to": v} for k, v in changes.items()})


def add_member(db, pid, user_id, actor_id):
    u = db.execute("SELECT status FROM users WHERE id = ?", (user_id,)).fetchone()
    if u is None or u["status"] != "active":
        raise AuthError("الحساب غير موجود أو موقوف.")
    with tx(db):
        cur = db.execute("INSERT INTO project_members(project_id, user_id, assigned_at, assigned_by) "
                         "VALUES (?,?,?,?) ON CONFLICT DO NOTHING", (pid, user_id, utcnow(), actor_id))
        if cur.rowcount:
            audit.log(db, actor_id, "member_added", "user", user_id, pid)


def remove_member(db, pid, user_id, actor_id):
    with tx(db):
        cur = db.execute("DELETE FROM project_members WHERE project_id = ? AND user_id = ?", (pid, user_id))
        if cur.rowcount:
            audit.log(db, actor_id, "member_removed", "user", user_id, pid)


def visible_projects(db, user, can_view_all: bool):
    if can_view_all:
        return db.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    return db.execute(
        "SELECT p.* FROM projects p JOIN project_members m ON m.project_id = p.id "
        "WHERE m.user_id = ? ORDER BY p.created_at DESC", (user["id"],)).fetchall()


def members(db, pid):
    return db.execute(
        "SELECT u.id, u.code, u.full_name, u.role, u.status, u.job_title, m.assigned_at FROM project_members m "
        "JOIN users u ON u.id = m.user_id WHERE m.project_id = ? ORDER BY u.role, u.full_name", (pid,)).fetchall()
