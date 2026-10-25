"""الموارد (الدستور، البند 3.6): سجلات الأفراد والأطقم والمعدات، والهيكل التنظيمي للمشروع، والتخصيص وقواعد تحققه."""
import math
from datetime import date, timedelta

from . import audit
from .boq import fmt_qty, is_locked, parse_qty
from .db import next_counter, tx, utcnow
from .errors import AuthError
from .i18n import _
from .projects import parse_money
from .registers import EMAIL_RE, catalog

PERSON_STATUS = {"active": "On duty", "leave": "On leave", "terminated": "Left the company"}
EQUIPMENT_STATUS = {"working": "Working", "maintenance": "In maintenance", "out": "Out of service"}
OWNERSHIP = {"owned": "Owned", "rented": "Rented"}
RESOURCE_KINDS = {"person": "Person", "crew": "Crew", "equipment": "Equipment item", "subcontractor": "Subcontractor"}
ALLOCATION_STATUS = {"planned": "Planned", "approved": "Approved", "active": "In progress", "done": "Finished",
                     "cancelled": "Cancelled"}
LIVE = ("planned", "approved", "active")          # تخصيصات تحجز المورد
OFF_DAYS = (4, 5, 3, 2, 1, 0)                     # الجمعة ثم السبت ثم الخميس… (weekday: الاثنين = 0)


def _date(v, what, required=True):
    s = (str(v) if v is not None else "").strip()
    if not s:
        if required:
            raise AuthError(_("Enter {what}.", what=what))
        return None
    try:
        return date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        raise AuthError(_("The date format is not valid."))


def _active_codes(db, kind):
    return {r["code"] for r in catalog(db, kind, active_only=True)}


# ---------- الأفراد ----------

def people(db, active_only=False):
    sql = "SELECT * FROM people" + (" WHERE status != 'terminated'" if active_only else "")
    return db.execute(sql + " ORDER BY code").fetchall()


def _clean_person(db, form):
    d = {
        "full_name": (form.get("full_name") or "").strip(),
        "profession_code": form.get("profession_code") or "",
        "job_title_code": form.get("job_title_code") or "",
        "id_no": (form.get("id_no") or "").strip(),
        "nationality": (form.get("nationality") or "").strip() or None,
        "phone": (form.get("phone") or "").strip(),
        "email": (form.get("email") or "").strip().lower() or None,
        "daily_cost": parse_money(form.get("daily_cost")),
        "status": form.get("status") or "active",
    }
    if len(d["full_name"]) < 3:
        raise AuthError(_("Enter the person's full name."))
    if d["profession_code"] not in _active_codes(db, "profession"):
        raise AuthError(_("Choose the profession."))
    if d["job_title_code"] not in _active_codes(db, "job_title"):
        raise AuthError(_("Choose the job title."))
    if len(d["id_no"]) < 5:
        raise AuthError(_("Enter the ID or residence number."))
    if len(d["phone"]) < 7:
        raise AuthError(_("Enter the phone number."))
    if d["email"] and not EMAIL_RE.match(d["email"]):
        raise AuthError(_("Enter a valid email address."))
    if d["daily_cost"] is None:
        raise AuthError(_("Enter the daily cost."))
    if d["status"] not in PERSON_STATUS:
        raise AuthError(_("Choose the status."))
    uid = str(form.get("user_id") or "")
    d["user_id"] = int(uid) if uid.isdigit() else None
    if d["user_id"] and not db.execute("SELECT 1 FROM users WHERE id = ?", (d["user_id"],)).fetchone():
        raise AuthError(_("The account doesn't exist or is disabled."))
    return d


def save_person(db, form, actor_id, person_id=None) -> int:
    d = _clean_person(db, form)
    if d["user_id"] and db.execute("SELECT 1 FROM people WHERE user_id = ? AND id != ?",
                                   (d["user_id"], person_id or 0)).fetchone():
        raise AuthError(_("This account is already linked to another person."))
    with tx(db):
        if person_id is None:
            code = f"EMP-{d['profession_code']}-{next_counter(db, 'emp-' + d['profession_code']):04d}"
            pid = db.execute(f"INSERT INTO people(code, {', '.join(d)}, created_at, created_by) "
                             f"VALUES (?, {', '.join('?' for _ in d)}, ?, ?) RETURNING id",
                             (code, *d.values(), utcnow(), actor_id)).fetchone()[0]
            audit.log(db, actor_id, "person_created", "person", pid, code=code, full_name=d["full_name"])
            return pid
        cur = db.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
        if cur is None:
            raise AuthError(_("This person doesn't exist."))
        changes = {k: v for k, v in d.items() if cur[k] != v}
        if changes:
            db.execute(f"UPDATE people SET {', '.join(f'{k} = ?' for k in changes)} WHERE id = ?", (*changes.values(), person_id))
            audit.log(db, actor_id, "person_updated", "person", person_id, code=cur["code"],
                      **{k: {"from": cur[k], "to": v} for k, v in changes.items()})
        return person_id


# ---------- الأطقم ----------

def crews(db, active_only=False):
    sql = ("SELECT c.*, p.full_name AS leader_name, (SELECT COUNT(*) FROM crew_members m WHERE m.crew_id = c.id) AS n_members "
           "FROM crews c JOIN people p ON p.id = c.leader_id") + (" WHERE c.active = TRUE" if active_only else "")
    return db.execute(sql + " ORDER BY c.code").fetchall()


def crew_members(db, crew_id):
    return db.execute("SELECT p.* FROM crew_members m JOIN people p ON p.id = m.person_id WHERE m.crew_id = ? ORDER BY p.code",
                      (crew_id,)).fetchall()


def crew_daily_cost(db, crew) -> int:
    if crew["daily_cost"] is not None:
        return crew["daily_cost"]
    return sum(p["daily_cost"] for p in crew_members(db, crew["id"]))


def save_crew(db, form, actor_id, crew_id=None) -> int:
    name = (form.get("name") or "").strip()
    spec = form.get("specialty_code") or ""
    if len(name) < 3:
        raise AuthError(_("Enter the crew name."))
    if spec not in _active_codes(db, "specialty"):
        raise AuthError(_("Choose the specialty."))
    getlist = form.getlist if hasattr(form, "getlist") else (lambda k: form.get(k) or [])
    valid = {r["id"] for r in people(db, active_only=True)}
    members = sorted({int(x) for x in getlist("members") if str(x).isdigit() and int(x) in valid})
    leader = str(form.get("leader_id") or "")
    if not leader.isdigit() or int(leader) not in valid:
        raise AuthError(_("Choose the crew leader."))
    leader = int(leader)
    if leader not in members:
        members.append(leader)
    raw_cost = (form.get("daily_cost") or "").strip()
    daily = parse_money(raw_cost) if raw_cost else None
    active = bool(form.get("active")) if crew_id else True
    with tx(db):
        if crew_id is None:
            code = f"CRW-{spec}-{next_counter(db, 'crw-' + spec):03d}"
            crew_id = db.execute("INSERT INTO crews(code, name, specialty_code, leader_id, daily_cost, created_at, created_by) "
                                 "VALUES (?,?,?,?,?,?,?) RETURNING id",
                                 (code, name, spec, leader, daily, utcnow(), actor_id)).fetchone()[0]
            audit.log(db, actor_id, "crew_created", "crew", crew_id, code=code, name=name)
        else:
            cur = db.execute("SELECT * FROM crews WHERE id = ?", (crew_id,)).fetchone()
            if cur is None:
                raise AuthError(_("This crew doesn't exist."))
            db.execute("UPDATE crews SET name = ?, specialty_code = ?, leader_id = ?, daily_cost = ?, active = ? WHERE id = ?",
                       (name, spec, leader, daily, active, crew_id))
            db.execute("DELETE FROM crew_members WHERE crew_id = ?", (crew_id,))
            audit.log(db, actor_id, "crew_updated", "crew", crew_id, code=cur["code"], name=name, count=len(members))
        for m in members:
            db.execute("INSERT INTO crew_members(crew_id, person_id) VALUES (?, ?)", (crew_id, m))
    return crew_id


# ---------- المعدات ----------

def equipment(db, usable_only=False):
    sql = "SELECT * FROM equipment" + (" WHERE status != 'out'" if usable_only else "")
    return db.execute(sql + " ORDER BY code").fetchall()


def save_equipment(db, form, actor_id, eq_id=None) -> int:
    d = {
        "catalog_code": form.get("catalog_code") or "",
        "label": (form.get("label") or "").strip() or None,
        "make_model": (form.get("make_model") or "").strip() or None,
        "plate_serial": (form.get("plate_serial") or "").strip(),
        "ownership": form.get("ownership") or "",
        "lessor": (form.get("lessor") or "").strip() or None,
        "daily_cost": parse_money(form.get("daily_cost")),
        "status": form.get("status") or "working",
    }
    if d["catalog_code"] not in _active_codes(db, "equipment"):
        raise AuthError(_("Choose the equipment from the equipment catalog."))
    if len(d["plate_serial"]) < 2:
        raise AuthError(_("Enter the plate or serial number."))
    if d["ownership"] not in OWNERSHIP:
        raise AuthError(_("Choose owned or rented."))
    if d["ownership"] == "rented" and not d["lessor"]:
        raise AuthError(_("Enter the lessor of a rented equipment."))
    if d["daily_cost"] is None:
        raise AuthError(_("Enter the daily cost."))
    if d["status"] not in EQUIPMENT_STATUS:
        raise AuthError(_("Choose the status."))
    with tx(db):
        if eq_id is None:
            code = f"EQP-{d['catalog_code']}-{next_counter(db, 'eqp-' + d['catalog_code']):04d}"
            eq_id = db.execute(f"INSERT INTO equipment(code, {', '.join(d)}, created_at, created_by) "
                               f"VALUES (?, {', '.join('?' for _ in d)}, ?, ?) RETURNING id",
                               (code, *d.values(), utcnow(), actor_id)).fetchone()[0]
            audit.log(db, actor_id, "equipment_created", "equipment", eq_id, code=code)
        else:
            cur = db.execute("SELECT * FROM equipment WHERE id = ?", (eq_id,)).fetchone()
            if cur is None:
                raise AuthError(_("This equipment doesn't exist."))
            if d["catalog_code"] != cur["catalog_code"]:
                raise AuthError(_("Codes are permanent and can't be changed."))
            changes = {k: v for k, v in d.items() if cur[k] != v}
            if changes:
                db.execute(f"UPDATE equipment SET {', '.join(f'{k} = ?' for k in changes)} WHERE id = ?",
                           (*changes.values(), eq_id))
                audit.log(db, actor_id, "equipment_updated", "equipment", eq_id, code=cur["code"],
                          **{k: {"from": cur[k], "to": v} for k, v in changes.items()})
    return eq_id


# ---------- الهيكل التنظيمي ----------

def positions(db, pid):
    return db.execute("SELECT o.*, p.full_name, p.code AS person_code FROM project_positions o JOIN people p ON p.id = o.person_id "
                      "WHERE o.project_id = ? ORDER BY o.id", (pid,)).fetchall()


def org_tree(db, pid):
    """الوظائف الحالية مرتبة شجرةً: [(الوظيفة، [الأبناء…])]."""
    rows = [r for r in positions(db, pid) if not r["to_date"]]
    kids = {}
    for r in rows:
        kids.setdefault(r["reports_to"], []).append(r)
    ids = {r["id"] for r in rows}

    def build(parent):
        return [(r, build(r["id"])) for r in kids.get(parent, [])]
    roots = [r for r in rows if r["reports_to"] is None or r["reports_to"] not in ids]
    return [(r, build(r["id"])) for r in roots]


def add_position(db, pid, form, actor_id) -> int:
    p = db.execute("SELECT code FROM projects WHERE id = ?", (pid,)).fetchone()
    title = form.get("job_title_code") or ""
    if title not in _active_codes(db, "job_title"):
        raise AuthError(_("Choose the job title."))
    person = str(form.get("person_id") or "")
    if not person.isdigit() or int(person) not in {r["id"] for r in people(db, active_only=True)}:
        raise AuthError(_("Choose who holds the position."))
    boss = str(form.get("reports_to") or "")
    boss_id = int(boss) if boss.isdigit() else None
    if boss_id and not db.execute("SELECT 1 FROM project_positions WHERE id = ? AND project_id = ? AND to_date IS NULL",
                                  (boss_id, pid)).fetchone():
        raise AuthError(_("The direct manager must be a current position in this project."))
    start = _date(form.get("from_date"), _("the start date"))
    duties = (form.get("duties") or "").strip() or None
    counter = "org-%d" % pid
    with tx(db):
        code = f"{p['code']}-ORG-{next_counter(db, counter):02d}"
        oid = db.execute("INSERT INTO project_positions(project_id, code, job_title_code, reports_to, person_id, from_date, "
                         "duties, created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?) RETURNING id",
                         (pid, code, title, boss_id, int(person), start, duties, utcnow(), actor_id)).fetchone()[0]
        audit.log(db, actor_id, "position_added", "project", pid, pid, code=code)
    return oid


def end_position(db, pid, oid, end, actor_id):
    row = db.execute("SELECT * FROM project_positions WHERE id = ? AND project_id = ?", (oid, pid)).fetchone()
    if row is None or row["to_date"]:
        raise AuthError(_("This position doesn't exist or has already ended."))
    end = _date(end, _("the end date"))
    if end < str(row["from_date"])[:10]:
        raise AuthError(_("The end date must be after the start date."))
    if db.execute("SELECT 1 FROM project_positions WHERE reports_to = ? AND to_date IS NULL", (oid,)).fetchone():
        raise AuthError(_("Other positions report to this one. Move them first, or add the replacement before ending it."))
    with tx(db):
        db.execute("UPDATE project_positions SET to_date = ? WHERE id = ?", (end, oid))
        audit.log(db, actor_id, "position_ended", "project", pid, pid, code=row["code"])


# ---------- التخصيص ----------

def working_days(start: str, end: str, per_week: int) -> int:
    off = set(OFF_DAYS[:7 - per_week])
    d, last, n = date.fromisoformat(start), date.fromisoformat(end), 0
    while d <= last:
        if d.weekday() not in off:
            n += 1
        d += timedelta(days=1)
    return n


def _resource(db, kind, rid):
    table = {"person": "people", "crew": "crews", "equipment": "equipment", "subcontractor": "entities"}[kind]
    return db.execute(f"SELECT * FROM {table} WHERE id = ?", (rid,)).fetchone()


def daily_cost_of(db, kind, res) -> int:
    if kind == "crew":
        return crew_daily_cost(db, res)
    return res["daily_cost"] if kind in ("person", "equipment") else 0


def _overlap_peak(db, kind, rid, start, end, skip_id=None) -> int:
    """أعلى مجموع لنسب التفرغ في أي يوم من الفترة، في كل المشاريع (بأجزاء من عشرة آلاف)."""
    col = {"person": "person_id", "crew": "crew_id", "equipment": "equipment_id"}[kind]
    rows = db.execute(f"SELECT from_date, to_date, allocation_bp FROM allocations WHERE {col} = ? AND id != ? "
                      f"AND status IN ('planned','approved','active') AND from_date <= ? AND to_date >= ?",
                      (rid, skip_id or 0, end, start)).fetchall()
    if not rows:
        return 0
    peak, d, last = 0, date.fromisoformat(start), date.fromisoformat(end)
    spans = [(date.fromisoformat(str(r[0])[:10]), date.fromisoformat(str(r[1])[:10]), r[2]) for r in rows]
    while d <= last:
        peak = max(peak, sum(bp for a, b, bp in spans if a <= d <= b))
        d += timedelta(days=1)
    return peak


def evaluate(db, a: dict) -> dict:
    """الحسابات والتنبيهات لتخصيص (مخزن أو قيد الإدخال)."""
    item = db.execute("SELECT * FROM boq_items WHERE id = ?", (a["boq_item_id"],)).fetchone()
    days = working_days(str(a["from_date"])[:10], str(a["to_date"])[:10], a["days_per_week"])
    needed = math.ceil(a["qty_milli"] / a["productivity_milli"])
    if a["resource_kind"] == "subcontractor":
        daily, cost = None, a["qty_milli"] * (a["unit_rate"] or 0) // 1000
    else:
        res = _resource(db, a["resource_kind"], a[{"person": "person_id", "crew": "crew_id", "equipment": "equipment_id"}[a["resource_kind"]]])
        daily = daily_cost_of(db, a["resource_kind"], res)
        cost = days * daily * a["allocation_bp"] // 10000
    unit_cost = cost * 1000 // a["qty_milli"]
    warnings = []
    if a["resource_kind"] == "equipment" and res["status"] == "maintenance" and dict(a).get("status", "planned") in LIVE:
        warnings.append(_("This equipment is in maintenance now."))
    if days < needed:
        warnings.append(_("The period has {d} working days, but the productivity rate needs {n}.", d=days, n=needed))
    if item is not None and unit_cost > item["unit_rate"]:
        warnings.append(_("The cost per unit is higher than the item's contract rate."))
    step_id = dict(a).get("step_id")
    step = db.execute("SELECT * FROM scope_steps WHERE id = ?", (step_id,)).fetchone() if step_id else None
    if step is not None and step["party"] == "subcontractor" and step["entity_id"] != a["entity_id"]:
        warnings.append(_("The scope step is assigned to another subcontractor."))
    if step is not None and a["resource_kind"] == "crew" and step["crew_id"] != a["crew_id"]:
        warnings.append(_("The scope step is assigned to another crew."))
    return {"days": days, "needed": needed, "daily": daily, "cost": cost, "unit_cost": unit_cost, "warnings": warnings,
            "item": item}


def _step_for(db, item_id, kind, raw):
    """خطوة نطاق العمل إلزامية متى كانت للبند خطوات، ونوع المخصَّص يطابق جهة تنفيذها (القاعدة 6)."""
    rows = db.execute("SELECT * FROM scope_steps WHERE boq_item_id = ?", (item_id,)).fetchall()
    if not rows:
        return None
    raw = str(raw or "")
    step = next((r for r in rows if raw.isdigit() and r["id"] == int(raw)), None)
    if step is None:
        raise AuthError(_("Choose the scope step of this item."))
    if step["party"] == "subcontractor" and kind != "subcontractor":
        raise AuthError(_("This step is assigned to a subcontractor, so only a subcontractor can be allocated to it."))
    if step["party"] == "crew" and kind == "subcontractor":
        raise AuthError(_("This step is executed by company crews, so a subcontractor can't be allocated to it."))
    return step


def add_allocation(db, pid, form, actor_id) -> tuple[int, str, list]:
    p = db.execute("SELECT code FROM projects WHERE id = ?", (pid,)).fetchone()
    kind = form.get("resource_kind") or ""
    if kind not in RESOURCE_KINDS:
        raise AuthError(_("Choose what is allocated: a person, a crew, equipment or a subcontractor."))
    raw = str(form.get(f"resource_id_{kind}") or form.get("resource_id") or "")
    res = _resource(db, kind, int(raw)) if raw.isdigit() else None
    if res is None:
        raise AuthError(_("Choose the person, crew, equipment or subcontractor."))
    if kind == "person" and res["status"] == "terminated":
        raise AuthError(_("This person has left the company and can't be allocated."))
    if kind == "equipment" and res["status"] == "out":
        raise AuthError(_("This equipment is out of service and can't be allocated."))
    if kind == "crew" and not res["active"]:
        raise AuthError(_("This crew is stopped and can't be allocated."))
    if kind == "subcontractor" and (res["kind"] != "subcontractor" or res["approval_status"] != "approved" or not res["active"]):
        raise AuthError(_("Only an approved subcontractor can be allocated."))
    item_raw = str(form.get("boq_item_id") or "")
    item = db.execute("SELECT * FROM boq_items WHERE id = ? AND project_id = ?",
                      (int(item_raw), pid)).fetchone() if item_raw.isdigit() else None
    if item is None:
        raise AuthError(_("Choose the BOQ item."))
    step = _step_for(db, item["id"], kind, form.get("step_id"))
    current = {r["id"] for r in positions(db, pid) if not r["to_date"]}
    sup = str(form.get("supervisor_id") or "")
    if not sup.isdigit() or int(sup) not in current:
        raise AuthError(_("Choose who supervises the work, from the project positions."))
    position = None
    if kind == "person":
        pos = str(form.get("position_id") or "")
        if not pos.isdigit() or int(pos) not in current:
            raise AuthError(_("Choose the person's position in the project organization chart."))
        position = int(pos)
    start, end = _date(form.get("from_date"), _("the start date")), _date(form.get("to_date"), _("the end date"))
    if end < start:
        raise AuthError(_("The end date must be after the start date."))
    try:
        per_week = int(form.get("days_per_week") or 6)
        hours = int(form.get("hours_per_day") or 8)
    except ValueError:
        raise AuthError(_("Enter whole numbers for the working days and hours."))
    if not (1 <= per_week <= 7 and 1 <= hours <= 24):
        raise AuthError(_("Enter whole numbers for the working days and hours."))
    from .contracts import parse_pct
    bp = parse_pct(form.get("allocation_pct") or "100", _("the allocation percentage"), required=True)
    if bp < 1:
        raise AuthError(_("{what} must be a percentage between 0 and 100.", what=_("the allocation percentage")))
    qty = parse_qty(form.get("qty") or fmt_qty(item["qty_milli"]).replace(",", ""))
    productivity = parse_qty(form.get("productivity"))
    rate = None
    if kind == "subcontractor":
        rate = parse_money(form.get("unit_rate"))
        if rate is None:
            raise AuthError(_("Enter the subcontractor's estimated unit rate."))
    if kind in ("person", "crew", "equipment"):
        peak = _overlap_peak(db, kind, res["id"], start, end)
        if peak + bp > 10000:
            other = db.execute(
                "SELECT p.code FROM allocations a JOIN projects p ON p.id = a.project_id WHERE a.{0} = ? AND a.status IN "
                "('planned','approved','active') AND a.from_date <= ? AND a.to_date >= ? ORDER BY a.id LIMIT 1".format(
                    {"person": "person_id", "crew": "crew_id", "equipment": "equipment_id"}[kind]),
                (res["id"], end, start)).fetchone()
            raise AuthError(_("Conflict: this resource is already allocated {pct} in the same period (project {code}).",
                              pct=f"{peak / 100:g}%", code=other[0] if other else "—"))
    a = {"resource_kind": kind, "person_id": res["id"] if kind == "person" else None,
         "crew_id": res["id"] if kind == "crew" else None, "equipment_id": res["id"] if kind == "equipment" else None,
         "entity_id": res["id"] if kind == "subcontractor" else None, "position_id": position, "wbs_id": item["wbs_id"],
         "boq_item_id": item["id"], "supervisor_id": int(sup), "from_date": start, "to_date": end,
         "days_per_week": per_week, "hours_per_day": hours, "allocation_bp": bp, "qty_milli": qty,
         "productivity_milli": productivity, "unit_rate": rate, "notes": (form.get("notes") or "").strip() or None,
         "step_id": step["id"] if step else None}
    ev = evaluate(db, a)
    counter = "alc-%d" % pid
    with tx(db):
        code = f"{p['code']}-ALC-{next_counter(db, counter):04d}"
        aid = db.execute(f"INSERT INTO allocations(project_id, code, {', '.join(a)}, created_at, created_by) "
                         f"VALUES (?, ?, {', '.join('?' for _ in a)}, ?, ?) RETURNING id",
                         (pid, code, *a.values(), utcnow(), actor_id)).fetchone()[0]
        audit.log(db, actor_id, "allocation_added", "project", pid, pid, code=code, amount=ev["cost"])
    return aid, code, ev["warnings"]


def allocations(db, pid):
    return db.execute(
        "SELECT a.*, b.code AS item_code, b.description AS item_desc, b.unit AS item_unit, st.code AS step_code, "
        "st.name AS step_name, "
        "COALESCE(pe.full_name, c.name, e.label, en.name) AS res_name, COALESCE(pe.code, c.code, e.code, en.code) AS res_code, "
        "e.catalog_code AS eq_catalog FROM allocations a JOIN boq_items b ON b.id = a.boq_item_id "
        "LEFT JOIN people pe ON pe.id = a.person_id LEFT JOIN crews c ON c.id = a.crew_id "
        "LEFT JOIN equipment e ON e.id = a.equipment_id LEFT JOIN entities en ON en.id = a.entity_id "
        "LEFT JOIN scope_steps st ON st.id = a.step_id "
        "WHERE a.project_id = ? ORDER BY a.id", (pid,)).fetchall()


def approve_allocation(db, pid, aid, actor_id):
    a = db.execute("SELECT * FROM allocations WHERE id = ? AND project_id = ?", (aid, pid)).fetchone()
    if a is None or a["status"] != "planned":
        raise AuthError(_("Only a planned allocation can be approved."))
    if a["created_by"] == actor_id:
        raise AuthError(_("Whoever prepares an allocation can't approve it."))
    with tx(db):
        db.execute("UPDATE allocations SET status = 'approved', approved_at = ?, approved_by = ? WHERE id = ?",
                   (utcnow(), actor_id, aid))
        audit.log(db, actor_id, "allocation_approved", "project", pid, pid, code=a["code"])


def cancel_allocation(db, pid, aid, reason, actor_id, may_approve=False):
    """بعد اعتماد الميزانية يصبح التخصيص جزءًا من خط الأساس، فلا يلغيه إلا من يعتمد التغيير (المبدأ 8 في البند 3.6)."""
    a = db.execute("SELECT * FROM allocations WHERE id = ? AND project_id = ?", (aid, pid)).fetchone()
    if a is None or a["status"] not in LIVE:
        raise AuthError(_("This allocation can't be cancelled."))
    if is_locked(db, pid) and not may_approve:
        raise AuthError(_("After the budget approval, only the Director can cancel an allocation."))
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise AuthError(_("Write the reason for cancelling."))
    with tx(db):
        db.execute("UPDATE allocations SET status = 'cancelled', change_reason = ? WHERE id = ?", (reason, aid))
        audit.log(db, actor_id, "allocation_cancelled", "project", pid, pid, code=a["code"], reason=reason)


def weekly_demand(db, pid) -> list[dict]:
    """مخطط احتياج الموارد: عدد الأفراد والأطقم والمعدات المطلوب في كل أسبوع."""
    rows = [a for a in allocations(db, pid) if a["status"] in LIVE and a["resource_kind"] != "subcontractor"]
    if not rows:
        return []
    start = min(date.fromisoformat(str(a["from_date"])[:10]) for a in rows)
    end = max(date.fromisoformat(str(a["to_date"])[:10]) for a in rows)
    start -= timedelta(days=(start.weekday() + 2) % 7)  # بداية الأسبوع السبت
    weeks, d = [], start
    while d <= end and len(weeks) < 104:
        wk_end = d + timedelta(days=6)
        counts = {"person": 0, "crew": 0, "equipment": 0}
        for a in rows:
            if date.fromisoformat(str(a["from_date"])[:10]) <= wk_end and date.fromisoformat(str(a["to_date"])[:10]) >= d:
                counts[a["resource_kind"]] += 1
        weeks.append({"start": d.isoformat(), **counts, "total": sum(counts.values())})
        d += timedelta(days=7)
    return weeks
