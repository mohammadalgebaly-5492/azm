"""التقرير اليومي للموقع (الدستور، البند 4.3) ومراجعته (البند 4.4): ما يدخله مهندس المشروع كل يوم، وتنبيهات البيانات
غير المنطقية قبل المراجعة، واعتماد مهندس تحكم تكلفة الذي يدخله في المؤشرات الرسمية."""
from . import audit
from .boq import fmt_qty, parse_qty
from .db import next_counter, tx, utcnow
from .errors import AuthError
from .i18n import _
from .resources import _date, daily_cost_of, _resource
from .schedule import today

STATUS = {"review": "Under review", "approved": "Approved", "returned": "Returned"}
IDLE = {"breakdown": "Breakdown", "no_operator": "No operator", "no_front": "No work front", "weather": "Weather",
        "other": "Other reason"}
COLS = {"person": "person_id", "crew": "crew_id", "equipment": "equipment_id"}


def reports(db, pid):
    return db.execute(
        "SELECT r.*, (SELECT COUNT(*) FROM dsr_activities x WHERE x.report_id = r.id) AS n_acts, "
        "(SELECT COUNT(*) FROM dsr_steps x WHERE x.report_id = r.id) AS n_steps, "
        "(SELECT CAST(COALESCE(SUM(cost), 0) AS BIGINT) FROM dsr_resources x WHERE x.report_id = r.id) AS cost "
        "FROM daily_reports r WHERE r.project_id = ? ORDER BY r.report_date DESC", (pid,)).fetchall()


def report(db, pid, rid):
    return db.execute("SELECT * FROM daily_reports WHERE id = ? AND project_id = ?", (rid, pid)).fetchone()


def details(db, rid) -> dict:
    return {
        "activities": {r[0] for r in db.execute("SELECT activity_id FROM dsr_activities WHERE report_id = ?", (rid,))},
        "steps": {r[0] for r in db.execute("SELECT step_id FROM dsr_steps WHERE report_id = ?", (rid,))},
        "quantities": {r[0]: r[1] for r in db.execute("SELECT boq_item_id, qty_milli FROM dsr_quantities WHERE report_id = ?",
                                                      (rid,))},
        "resources": {r["allocation_id"]: r for r in db.execute("SELECT * FROM dsr_resources WHERE report_id = ?", (rid,))},
    }


def allocations_on(db, pid, on):
    """المخصَّصون المعتمدون للمشروع في ذلك اليوم (الأفراد والأطقم والمعدات)."""
    from .resources import allocations
    return [a for a in allocations(db, pid) if a["status"] in ("approved", "active") and a["resource_kind"] != "subcontractor"
            and str(a["from_date"])[:10] <= on <= str(a["to_date"])[:10]]


def open_steps(db, pid, rid=None):
    """خطوات النطاق التي لم تنتهِ بعد، مع خطوات هذا التقرير."""
    return db.execute(
        "SELECT s.*, b.code AS item_code FROM scope_steps s JOIN boq_items b ON b.id = s.boq_item_id WHERE s.project_id = ? "
        "AND (s.finished_on IS NULL OR s.id IN (SELECT step_id FROM dsr_steps WHERE report_id = ?)) ORDER BY b.code, s.seq",
        (pid, rid or 0)).fetchall()


def _ids(form, key, valid):
    getlist = form.getlist if hasattr(form, "getlist") else (lambda k: form.get(k) or [])
    return sorted({int(x) for x in getlist(key) if str(x).isdigit() and int(x) in valid})


def _clean(db, pid, form, rid=None):
    on = _date(form.get("report_date"), _("the report date"))
    if on > today().isoformat():
        raise AuthError(_("A daily report can't be for a future day."))
    acts = _ids(form, "activities", {r[0] for r in db.execute("SELECT id FROM activities WHERE project_id = ?", (pid,))})
    if not acts:
        raise AuthError(_("Choose the activities worked on that day."))
    steps = _ids(form, "steps", {r["id"] for r in open_steps(db, pid, rid)})
    taken = db.execute("SELECT s.step_id FROM dsr_steps s JOIN daily_reports r ON r.id = s.report_id WHERE r.project_id = ? "
                       "AND r.status != 'approved' AND r.id != ?", (pid, rid or 0)).fetchall()
    if set(steps) & {r[0] for r in taken}:
        raise AuthError(_("A finished step is already in another report waiting for review."))
    qty = {}
    for item in db.execute("SELECT id FROM boq_items WHERE project_id = ?", (pid,)).fetchall():
        raw = (form.get(f"qty_{item['id']}") or "").strip()
        if raw:
            q = parse_qty(raw)
            if q > 0:
                qty[item["id"]] = q
    res = {}
    for a in allocations_on(db, pid, on):
        raw = (form.get(f"hours_{a['id']}") or "").strip()
        if not raw:
            continue
        hours = parse_qty(raw)
        if not 0 < hours <= 24000:
            raise AuthError(_("Working hours must be between 0 and 24."))
        idle = form.get(f"idle_{a['id']}") or None
        if idle and (a["resource_kind"] != "equipment" or idle not in IDLE):
            idle = None
        daily = daily_cost_of(db, a["resource_kind"], _resource(db, a["resource_kind"], a[COLS[a["resource_kind"]]]))
        res[a["id"]] = {"hours": hours, "idle": idle, "cost": daily * hours // (a["hours_per_day"] * 1000)}
    return {"date": on, "activities": acts, "steps": steps, "quantities": qty, "resources": res,
            "issues": (form.get("issues") or "").strip() or None}


def warnings(db, pid, d, rid=None) -> list[str]:
    """البيانات غير المنطقية (البند 4.4): تنبيه قبل المراجعة، لا منع."""
    out = []
    for iid, q in d["quantities"].items():
        item = db.execute("SELECT code, qty_milli FROM boq_items WHERE id = ?", (iid,)).fetchone()
        done = db.execute("SELECT CAST(COALESCE(SUM(q.qty_milli), 0) AS BIGINT) FROM dsr_quantities q JOIN daily_reports r "
                          "ON r.id = q.report_id WHERE q.boq_item_id = ? AND r.status = 'approved' AND r.id != ?",
                          (iid, rid or 0)).fetchone()[0]
        if done + q > item["qty_milli"]:
            out.append(_("Executed quantity of {code} would reach {total}, more than the item quantity {qty}.",
                         code=item["code"], total=fmt_qty(done + q), qty=fmt_qty(item["qty_milli"])))
        plan = db.execute("SELECT CAST(COALESCE(SUM(productivity_milli), 0) AS BIGINT) FROM allocations WHERE boq_item_id = ? "
                          "AND status IN ('approved','active') AND from_date <= ? AND to_date >= ?",
                          (iid, d["date"], d["date"])).fetchone()[0]
        if plan and q * 2 > plan * 3:
            out.append(_("The quantity of {code} today ({q}) is much higher than the planned productivity ({p}).",
                         code=item["code"], q=fmt_qty(q), p=fmt_qty(plan)))
    for aid in d["resources"]:
        a = db.execute("SELECT * FROM allocations WHERE id = ?", (aid,)).fetchone()
        col = COLS[a["resource_kind"]]
        other = db.execute(
            f"SELECT p.code FROM dsr_resources x JOIN allocations o ON o.id = x.allocation_id JOIN daily_reports r ON r.id = x.report_id "
            f"JOIN projects p ON p.id = r.project_id WHERE o.{col} = ? AND r.report_date = ? AND r.project_id != ? LIMIT 1",
            (a[col], d["date"], pid)).fetchone()
        if other:
            out.append(_("Allocation {code} is also recorded on the same day in project {other}.", code=a["code"], other=other[0]))
    if not d["resources"]:
        out.append(_("No people, crews or equipment are recorded for this day."))
    return out


def _write(db, rid, d):
    for t in ("dsr_activities", "dsr_steps", "dsr_quantities", "dsr_resources"):
        db.execute(f"DELETE FROM {t} WHERE report_id = ?", (rid,))
    for a in d["activities"]:
        db.execute("INSERT INTO dsr_activities(report_id, activity_id) VALUES (?, ?)", (rid, a))
    for s in d["steps"]:
        db.execute("INSERT INTO dsr_steps(report_id, step_id) VALUES (?, ?)", (rid, s))
    for i, q in d["quantities"].items():
        db.execute("INSERT INTO dsr_quantities(report_id, boq_item_id, qty_milli) VALUES (?, ?, ?)", (rid, i, q))
    for a, r in d["resources"].items():
        db.execute("INSERT INTO dsr_resources(report_id, allocation_id, hours_milli, idle_reason, cost) VALUES (?,?,?,?,?)",
                   (rid, a, r["hours"], r["idle"], r["cost"]))


def create_report(db, pid, form, actor_id) -> tuple[int, str, list]:
    p = db.execute("SELECT code FROM projects WHERE id = ?", (pid,)).fetchone()
    d = _clean(db, pid, form)
    if db.execute("SELECT 1 FROM daily_reports WHERE project_id = ? AND report_date = ?", (pid, d["date"])).fetchone():
        raise AuthError(_("There is already a report for this day. Open it and edit it instead."))
    warns = warnings(db, pid, d)
    counter = "dsr-%d" % pid
    with tx(db):
        code = f"{p['code']}-DSR-{next_counter(db, counter):04d}"
        from .authority import level_of
        needs_pm = level_of(db, actor_id) != "full"
        rid = db.execute("INSERT INTO daily_reports(project_id, code, report_date, issues, needs_pm, created_at, created_by) "
                         "VALUES (?,?,?,?,?,?,?) RETURNING id",
                         (pid, code, d["date"], d["issues"], needs_pm, utcnow(), actor_id)).fetchone()[0]
        _write(db, rid, d)
        audit.log(db, actor_id, "dsr_submitted", "project", pid, pid, code=code)
    return rid, code, warns


def update_report(db, pid, rid, form, actor_id) -> list:
    cur = report(db, pid, rid)
    if cur is None or cur["status"] == "approved":
        raise AuthError(_("An approved report can't change."))
    d = _clean(db, pid, form, rid)
    if d["date"] != str(cur["report_date"])[:10] and db.execute(
            "SELECT 1 FROM daily_reports WHERE project_id = ? AND report_date = ? AND id != ?", (pid, d["date"], rid)).fetchone():
        raise AuthError(_("There is already a report for this day. Open it and edit it instead."))
    warns = warnings(db, pid, d, rid)
    with tx(db):
        db.execute("UPDATE daily_reports SET report_date = ?, issues = ?, status = 'review', updated_at = ?, pm_checked_at = NULL, "
                   "pm_checked_by = NULL WHERE id = ?", (d["date"], d["issues"], utcnow(), rid))
        _write(db, rid, d)
        audit.log(db, actor_id, "dsr_resubmitted" if cur["status"] == "returned" else "dsr_updated", "project", pid, pid,
                  code=cur["code"])
    return warns


def approve_report(db, pid, rid, actor_id):
    """الاعتماد يدخل التقرير في المؤشرات: تنتهي خطواته في تاريخه، ويبدأ نشاطه فعليًا، وينتهي إذا اكتمل بنده."""
    cur = report(db, pid, rid)
    if cur is None or cur["status"] != "review":
        raise AuthError(_("Only a report under review can be approved."))
    if cur["created_by"] == actor_id:
        raise AuthError(_("Whoever prepares a report can't review it."))
    if cur["needs_pm"] and not cur["pm_checked_at"]:
        raise AuthError(_("The project manager checks this report first: its engineer's authority is restricted."))
    on = str(cur["report_date"])[:10]
    d = details(db, rid)
    with tx(db):
        for s in d["steps"]:
            db.execute("UPDATE scope_steps SET finished_on = ?, finished_by = ? WHERE id = ? AND finished_on IS NULL",
                       (on, cur["created_by"], s))
        for aid in d["activities"]:
            a = db.execute("SELECT * FROM activities WHERE id = ?", (aid,)).fetchone()
            if not a["actual_start"] or str(a["actual_start"])[:10] > on:
                db.execute("UPDATE activities SET actual_start = ? WHERE id = ?", (on, aid))
            if a["boq_item_id"] and not a["actual_finish"]:
                left = db.execute("SELECT COUNT(*) FROM scope_steps WHERE boq_item_id = ? AND finished_on IS NULL",
                                  (a["boq_item_id"],)).fetchone()[0]
                total = db.execute("SELECT CAST(COALESCE(SUM(weight_bp), 0) AS BIGINT) FROM scope_steps WHERE boq_item_id = ?",
                                   (a["boq_item_id"],)).fetchone()[0]
                if total == 10000 and left == 0:
                    db.execute("UPDATE activities SET actual_finish = ? WHERE id = ?", (on, aid))
        db.execute("UPDATE daily_reports SET status = 'approved', reviewed_at = ?, reviewed_by = ?, return_reason = NULL "
                   "WHERE id = ?", (utcnow(), actor_id, rid))
        audit.log(db, actor_id, "dsr_approved", "project", pid, pid, code=cur["code"], count=len(d["steps"]))


def return_report(db, pid, rid, reason, actor_id):
    cur = report(db, pid, rid)
    if cur is None or cur["status"] != "review":
        raise AuthError(_("Only a report under review can be returned."))
    if cur["created_by"] == actor_id:
        raise AuthError(_("Whoever prepares a report can't review it."))
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise AuthError(_("Write the reason for returning the report."))
    with tx(db):
        db.execute("UPDATE daily_reports SET status = 'returned', return_reason = ?, reviewed_at = ?, reviewed_by = ?, "
                   "times_returned = times_returned + 1 WHERE id = ?", (reason, utcnow(), actor_id, rid))
        audit.log(db, actor_id, "dsr_returned", "project", pid, pid, code=cur["code"], reason=reason)


def pm_check(db, pid, rid, actor_id):
    """فحص مدير المشروع لتقرير مهندس صلاحيته مقيّدة أو موقوفة، قبل مراجعة مهندس تحكم تكلفة."""
    cur = report(db, pid, rid)
    if cur is None or cur["status"] != "review" or not cur["needs_pm"] or cur["pm_checked_at"]:
        raise AuthError(_("This report doesn't need the project manager's check now."))
    if cur["created_by"] == actor_id:
        raise AuthError(_("Whoever prepares a report can't review it."))
    with tx(db):
        db.execute("UPDATE daily_reports SET pm_checked_at = ?, pm_checked_by = ? WHERE id = ?", (utcnow(), actor_id, rid))
        audit.log(db, actor_id, "dsr_pm_checked", "project", pid, pid, code=cur["code"])


def actual_cost(db, pid, until=None) -> dict[int, int]:
    """التكلفة الفعلية لكل بند من التقارير المعتمدة: ساعات الأطقم والأفراد والمعدات × تكلفتها."""
    sql = ("SELECT a.boq_item_id, CAST(SUM(x.cost) AS BIGINT) FROM dsr_resources x JOIN daily_reports r ON r.id = x.report_id "
           "JOIN allocations a ON a.id = x.allocation_id WHERE r.project_id = ? AND r.status = 'approved'")
    args = [pid]
    if until:
        sql += " AND r.report_date <= ?"
        args.append(str(until)[:10])
    return {r[0]: r[1] for r in db.execute(sql + " GROUP BY a.boq_item_id", args).fetchall()}

