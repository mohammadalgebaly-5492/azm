"""الجدول الزمني للمتابعة (الدستور، البند 3.4): الأنشطة وعلاقاتها، والمخطط مقابل الفعلي والمتوقع، والإنجاز من خطوات النطاق،
والمراجعة والاعتماد كخط أساس للزمن. وجدول الدفعات التعاقدية المربوط بالأنشطة (البند 3.2)."""
from datetime import date, timedelta

from . import audit
from .contracts import contract_of, fmt_pct, parse_pct, summary
from .db import next_counter, tx, utcnow
from .errors import AuthError
from .i18n import _
from .resources import _date

FULL = 10000


def _d(v):
    return date.fromisoformat(str(v)[:10]) if v else None


def today():
    return date.today()


# ---------- الأنشطة ----------

def activities(db, pid):
    return db.execute(
        "SELECT a.*, w.code AS wbs_code, w.name AS wbs_name, b.code AS item_code, b.description AS item_desc, "
        "b.amount AS item_amount FROM activities a JOIN wbs_nodes w ON w.id = a.wbs_id "
        "LEFT JOIN boq_items b ON b.id = a.boq_item_id WHERE a.project_id = ? ORDER BY w.code, a.code", (pid,)).fetchall()


def links(db, pid) -> dict[int, list[int]]:
    out = {}
    for a, p in db.execute("SELECT l.activity_id, l.predecessor_id FROM activity_links l JOIN activities a ON a.id = l.activity_id "
                           "WHERE a.project_id = ?", (pid,)).fetchall():
        out.setdefault(a, []).append(p)
    return out


def state(db, pid):
    return db.execute("SELECT schedule_reviewed_at, schedule_reviewed_by, schedule_approved_at, schedule_approved_by "
                      "FROM projects WHERE id = ?", (pid,)).fetchone()


def _ensure_open(db, pid):
    if state(db, pid)["schedule_approved_at"]:
        raise AuthError(_("The schedule is approved as a baseline. The planned dates can't change now."))


def _cycle(graph: dict[int, list[int]]) -> bool:
    seen, stack = set(), set()

    def visit(n):
        if n in stack:
            return True
        if n in seen:
            return False
        seen.add(n)
        stack.add(n)
        found = any(visit(m) for m in graph.get(n, []))
        stack.discard(n)
        return found
    return any(visit(n) for n in list(graph))


def _clean(db, pid, form, aid=None):
    name = (form.get("name") or "").strip()
    if len(name) < 3:
        raise AuthError(_("Enter the activity name."))
    kind, _sep, num = str(form.get("link") or "").partition("-")
    wbs_id = item_id = None
    if num.isdigit() and kind == "item":
        r = db.execute("SELECT id, wbs_id FROM boq_items WHERE id = ? AND project_id = ?", (int(num), pid)).fetchone()
        if r:
            item_id, wbs_id = r["id"], r["wbs_id"]
    elif num.isdigit() and kind == "wbs":
        r = db.execute("SELECT id FROM wbs_nodes WHERE id = ? AND project_id = ?", (int(num), pid)).fetchone()
        wbs_id = r["id"] if r else None
    if wbs_id is None:
        raise AuthError(_("Choose the item or WBS section of the activity."))
    start, finish = _date(form.get("planned_start"), _("the planned start")), _date(form.get("planned_finish"), _("the planned finish"))
    if finish < start:
        raise AuthError(_("The planned finish must be on or after the planned start."))
    getlist = form.getlist if hasattr(form, "getlist") else (lambda k: form.get(k) or [])
    valid = {r[0] for r in db.execute("SELECT id FROM activities WHERE project_id = ?", (pid,)).fetchall()}
    preds = sorted({int(x) for x in getlist("predecessors") if str(x).isdigit() and int(x) in valid and int(x) != aid})
    if aid is not None:
        graph = links(db, pid)
        graph[aid] = preds
        if _cycle(graph):
            raise AuthError(_("These predecessors make a loop: an activity would wait for itself."))
    return {"name": name, "wbs_id": wbs_id, "boq_item_id": item_id, "planned_start": start, "planned_finish": finish,
            "notes": (form.get("notes") or "").strip() or None}, preds


def add_activity(db, pid, form, actor_id) -> tuple[int, str]:
    _ensure_open(db, pid)
    a, preds = _clean(db, pid, form)
    wbs = db.execute("SELECT code FROM wbs_nodes WHERE id = ?", (a["wbs_id"],)).fetchone()
    counter = "act-%d" % a["wbs_id"]
    with tx(db):
        code = f"{wbs['code']}-A{next_counter(db, counter) * 10:03d}"
        aid = db.execute(f"INSERT INTO activities(project_id, code, {', '.join(a)}, created_at, created_by) "
                         f"VALUES (?, ?, {', '.join('?' for _ in a)}, ?, ?) RETURNING id",
                         (pid, code, *a.values(), utcnow(), actor_id)).fetchone()[0]
        for p in preds:
            db.execute("INSERT INTO activity_links(activity_id, predecessor_id) VALUES (?, ?)", (aid, p))
        _reset_review(db, pid)
        audit.log(db, actor_id, "activity_added", "project", pid, pid, code=code, name=a["name"])
    return aid, code


def _activity(db, pid, aid):
    row = db.execute("SELECT * FROM activities WHERE id = ? AND project_id = ?", (aid, pid)).fetchone()
    if row is None:
        raise AuthError(_("This activity doesn't exist."))
    return row


def _reset_review(db, pid):
    """أي تعديل على المخطط قبل الاعتماد يعيد الجدول للمراجعة."""
    db.execute("UPDATE projects SET schedule_reviewed_at = NULL, schedule_reviewed_by = NULL WHERE id = ?", (pid,))


def update_activity(db, pid, aid, form, actor_id):
    _ensure_open(db, pid)
    cur = _activity(db, pid, aid)
    a, preds = _clean(db, pid, form, aid)
    if a["wbs_id"] != cur["wbs_id"]:
        raise AuthError(_("The section is part of the activity code and can't change. Delete the activity and add it again."))
    changes = {k: v for k, v in a.items() if (str(cur[k])[:10] if k.startswith("planned") else cur[k]) != v}
    old = sorted(links(db, pid).get(aid, []))
    with tx(db):
        if changes:
            db.execute(f"UPDATE activities SET {', '.join(f'{k} = ?' for k in changes)} WHERE id = ?", (*changes.values(), aid))
        if preds != old:
            db.execute("DELETE FROM activity_links WHERE activity_id = ?", (aid,))
            for p in preds:
                db.execute("INSERT INTO activity_links(activity_id, predecessor_id) VALUES (?, ?)", (aid, p))
        if changes or preds != old:
            _reset_review(db, pid)
            audit.log(db, actor_id, "activity_updated", "project", pid, pid, code=cur["code"],
                      **{k: {"from": str(cur[k])[:10] if k.startswith("planned") else cur[k], "to": v}
                         for k, v in changes.items() if k in ("name", "planned_start", "planned_finish")})


def delete_activity(db, pid, aid, actor_id):
    _ensure_open(db, pid)
    cur = _activity(db, pid, aid)
    if db.execute("SELECT 1 FROM payment_milestones WHERE activity_id = ?", (aid,)).fetchone():
        raise AuthError(_("A contract payment is linked to this activity. Remove the payment first."))
    if db.execute("SELECT 1 FROM allocations WHERE activity_id = ?", (aid,)).fetchone():
        raise AuthError(_("Resources are allocated to this activity, so it can't be deleted."))
    with tx(db):
        db.execute("DELETE FROM activities WHERE id = ?", (aid,))
        _reset_review(db, pid)
        audit.log(db, actor_id, "activity_deleted", "project", pid, pid, code=cur["code"])


def set_actual(db, pid, aid, form, actor_id):
    """التواريخ الفعلية تُحدَّث أثناء التنفيذ دون المساس بالمخطط."""
    cur = _activity(db, pid, aid)
    start = _date(form.get("actual_start"), _("the actual start"), required=False)
    finish = _date(form.get("actual_finish"), _("the actual finish"), required=False)
    now = today().isoformat()
    if finish and not start:
        raise AuthError(_("Enter the actual start before the actual finish."))
    if (start and start > now) or (finish and finish > now):
        raise AuthError(_("Actual dates can't be in the future."))
    if start and finish and finish < start:
        raise AuthError(_("The actual finish must be on or after the actual start."))
    with tx(db):
        db.execute("UPDATE activities SET actual_start = ?, actual_finish = ? WHERE id = ?", (start, finish, aid))
        audit.log(db, actor_id, "activity_progress", "project", pid, pid, code=cur["code"], actual_start=start,
                  actual_finish=finish)


def finish_step(db, pid, sid, finished_on, actor_id):
    """تسجيل انتهاء خطوة من خطوات نطاق العمل؛ منها تُحسب نسبة إنجاز البند."""
    st = db.execute("SELECT * FROM scope_steps WHERE id = ? AND project_id = ?", (sid, pid)).fetchone()
    if st is None:
        raise AuthError(_("This step doesn't exist."))
    on = _date(finished_on, _("the finish date"), required=False)
    if on and on > today().isoformat():
        raise AuthError(_("Actual dates can't be in the future."))
    with tx(db):
        db.execute("UPDATE scope_steps SET finished_on = ?, finished_by = ? WHERE id = ?", (on, actor_id if on else None, sid))
        audit.log(db, actor_id, "step_finished" if on else "step_reopened", "project", pid, pid, code=st["code"],
                  finished_on=on)


# ---------- الاستيراد من Primavera P6 أو Microsoft Project أو Excel ----------

IMPORT_HEADERS = {
    "id": ("المعرف", "رقم النشاط", "id", "activity id", "unique id", "task id"),
    "name": ("اسم النشاط", "النشاط", "name", "activity name", "task name"),
    "link": ("البند", "كود البند", "القسم", "البند أو القسم", "item", "wbs", "boq code", "item code"),
    "start": ("البدء", "تاريخ البدء", "البدء المخطط", "start", "planned start", "start date"),
    "finish": ("الانتهاء", "تاريخ الانتهاء", "الانتهاء المخطط", "finish", "planned finish", "finish date", "end"),
    "preds": ("السابق", "الأنشطة السابقة", "predecessors", "predecessor"),
}


def _import_date(v):
    from datetime import datetime
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d-%b-%y", "%d-%b-%Y", "%d %b %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s.split(" ")[0] if fmt.count(" ") == 0 else s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def import_rows(db, pid, rows, actor_id) -> tuple[int, list[str]]:
    """يستورد الأنشطة كلها أو لا شيء: أي خطأ في أي سطر يُعرض ولا يُستورد شيء."""
    import re
    _ensure_open(db, pid)
    head_at, cols = None, {}
    for i, row in enumerate(rows[:10]):
        found = {}
        for j, cell in enumerate(row):
            h = re.sub(r"\s+", " ", str(cell or "").strip().lower())
            for key, names in IMPORT_HEADERS.items():
                if key not in found and h in names:
                    found[key] = j
        if {"name", "link", "start", "finish"} <= set(found):
            head_at, cols = i, found
            break
    if head_at is None:
        raise AuthError(_("The file needs the columns: activity name, item or section, start and finish."))
    items = {r["code"]: r for r in db.execute("SELECT id, code, wbs_id FROM boq_items WHERE project_id = ?", (pid,)).fetchall()}
    wbs = {r["code"]: r for r in db.execute("SELECT id, code FROM wbs_nodes WHERE project_id = ?", (pid,)).fetchall()}
    cell = lambda row, k: row[cols[k]] if k in cols and cols[k] < len(row) else None  # noqa: E731
    parsed, errors, ids = [], [], {}
    for n, row in enumerate(rows[head_at + 1:], start=1):
        name = str(cell(row, "name") or "").strip()
        if not name:
            continue
        link = str(cell(row, "link") or "").strip()
        start, finish = _import_date(cell(row, "start")), _import_date(cell(row, "finish"))
        line = _("Row {n}", n=n)
        if link in items:
            target = {"wbs_id": items[link]["wbs_id"], "boq_item_id": items[link]["id"]}
        elif link in wbs:
            target = {"wbs_id": wbs[link]["id"], "boq_item_id": None}
        else:
            errors.append(f"{line}: " + _("the item or section code {code} isn't in this project.", code=link or "—"))
            continue
        if not start or not finish or finish < start:
            errors.append(f"{line}: " + _("the start and finish dates are missing or reversed."))
            continue
        key = str(cell(row, "id") or "").strip() or str(n)
        ids[key] = len(parsed)
        refs = [x for x in re.split(r"[,;،\s]+", str(cell(row, "preds") or "")) if x]
        parsed.append({"name": name[:200], "start": start, "finish": finish, "refs": refs, "line": line, **target})
    for p in parsed:
        p["preds"] = []
        for ref in p["refs"]:
            m = re.match(r"^([A-Za-z0-9._-]*?\d+)(?:FS|SS|FF|SF)?([+-]\d+.*)?$", ref)
            k = m.group(1) if m else ref
            if k not in ids:
                errors.append(f"{p['line']}: " + _("the predecessor {ref} isn't in the file.", ref=ref))
            else:
                p["preds"].append(ids[k])
    graph = {i: p["preds"] for i, p in enumerate(parsed)}
    if not errors and _cycle(graph):
        errors.append(_("These predecessors make a loop: an activity would wait for itself."))
    if errors or not parsed:
        return 0, errors or [_("No activities found in the file.")]
    with tx(db):
        made = []
        for p in parsed:
            code = db.execute("SELECT code FROM wbs_nodes WHERE id = ?", (p["wbs_id"],)).fetchone()["code"]
            code = f"{code}-A{next_counter(db, 'act-%d' % p['wbs_id']) * 10:03d}"
            made.append(db.execute("INSERT INTO activities(project_id, code, name, wbs_id, boq_item_id, planned_start, planned_finish, "
                                   "created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?) RETURNING id",
                                   (pid, code, p["name"], p["wbs_id"], p["boq_item_id"], p["start"], p["finish"], utcnow(),
                                    actor_id)).fetchone()[0])
        for i, p in enumerate(parsed):
            for j in sorted(set(p["preds"])):
                db.execute("INSERT INTO activity_links(activity_id, predecessor_id) VALUES (?, ?)", (made[i], made[j]))
        _reset_review(db, pid)
        audit.log(db, actor_id, "schedule_imported", "project", pid, pid, count=len(made))
    return len(made), []


# ---------- الحسابات ----------

def item_progress(db, pid, until=None) -> dict[int, int]:
    """نسبة إنجاز كل بند من خطواته المنتهية (حتى تاريخ معيّن إن طُلب)."""
    sql = "SELECT boq_item_id, CAST(SUM(weight_bp) AS BIGINT) FROM scope_steps WHERE project_id = ? AND finished_on IS NOT NULL"
    args = [pid]
    if until:
        sql += " AND finished_on <= ?"
        args.append(until.isoformat() if isinstance(until, date) else until)
    return {r[0]: r[1] for r in db.execute(sql + " GROUP BY boq_item_id", args).fetchall()}


def _subtree(db, pid):
    """لكل قسم: البنود تحته (شاملة الأقسام الفرعية)."""
    nodes = db.execute("SELECT id, code FROM wbs_nodes WHERE project_id = ?", (pid,)).fetchall()
    items = db.execute("SELECT id, wbs_id, amount FROM boq_items WHERE project_id = ?", (pid,)).fetchall()
    code = {n["id"]: n["code"] for n in nodes}
    return {n["id"]: [i for i in items if code[i["wbs_id"]] == n["code"] or code[i["wbs_id"]].startswith(n["code"] + ".")]
            for n in nodes}, items


def compute(db, pid, now=None) -> list[dict]:
    """كل نشاط بمدته وتكلفته المخططة وإنجازه وتواريخه المتوقعة وانحرافه بالأيام."""
    now = now or today()
    acts, graph = activities(db, pid), links(db, pid)
    under, items = _subtree(db, pid)
    prog = item_progress(db, pid)
    direct = {}
    for a in acts:
        if a["boq_item_id"]:
            direct.setdefault(a["boq_item_id"], []).append(a)
    rows = {}
    for a in acts:
        ps, pf = _d(a["planned_start"]), _d(a["planned_finish"])
        rows[a["id"]] = {"a": a, "ps": ps, "pf": pf, "dur": (pf - ps).days + 1, "preds": graph.get(a["id"], [])}
    # التكلفة المخططة: البند يوزَّع على أنشطته بالمدة، والقسم يحمل بنوده التي ليس لها نشاط مباشر
    for iid, group in direct.items():
        amount = next(i["amount"] for i in items if i["id"] == iid)
        total = sum(rows[a["id"]]["dur"] for a in group)
        for a in group:
            rows[a["id"]]["cost"] = amount * rows[a["id"]]["dur"] // total
    section_acts = {}
    for a in acts:
        if not a["boq_item_id"]:
            section_acts.setdefault(a["wbs_id"], []).append(a)
    for wid, group in section_acts.items():
        free = [i for i in under.get(wid, []) if i["id"] not in direct]
        amount = sum(i["amount"] for i in free)
        total = sum(rows[a["id"]]["dur"] for a in group)
        for a in group:
            r = rows[a["id"]]
            r["cost"] = amount * r["dur"] // total if total else 0
            weight = sum(i["amount"] for i in free)
            r["progress"] = sum(i["amount"] * prog.get(i["id"], 0) for i in free) // weight if weight else 0
    for r in rows.values():
        r.setdefault("cost", 0)
        if r["a"]["boq_item_id"]:
            r["progress"] = prog.get(r["a"]["boq_item_id"], 0)
    # التمرير الأمامي: المتوقع من الفعلي ومن تأخر الأنشطة السابقة
    done = {}

    def forecast(aid):
        if aid in done:
            return done[aid]
        r = rows[aid]
        a = r["a"]
        if a["actual_finish"]:
            fs, ff = _d(a["actual_start"]), _d(a["actual_finish"])
        elif a["actual_start"]:
            fs = _d(a["actual_start"])
            ff = max(fs + timedelta(days=r["dur"] - 1), now)
        else:
            fs = max([r["ps"], now] + [forecast(p)[1] + timedelta(days=1) for p in r["preds"] if p in rows])
            ff = fs + timedelta(days=r["dur"] - 1)
        done[aid] = (fs, ff)
        return fs, ff
    out = []
    for aid, r in rows.items():
        fs, ff = forecast(aid)
        a = r["a"]
        status = ("finished" if a["actual_finish"] else "started" if a["actual_start"] else
                  ("late" if r["ps"] < now else "not_started"))
        out.append({**r, "fs": fs, "ff": ff, "variance": (ff - r["pf"]).days, "status": status,
                    "actual_dur": ((_d(a["actual_finish"]) or now) - _d(a["actual_start"])).days + 1 if a["actual_start"] else None,
                    "preds_late": [p for p in r["preds"] if p in rows and rows[p]["pf"] >= r["ps"]]})
    return out


STATUS = {"not_started": "Not started", "late": "Should have started", "started": "In progress", "finished": "Finished"}


def overall(db, pid, rows, now=None) -> dict:
    total = db.execute("SELECT CAST(COALESCE(SUM(amount), 0) AS BIGINT) FROM boq_items WHERE project_id = ?",
                       (pid,)).fetchone()[0]
    prog = item_progress(db, pid)
    amounts = db.execute("SELECT id, amount FROM boq_items WHERE project_id = ?", (pid,)).fetchall()
    earned = sum(i["amount"] * prog.get(i["id"], 0) // FULL for i in amounts)
    planned = planned_value(rows, now or today())
    return {"total": total, "earned": earned, "earned_bp": earned * FULL // total if total else 0,
            "planned": planned, "planned_bp": planned * FULL // total if total else 0,
            "start": min((r["ps"] for r in rows), default=None), "finish": max((r["pf"] for r in rows), default=None),
            "forecast": max((r["ff"] for r in rows), default=None)}


def planned_value(rows, at: date) -> int:
    """القيمة المخططة حتى تاريخ: تكلفة كل نشاط موزعة بالتساوي على أيامه."""
    v = 0
    for r in rows:
        if at >= r["pf"]:
            v += r["cost"]
        elif at >= r["ps"]:
            v += r["cost"] * ((at - r["ps"]).days + 1) // r["dur"]
    return v


def checks(db, pid, rows) -> list[tuple[bool, str, bool]]:
    """(ناجح، النص، يمنع الاعتماد)."""
    under, items = _subtree(db, pid)
    covered = set()
    for r in rows:
        a = r["a"]
        covered |= {a["boq_item_id"]} if a["boq_item_id"] else {i["id"] for i in under.get(a["wbs_id"], [])}
    missing = [i for i in items if i["id"] not in covered]
    early = [r for r in rows if r["preds_late"]]
    out = [(bool(rows), _("The schedule has activities"), True),
           (not missing, _("Every BOQ item has an activity, directly or through its section ({n} without)", n=len(missing)), True),
           (not early, _("No activity starts before its predecessor finishes ({n} do)", n=len(early)), False)]
    c = contract_of(db, pid)
    if c is not None and rows:
        end = _d(summary(db, c)["current_end"])
        out.append((max(r["pf"] for r in rows) <= end, _("The planned finish is within the contract handover date ({d})",
                                                          d=end.isoformat()), False))
        share = sum(m["share_bp"] for m in milestones_raw(db, c["id"]))
        out.append((share == FULL, _("The contract payment schedule adds up to 100% (now {pct})", pct=fmt_pct(share)), False))
    return out


def review(db, pid, actor_id):
    st = state(db, pid)
    if st["schedule_approved_at"]:
        raise AuthError(_("The schedule is already approved."))
    if st["schedule_reviewed_at"]:
        raise AuthError(_("The schedule is already reviewed."))
    if not all(ok for ok, _t, blocking in checks(db, pid, compute(db, pid)) if blocking):
        raise AuthError(_("The schedule is not complete yet."))
    with tx(db):
        db.execute("UPDATE projects SET schedule_reviewed_at = ?, schedule_reviewed_by = ? WHERE id = ?", (utcnow(), actor_id, pid))
        audit.log(db, actor_id, "schedule_reviewed", "project", pid, pid)


def approve(db, pid, actor_id):
    st = state(db, pid)
    if st["schedule_approved_at"]:
        raise AuthError(_("The schedule is already approved."))
    if not st["schedule_reviewed_at"]:
        raise AuthError(_("The cost control engineer reviews the schedule before the Director approves it."))
    if st["schedule_reviewed_by"] == actor_id:
        raise AuthError(_("Whoever reviews the schedule can't approve it."))
    with tx(db):
        db.execute("UPDATE projects SET schedule_approved_at = ?, schedule_approved_by = ? WHERE id = ?", (utcnow(), actor_id, pid))
        audit.log(db, actor_id, "schedule_approved", "project", pid, pid)


def reopen(db, pid, reason, actor_id):
    """فتح الجدول المعتمد للتعديل: بسبب مكتوب، ومن المدير التنفيذي فقط (مبدأ الحوكمة)."""
    if not state(db, pid)["schedule_approved_at"]:
        raise AuthError(_("The schedule is not approved."))
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise AuthError(_("Write the reason for reopening."))
    with tx(db):
        db.execute("UPDATE projects SET schedule_approved_at = NULL, schedule_approved_by = NULL, schedule_reviewed_at = NULL, "
                   "schedule_reviewed_by = NULL WHERE id = ?", (pid,))
        audit.log(db, actor_id, "schedule_reopened", "project", pid, pid, reason=reason)


# ---------- الرسوم: منحنى التقدم والتدفق النقدي ----------

def periods(start: date, end: date) -> list[date]:
    """نهايات الفترات: أسبوعية للمشاريع القصيرة، وشهرية لما زاد عن ستة أشهر."""
    if (end - start).days <= 183:
        out, d = [], start + timedelta(days=6)
        while d < end + timedelta(days=7):
            out.append(d)
            d += timedelta(days=7)
        return out
    out, y, m = [], start.year, start.month
    while date(y, m, 1) <= end:
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        out.append(date(ny, nm, 1) - timedelta(days=1))
        y, m = ny, nm
    return out


def s_curve(db, pid, rows, now=None) -> list[dict]:
    now = now or today()
    if not rows:
        return []
    start = min(r["ps"] for r in rows)
    end = max(max(r["pf"] for r in rows), max(r["ff"] for r in rows))
    total = db.execute("SELECT CAST(COALESCE(SUM(amount), 0) AS BIGINT) FROM boq_items WHERE project_id = ?",
                       (pid,)).fetchone()[0] or 1
    amounts = {r[0]: r[1] for r in db.execute("SELECT id, amount FROM boq_items WHERE project_id = ?", (pid,)).fetchall()}
    out, last = [], start - timedelta(days=1)
    for t in periods(start, end):
        point = {"date": t, "planned": planned_value(rows, t) * FULL // total, "earned": None}
        if last < now:  # الفترة بدأت: الفعلي حتى نهايتها أو حتى اليوم
            prog = item_progress(db, pid, min(t, now))
            point["earned"] = sum(amounts[i] * bp // FULL for i, bp in prog.items() if i in amounts) * FULL // total
        out.append(point)
        last = t
    return out


def cash_flow(db, pid, rows, ms) -> list[dict]:
    """لكل فترة: الدفعات المتوقعة من المالك، والتكلفة المخططة للأعمال."""
    if not rows:
        return []
    start = min(r["ps"] for r in rows)
    end = max([max(r["ff"] for r in rows)] + [m["expected"] for m in ms])
    out, prev, last = [], 0, start - timedelta(days=1)
    for t in periods(start, end):
        pv = planned_value(rows, t)
        inflow = sum(m["value"] for m in ms if last < m["expected"] <= t)
        out.append({"date": t, "cost": pv - prev, "inflow": inflow})
        prev, last = pv, t
    return out


# ---------- جدول الدفعات التعاقدية ----------

def milestones_raw(db, cid):
    return db.execute("SELECT * FROM payment_milestones WHERE contract_id = ? ORDER BY seq", (cid,)).fetchall()


def milestones(db, pid, rows=None) -> list[dict]:
    c = contract_of(db, pid)
    if c is None:
        return []
    rows = rows if rows is not None else compute(db, pid)
    by_id = {r["a"]["id"]: r for r in rows}
    out = []
    for m in milestones_raw(db, c["id"]):
        r = by_id.get(m["activity_id"])
        due = r and r["progress"] >= m["required_progress_bp"]
        out.append({"m": m, "act": r["a"] if r else None, "value": c["value_ex_vat"] * m["share_bp"] // FULL,
                    "planned": r["pf"] if r else None, "expected": r["ff"] if r else None, "due": bool(due),
                    "delay": (r["ff"] - r["pf"]).days if r else 0})
    return out


def add_milestone(db, pid, form, actor_id) -> str:
    _ensure_open(db, pid)
    c = contract_of(db, pid)
    if c is None:
        raise AuthError(_("Record the main contract first."))
    desc = (form.get("description") or "").strip()
    if len(desc) < 3:
        raise AuthError(_("Write the payment description."))
    raw = str(form.get("activity_id") or "")
    act = db.execute("SELECT id FROM activities WHERE id = ? AND project_id = ?", (int(raw), pid)).fetchone() if raw.isdigit() else None
    if act is None:
        raise AuthError(_("Choose the linked activity."))
    share = parse_pct(form.get("share_pct"), _("the payment share of the contract value"), required=True)
    need = parse_pct(form.get("required_pct") or "100", _("the progress required for the payment"), required=True)
    if share < 1 or need < 1:
        raise AuthError(_("{what} must be a percentage between 0 and 100.", what=_("the payment share of the contract value")))
    taken = sum(m["share_bp"] for m in milestones_raw(db, c["id"]))
    if taken + share > FULL:
        raise AuthError(_("The payments would exceed 100% of the contract value. The others already take {pct}.",
                          pct=fmt_pct(taken)))
    counter = "pay-%d" % c["id"]
    with tx(db):
        n = next_counter(db, counter)
        seq = db.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM payment_milestones WHERE contract_id = ?", (c["id"],)).fetchone()[0]
        code = f"{c['code']}-PAY-{n:02d}"
        db.execute("INSERT INTO payment_milestones(contract_id, code, seq, description, activity_id, required_progress_bp, share_bp, "
                   "notes, created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (c["id"], code, seq, desc, act["id"], need, share, (form.get("notes") or "").strip() or None, utcnow(), actor_id))
        audit.log(db, actor_id, "payment_added", "project", pid, pid, code=code, share_bp=share)
    return code


def delete_milestone(db, pid, mid, actor_id):
    _ensure_open(db, pid)
    c = contract_of(db, pid)
    m = db.execute("SELECT * FROM payment_milestones WHERE id = ? AND contract_id = ?", (mid, c["id"] if c else 0)).fetchone()
    if m is None:
        raise AuthError(_("This payment doesn't exist."))
    with tx(db):
        db.execute("DELETE FROM payment_milestones WHERE id = ?", (mid,))
        audit.log(db, actor_id, "payment_removed", "project", pid, pid, code=m["code"])
