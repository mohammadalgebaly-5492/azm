"""بوابة بدء التنفيذ (الدستور، البند 4.1)، والتأخير ومسؤوليته وتكلفته (4.5)، والإنذار المبكر وخطط التعافي (4.6)، والإغلاق
والأرشفة (4.10)."""
from datetime import date, timedelta

from . import audit
from .contracts import contract_of
from .db import next_counter, tx, utcnow
from .errors import AuthError
from .i18n import _
from .projects import parse_money

ELEMENTS = {"schedule": "The schedule", "boq": "The BOQ and pricing", "resources": "The resources", "contract": "The contract",
            "scope": "The scopes of work", "subcontractors": "The subcontractors", "org": "The organization chart",
            "documents": "The documents"}
DECISIONS = {"approved": "Approved", "with_cr": "Approved with a change request"}
RESPONSIBLE = {"company": "The company", "owner": "Owner", "consultant": "Consultant", "external": "Beyond both parties' control"}
OPTIONS = {"resources": "More resources", "overtime": "Overtime", "fast_track": "Overlapping execution",
           "resequence": "Re-sequencing"}
PLAN_STATUS = {"review": "Waiting for cost control", "cc_reviewed": "Waiting for the Director", "approved": "Approved",
               "returned": "Returned"}
RECOVERY_DAYS = 7


# ---------- 4.1 بوابة بدء التنفيذ ----------

def kickoff_reviews(db, pid):
    return {r["element"]: r for r in db.execute("SELECT * FROM kickoff_reviews WHERE project_id = ?", (pid,)).fetchall()}


def review_element(db, pid, form, actor_id):
    """مدير المشروع يعتمد عناصر الخطة بندًا بندًا؛ والتعديل يكون بطلب تغيير، لا بتعديل الجزء الأول مباشرة."""
    p = db.execute("SELECT kickoff_at FROM projects WHERE id = ?", (pid,)).fetchone()
    if p["kickoff_at"]:
        raise AuthError(_("Execution has already started."))
    el, dec = form.get("element") or "", form.get("decision") or ""
    if el not in ELEMENTS or dec not in DECISIONS:
        raise AuthError(_("Choose the plan element and the decision."))
    cr = str(form.get("cr_id") or "")
    cr_id = int(cr) if cr.isdigit() and db.execute("SELECT 1 FROM change_requests WHERE id = ? AND project_id = ?",
                                                   (int(cr), pid)).fetchone() else None
    if dec == "with_cr" and not cr_id:
        raise AuthError(_("Choose the change request raised for this element."))
    notes = (form.get("notes") or "").strip() or None
    with tx(db):
        db.execute("DELETE FROM kickoff_reviews WHERE project_id = ? AND element = ?", (pid, el))
        db.execute("INSERT INTO kickoff_reviews(project_id, element, decision, cr_id, notes, decided_at, decided_by) "
                   "VALUES (?,?,?,?,?,?,?)", (pid, el, dec, cr_id if dec == "with_cr" else None, notes, utcnow(), actor_id))
        audit.log(db, actor_id, "kickoff_element", "project", pid, pid, element=el, decision=dec)


def start_execution(db, pid, actor_id) -> str:
    """بعد اعتماد المدير التنفيذي لخطوط الأساس ومراجعة مدير المشروع لكل العناصر: محضر بدء التنفيذ، والمشروع قيد التنفيذ."""
    p = db.execute("SELECT code, kickoff_at, baseline_approved_at, schedule_approved_at FROM projects WHERE id = ?", (pid,)).fetchone()
    if p["kickoff_at"]:
        raise AuthError(_("Execution has already started."))
    if not p["baseline_approved_at"] or not p["schedule_approved_at"]:
        raise AuthError(_("The Director approves the budget and the schedule baselines first."))
    if set(kickoff_reviews(db, pid)) != set(ELEMENTS):
        raise AuthError(_("Review every element of the plan first."))
    with tx(db):
        db.execute("UPDATE projects SET kickoff_at = ?, kickoff_by = ?, status = 'active' WHERE id = ?", (utcnow(), actor_id, pid))
        audit.log(db, actor_id, "kickoff", "project", pid, pid, code=f"{p['code']}-KOF")
    return f"{p['code']}-KOF"


# ---------- 4.5 التأخير ومسؤوليته وتكلفته ----------

def delay_cost_per_day(db, pid, activity_id=None) -> dict:
    """لكل يوم تأخير: غرامة التأخير المحتملة من العقد، وتكلفة الموارد المخصصة المتوقفة على النشاط، والمصاريف غير المباشرة
    اليومية للمشروع."""
    c = contract_of(db, pid)
    penalty = 0
    if c and c["penalty_method"] == "daily_pct" and c["penalty_value"]:
        penalty = c["value_ex_vat"] * c["penalty_value"] // 10000
    elif c and c["penalty_method"] == "daily_amount" and c["penalty_value"]:
        penalty = c["penalty_value"]
    idle = 0
    if activity_id:
        from .resources import _resource, daily_cost_of
        for a in db.execute("SELECT * FROM allocations WHERE activity_id = ? AND status IN ('approved','active') "
                            "AND resource_kind != 'subcontractor'", (activity_id,)).fetchall():
            col = {"person": "person_id", "crew": "crew_id", "equipment": "equipment_id"}[a["resource_kind"]]
            idle += daily_cost_of(db, a["resource_kind"], _resource(db, a["resource_kind"], a[col])) * a["allocation_bp"] // 10000
    overhead = db.execute("SELECT daily_overhead FROM projects WHERE id = ?", (pid,)).fetchone()[0] or 0
    return {"penalty": penalty, "idle": idle, "overhead": overhead, "total": penalty + idle + overhead}


def set_overhead(db, pid, raw, actor_id):
    """المصاريف غير المباشرة اليومية للمشروع (البند 4.5)، يحددها مهندس تحكم تكلفة وتدخل في تكلفة يوم التأخير."""
    value = parse_money(raw)
    if value is None or value < 0:
        raise AuthError(_("Enter the daily indirect cost in SAR."))
    with tx(db):
        db.execute("UPDATE projects SET daily_overhead = ? WHERE id = ?", (value, pid))
        audit.log(db, actor_id, "overhead_set", "project", pid, pid, amount=value)


def record_delay(db, pid, form, actor_id) -> str:
    raw = str(form.get("activity_id") or "")
    act = db.execute("SELECT id FROM activities WHERE id = ? AND project_id = ?", (int(raw), pid)).fetchone() if raw.isdigit() else None
    try:
        days = int(form.get("days") or 0)
    except ValueError:
        days = 0
    if days < 1:
        raise AuthError(_("Enter the delay in days."))
    cause = (form.get("cause") or "").strip()
    if len(cause) < 5:
        raise AuthError(_("Write the cause of the delay."))
    who = form.get("responsible") or ""
    if who not in RESPONSIBLE:
        raise AuthError(_("Choose who is responsible for the delay."))
    cost = delay_cost_per_day(db, pid, act["id"] if act else None)["total"]
    p = db.execute("SELECT code FROM projects WHERE id = ?", (pid,)).fetchone()
    with tx(db):
        # الشركة: خسارة على المشروع. المالك أو الاستشاري أو ظرف خارجي: طلب تمديد مدة ومطالبة
        if who == "company":
            code = f"{p['code']}-DLY-{next_counter(db, 'dly-%d' % pid):03d}"
        else:
            code = f"{p['code']}-CLM-{next_counter(db, 'clm-%d' % pid):03d}"
        db.execute("INSERT INTO delays(project_id, code, activity_id, days, cause, responsible, cost_per_day, created_at, created_by) "
                   "VALUES (?,?,?,?,?,?,?,?,?)", (pid, code, act["id"] if act else None, days, cause, who, cost, utcnow(), actor_id))
        audit.log(db, actor_id, "delay_recorded", "project", pid, pid, code=code, days=days)
    return code


def delays(db, pid):
    return db.execute("SELECT d.*, a.code AS act_code, a.name AS act_name FROM delays d LEFT JOIN activities a ON a.id = d.activity_id "
                      "WHERE d.project_id = ? ORDER BY d.id DESC", (pid,)).fetchall()


# ---------- 4.6 الإنذار المبكر وخطط التعافي ----------

def alert(status) -> dict | None:
    """ما تفعله المنصة حسب الحالة بالألوان (البند 4.3)."""
    return {"yellow": {"level": "warn", "to": _("the project manager and the cost control engineer")},
            "red": {"level": "bad", "to": _("the Director"), "plan": True},
            "critical": {"level": "bad", "to": _("the management and the main account"), "plan": True, "meeting": True}}.get(status)


def suggestions(db, pid, rows, now=None) -> list[dict]:
    """بدائل محسوبة للأنشطة المتأخرة: زيادة الموارد، والعمل الإضافي، والتنفيذ المتداخل (تقديرات للقرار البشري)."""
    now = now or date.today()
    out = []
    for r in rows:
        if r["variance"] <= 0 or r["a"]["actual_finish"]:
            continue
        remaining = max(1, (r["ff"] - max(now, r["fs"])).days + 1)
        daily = delay_cost_per_day(db, pid, r["a"]["id"])["idle"]
        out.append({"a": r["a"], "late": r["variance"], "remaining": remaining, "options": [
            {"key": "resources", "days": remaining // 2, "cost": daily * (remaining // 2)},
            {"key": "overtime", "days": remaining // 5, "cost": daily * 3 // 8 * (remaining - remaining // 5)},
            {"key": "fast_track", "days": min(r["variance"], max(1, r["dur"] * 3 // 10)), "cost": 0},
        ]})
    return out


def plans(db, pid):
    return db.execute("SELECT * FROM recovery_plans WHERE project_id = ? ORDER BY id DESC", (pid,)).fetchall()


def add_plan(db, pid, form, actor_id) -> str:
    opt = form.get("option") or ""
    if opt not in OPTIONS:
        raise AuthError(_("Choose the recovery option."))
    desc = (form.get("description") or "").strip()
    if len(desc) < 10:
        raise AuthError(_("Describe the recovery plan."))
    try:
        days = int(form.get("days_saved") or 0)
    except ValueError:
        days = 0
    cost = parse_money(form.get("extra_cost")) or 0
    p = db.execute("SELECT code FROM projects WHERE id = ?", (pid,)).fetchone()
    with tx(db):
        code = f"{p['code']}-RCV-{next_counter(db, 'rcv-%d' % pid):02d}"
        db.execute("INSERT INTO recovery_plans(project_id, code, option, description, days_saved, extra_cost, created_at, created_by) "
                   "VALUES (?,?,?,?,?,?,?,?)", (pid, code, opt, desc, days, cost, utcnow(), actor_id))
        audit.log(db, actor_id, "recovery_added", "project", pid, pid, code=code)
    return code


def decide_plan(db, pid, plan_id, action, reason, actor_id, director=False):
    """مدير المشروع يُعِد، ومهندس تحكم تكلفة يراجع، والمدير التنفيذي يعتمد."""
    x = db.execute("SELECT * FROM recovery_plans WHERE id = ? AND project_id = ?", (plan_id, pid)).fetchone()
    if x is None:
        raise AuthError(_("This recovery plan doesn't exist."))
    if x["status"] != ("cc_reviewed" if director else "review"):
        raise AuthError(_("This recovery plan is not at this step."))
    if actor_id in (x["created_by"], x["cc_by"]):
        raise AuthError(_("Whoever raised or approved a step can't approve the next one."))
    if action == "return":
        reason = (reason or "").strip()
        if len(reason) < 5:
            raise AuthError(_("Write the reason for returning."))
        sets, args = "status = 'returned', return_reason = ?", (reason,)
    elif director:
        sets, args = "status = 'approved', dir_at = ?, dir_by = ?", (utcnow(), actor_id)
    else:
        sets, args = "status = 'cc_reviewed', cc_at = ?, cc_by = ?", (utcnow(), actor_id)
    with tx(db):
        db.execute(f"UPDATE recovery_plans SET {sets} WHERE id = ?", (*args, plan_id))
        audit.log(db, actor_id, "recovery_" + ("returned" if action == "return" else "approved" if director else "reviewed"),
                  "project", pid, pid, code=x["code"])


def plan_due(db, pid, status) -> bool:
    """أحمر أو حرج بلا خطة تعافي مفتوحة أو معتمدة خلال آخر 30 يومًا: الخطة إلزامية خلال 7 أيام."""
    if status not in ("red", "critical"):
        return False
    since = (date.today() - timedelta(days=30)).isoformat()
    return not db.execute("SELECT 1 FROM recovery_plans WHERE project_id = ? AND status != 'returned' AND created_at >= ?",
                          (pid, since)).fetchone()


# ---------- 4.10 الإغلاق والأرشفة ----------

def closeout(db, pid):
    return db.execute("SELECT * FROM closeouts WHERE project_id = ?", (pid,)).fetchone()


def final_report(db, pid) -> dict:
    """المقارنة النهائية بين المخطط والفعلي في الزمن والتكلفة والهامش، والتغييرات، والتقييم."""
    from .performance import indicators
    ind = indicators(db, pid)
    m = ind["project"]
    c = contract_of(db, pid)
    from .contracts import summary
    value = summary(db, c)["current"] if c else m["bac"]
    n_cr = db.execute("SELECT COUNT(*) FROM change_requests WHERE project_id = ? AND status = 'approved'", (pid,)).fetchone()[0]
    reports = db.execute("SELECT COUNT(*), SUM(CASE WHEN reviewed_at IS NOT NULL AND status = 'approved' THEN 1 ELSE 0 END) "
                         "FROM daily_reports WHERE project_id = ?", (pid,)).fetchone()
    first_time = db.execute("SELECT COUNT(*) FROM daily_reports WHERE project_id = ? AND status = 'approved' AND updated_at IS NULL",
                            (pid,)).fetchone()[0]
    score_parts = [x for x in (m["spi"], m["cpi"]) if x is not None]
    accuracy = first_time * 10000 // reports[0] if reports[0] else None
    if accuracy is not None:
        score_parts.append(accuracy)
    score = min(100, sum(score_parts) // len(score_parts) // 100) if score_parts else None
    return {"m": m, "value": value, "margin": value - m["ac"], "planned_margin": value - m["bac"] if c else 0,
            "changes": n_cr, "reports": reports[0], "accuracy": accuracy, "score": score}


def save_lessons(db, pid, form, actor_id, role):
    co = closeout(db, pid)
    if co and co["status"] == "approved":
        raise AuthError(_("The project is closed."))
    text = (form.get("lessons") or "").strip()
    if len(text) < 10:
        raise AuthError(_("Write the lessons learned."))
    col = "lessons_pm" if role == "pm" else "lessons_cc"
    with tx(db):
        if co is None:
            db.execute(f"INSERT INTO closeouts(project_id, {col}, updated_at, updated_by) VALUES (?,?,?,?)",
                       (pid, text, utcnow(), actor_id))
        else:
            db.execute(f"UPDATE closeouts SET {col} = ?, updated_at = ?, updated_by = ? WHERE project_id = ?",
                       (text, utcnow(), actor_id, pid))
        audit.log(db, actor_id, "lessons_saved", "project", pid, pid)


def close_project(db, pid, actor_id) -> str:
    """اعتماد المدير التنفيذي للإغلاق: تُغلق بيانات المشروع للقراءة فقط."""
    co = closeout(db, pid)
    if co is None or not co["lessons_pm"] or not co["lessons_cc"]:
        raise AuthError(_("The project manager and the cost control engineer write the lessons learned first."))
    if co["status"] == "approved":
        raise AuthError(_("The project is closed."))
    if actor_id == co["updated_by"]:
        raise AuthError(_("Whoever raised or approved a step can't approve the next one."))
    p = db.execute("SELECT code FROM projects WHERE id = ?", (pid,)).fetchone()
    with tx(db):
        db.execute("UPDATE closeouts SET status = 'approved', approved_at = ?, approved_by = ? WHERE project_id = ?",
                   (utcnow(), actor_id, pid))
        db.execute("UPDATE projects SET status = 'closed' WHERE id = ?", (pid,))
        audit.log(db, actor_id, "project_closed", "project", pid, pid, code=f"{p['code']}-CLS")
    return f"{p['code']}-CLS"
