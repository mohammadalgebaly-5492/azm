"""مستويات صلاحية مهندس المشروع وتقييمه الآلي (الدستور، البند 4.4): يحددها مهندس تحكم تكلفة بسبب مكتوب، ويُبلَّغ المدير
التنفيذي، وتُحفظ في السجل. المقيّد والموقوف تمر تقاريرهم بمدير المشروع أولًا، والموقوف لا يرفع طلبات بنفسه."""
from datetime import date, timedelta

from . import audit
from .db import tx, utcnow
from .errors import AuthError
from .i18n import _

LEVELS = {"full": "Full", "restricted": "Restricted", "suspended": "Suspended"}
NOTICE_DAYS = 7


def level_of(db, user_id) -> str:
    r = db.execute("SELECT level FROM engineer_levels WHERE user_id = ?", (user_id,)).fetchone()
    return r["level"] if r else "full"


def ensure_can_raise(db, user_id):
    if level_of(db, user_id) == "suspended":
        raise AuthError(_("Your authority is suspended until re-evaluation. The project manager raises it for you."))


def set_level(db, user_id, level, reason, actor_id):
    if level not in LEVELS:
        raise AuthError(_("Choose the authority level."))
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise AuthError(_("Write the reason for changing the authority."))
    if user_id == actor_id:
        raise AuthError(_("No one changes their own authority."))
    cur = level_of(db, user_id)
    if cur == level:
        raise AuthError(_("This is already the current level."))
    with tx(db):
        db.execute("DELETE FROM engineer_levels WHERE user_id = ?", (user_id,))
        db.execute("INSERT INTO engineer_levels(user_id, level, reason, set_at, set_by) VALUES (?,?,?,?,?)",
                   (user_id, level, reason, utcnow(), actor_id))
        db.execute("INSERT INTO authority_changes(user_id, from_level, to_level, reason, set_at, set_by) VALUES (?,?,?,?,?,?)",
                   (user_id, cur, level, reason, utcnow(), actor_id))
        audit.log(db, actor_id, "authority_changed", "user", user_id, level=level, reason=reason)


def recent_changes(db, days=NOTICE_DAYS):
    since = (date.today() - timedelta(days=days)).isoformat()
    return db.execute("SELECT c.*, u.full_name FROM authority_changes c JOIN users u ON u.id = c.user_id WHERE c.set_at >= ? "
                      "ORDER BY c.id DESC", (since,)).fetchall()


def _days(a, b):
    try:
        return (date.fromisoformat(str(a)[:10]) - date.fromisoformat(str(b)[:10])).days
    except (TypeError, ValueError):
        return 0


def scorecards(db) -> list[dict]:
    """مؤشرات كل من يرفع التقارير اليومية: الالتزام بالمواعيد، ودقة البيانات، وأداء الزمن والتكلفة لمشاريعه، وسرعة الرفع."""
    from .performance import indicators
    cache, out = {}, []
    for u in db.execute("SELECT DISTINCT u.id, u.full_name, u.code FROM daily_reports r JOIN users u ON u.id = r.created_by "
                        "ORDER BY u.full_name").fetchall():
        rows = db.execute("SELECT report_date, created_at, status, times_returned, project_id FROM daily_reports "
                          "WHERE created_by = ?", (u["id"],)).fetchall()
        on_time = sum(1 for r in rows if _days(r["created_at"], r["report_date"]) <= 1)
        approved = [r for r in rows if r["status"] == "approved"]
        clean = sum(1 for r in approved if not r["times_returned"])
        spi, cpi = [], []
        for pid in {r["project_id"] for r in rows}:
            if pid not in cache:
                cache[pid] = indicators(db, pid)["project"]
            if cache[pid]["spi"] is not None:
                spi.append(cache[pid]["spi"])
            if cache[pid]["cpi"] is not None:
                cpi.append(cache[pid]["cpi"])
        out.append({"user": u, "level": level_of(db, u["id"]), "reports": len(rows),
                    "on_time": on_time * 10000 // len(rows) if rows else None,
                    "accuracy": clean * 10000 // len(approved) if approved else None,
                    "spi": sum(spi) // len(spi) if spi else None, "cpi": sum(cpi) // len(cpi) if cpi else None,
                    "delay": sum(max(0, _days(r["created_at"], r["report_date"])) for r in rows) / len(rows) if rows else None})
    return out
