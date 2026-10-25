"""السجلات المشتركة بين المشاريع (الدستور، المادة 2 والبند 3.9): الأدلة، وسجل الجهات وأشخاصها، وممثلو الجهات في كل مشروع."""
import re

from . import audit
from .db import next_counter, tx, utcnow
from .errors import AuthError
from .i18n import _, current_lang

CODE_RE = re.compile(r"^[A-Z]{3}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# الأدلة: المفتاح ← (الاسم، الوصف). الترجمة في i18n_ar.py
CATALOGS = {
    "unit": ("Units", "Units of measure for BOQ items and quantities."),
    "doc_type": ("Document types", "The kinds of project documents."),
    "profession": ("Professions", "The profession of each person in the people register."),
    "specialty": ("Specialties", "Work specialties of crews and subcontractors."),
    "job_title": ("Job titles", "Job titles for people and for positions in a project's organization chart."),
    "equipment_type": ("Equipment types", "The main classes of equipment."),
    "equipment": ("Equipment catalog", "Equipment names. Each name belongs to one equipment type."),
}
COST_UNITS = {"day": "Daily", "hour": "Hourly"}

# أنواع الجهات: المفتاح ← (الاسم، بادئة الكود)
ENTITY_KINDS = {
    "owner": ("Owner", "OWN"),
    "consultant": ("Consultant", "CNS"),
    "subcontractor": ("Subcontractor", "SUB"),
    "supplier": ("Supplier", "SUP"),
}
VENDORS = ("subcontractor", "supplier")   # جهات لها سجل تجاري واعتماد لدى الشركة
APPROVAL = {"approved": "Approved", "review": "Under evaluation", "suspended": "Suspended"}
ADDRESS_LABELS = {"main": "Head office", "branch": "Branch"}
MIN_REPRESENTATIVES = 2


def label(row) -> str:
    """اسم عنصر الدليل بلغة الواجهة."""
    return row["name_ar"] if current_lang() == "ar" else row["name_en"]


# ---------- الأدلة ----------

def catalog(db, kind, active_only=False):
    sql = "SELECT * FROM catalog_items WHERE kind = ?" + (" AND active = TRUE" if active_only else "")
    return db.execute(sql + " ORDER BY sort, code", (kind,)).fetchall()


def catalog_names(db, kind) -> dict:
    return {r["code"]: label(r) for r in catalog(db, kind)}


def _clean_catalog(db, kind, form, item_id=None):
    if kind not in CATALOGS:
        raise AuthError(_("Unknown list."))
    code = (form.get("code") or "").strip().upper()
    name_ar, name_en = (form.get("name_ar") or "").strip(), (form.get("name_en") or "").strip()
    if not CODE_RE.match(code):
        raise AuthError(_("The code is 3 English capital letters, e.g. EXC."))
    if not (2 <= len(name_ar) <= 80 and 2 <= len(name_en) <= 80):
        raise AuthError(_("Enter the name in Arabic and English (2 to 80 characters)."))
    if db.execute("SELECT 1 FROM catalog_items WHERE kind = ? AND code = ? AND id != ?",
                  (kind, code, item_id or 0)).fetchone():
        raise AuthError(_("Another entry in this list already uses this code."))
    data = {"code": code, "name_ar": name_ar, "name_en": name_en, "parent_code": None, "cost_unit": None}
    if kind == "equipment":
        parent = (form.get("parent_code") or "").strip()
        if parent not in {r["code"] for r in catalog(db, "equipment_type", active_only=True)}:
            raise AuthError(_("Choose the equipment type."))
        cost_unit = form.get("cost_unit") or ""
        if cost_unit not in COST_UNITS:
            raise AuthError(_("Choose the cost unit."))
        data.update(parent_code=parent, cost_unit=cost_unit)
    return data


def add_catalog_item(db, kind, form, actor_id) -> int:
    data = _clean_catalog(db, kind, form)
    sort = (db.execute("SELECT MAX(sort) FROM catalog_items WHERE kind = ?", (kind,)).fetchone()[0] or 0) + 10
    with tx(db):
        iid = db.execute(
            "INSERT INTO catalog_items(kind, code, name_ar, name_en, parent_code, cost_unit, sort) "
            "VALUES (?,?,?,?,?,?,?) RETURNING id",
            (kind, data["code"], data["name_ar"], data["name_en"], data["parent_code"], data["cost_unit"], sort)
        ).fetchone()[0]
        audit.log(db, actor_id, "catalog_item_added", "catalog", iid, list=kind, **{k: v for k, v in data.items() if v})
    return iid


def update_catalog_item(db, item_id, form, actor_id):
    cur = db.execute("SELECT * FROM catalog_items WHERE id = ?", (item_id,)).fetchone()
    if cur is None:
        raise AuthError(_("This entry doesn't exist."))
    data = _clean_catalog(db, cur["kind"], form, item_id)
    if data["code"] != cur["code"]:
        raise AuthError(_("Codes are permanent and can't be changed."))
    changes = {k: v for k, v in data.items() if cur[k] != v}
    if not changes:
        return
    with tx(db):
        db.execute(f"UPDATE catalog_items SET {', '.join(f'{k} = ?' for k in changes)} WHERE id = ?",
                   (*changes.values(), item_id))
        audit.log(db, actor_id, "catalog_item_updated", "catalog", item_id, list=cur["kind"],
                  **{k: {"from": cur[k], "to": v} for k, v in changes.items()})


def set_catalog_active(db, item_id, active: bool, actor_id):
    """العنصر لا يُحذف أبدًا لأنه قد يكون مستخدمًا؛ يُوقف فلا يظهر في الاختيارات الجديدة."""
    cur = db.execute("SELECT * FROM catalog_items WHERE id = ?", (item_id,)).fetchone()
    if cur is None:
        raise AuthError(_("This entry doesn't exist."))
    if bool(cur["active"]) == active:
        return
    with tx(db):
        db.execute("UPDATE catalog_items SET active = ? WHERE id = ?", (active, item_id))
        audit.log(db, actor_id, "catalog_item_updated", "catalog", item_id, list=cur["kind"], code=cur["code"],
                  active={"from": bool(cur["active"]), "to": active})


# ---------- الجهات ----------

def entity(db, eid):
    return db.execute("SELECT * FROM entities WHERE id = ?", (eid,)).fetchone()


def entities(db, kind=None, q="", active_only=False):
    sql = ("SELECT e.*, (SELECT COUNT(*) FROM entity_people p WHERE p.entity_id = e.id AND p.active = TRUE) AS n_people, "
           "(SELECT COUNT(*) FROM projects pr WHERE pr.owner_entity_id = e.id OR pr.consultant_entity_id = e.id) AS n_projects "
           "FROM entities e WHERE 1 = 1")
    args = []
    if kind:
        sql += " AND e.kind = ?"
        args.append(kind)
    if active_only:
        sql += " AND e.active = TRUE"
    if q:
        sql += " AND (LOWER(e.name) LIKE ? OR LOWER(COALESCE(e.name_en, '')) LIKE ? OR LOWER(e.code) LIKE ?)"
        args += [f"%{q.lower()}%"] * 3
    return db.execute(sql + " ORDER BY e.kind, e.name", args).fetchall()


def _clean_entity(db, form, kind):
    name = (form.get("name") or "").strip()
    email = (form.get("email") or "").strip().lower()
    if len(name) < 3:
        raise AuthError(_("Enter the entity name."))
    if not EMAIL_RE.match(email):
        raise AuthError(_("Enter a valid email address."))
    data = {
        "name": name,
        "name_en": (form.get("name_en") or "").strip() or None,
        "email": email,
        "phone": (form.get("phone") or "").strip() or None,
        "website": (form.get("website") or "").strip() or None,
        "cr_no": (form.get("cr_no") or "").strip() or None,
        "vat_no": (form.get("vat_no") or "").strip() or None,
        "classification": (form.get("classification") or "").strip() or None,
        "approval_status": None,
        "notes": (form.get("notes") or "").strip() or None,
    }
    specialties = []
    if kind in VENDORS:
        if not data["cr_no"]:
            raise AuthError(_("Enter the commercial registration number."))
        if not data["vat_no"]:
            raise AuthError(_("Enter the VAT number."))
        if form.get("approval_status") not in APPROVAL:
            raise AuthError(_("Choose the approval status."))
        data["approval_status"] = form.get("approval_status")
    if kind == "subcontractor":
        allowed = {r["code"] for r in catalog(db, "specialty", active_only=True)}
        specialties = sorted({s for s in _getlist(form, "specialties") if s in allowed})
        if not specialties:
            raise AuthError(_("Choose at least one specialty."))
    return data, specialties


def _getlist(form, key):
    return form.getlist(key) if hasattr(form, "getlist") else list(form.get(key) or [])


def create_entity(db, kind, form, actor_id) -> tuple[int, str]:
    if kind not in ENTITY_KINDS:
        raise AuthError(_("Choose the entity type."))
    data, specialties = _clean_entity(db, form, kind)
    prefix = ENTITY_KINDS[kind][1]
    with tx(db):
        code = f"ENT-{prefix}-{next_counter(db, f'entity-{prefix}'):04d}"
        eid = db.execute(
            "INSERT INTO entities(code, kind, name, name_en, email, phone, website, cr_no, vat_no, classification, "
            "approval_status, notes, created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id",
            (code, kind, data["name"], data["name_en"], data["email"], data["phone"], data["website"], data["cr_no"],
             data["vat_no"], data["classification"], data["approval_status"], data["notes"], utcnow(), actor_id)
        ).fetchone()[0]
        for s in specialties:
            db.execute("INSERT INTO entity_specialties(entity_id, specialty_code) VALUES (?, ?)", (eid, s))
        audit.log(db, actor_id, "entity_created", "entity", eid, code=code, kind=kind, name=data["name"])
    return eid, code


def update_entity(db, eid, form, actor_id):
    cur = entity(db, eid)
    if cur is None:
        raise AuthError(_("This entity doesn't exist."))
    data, specialties = _clean_entity(db, form, cur["kind"])
    data["active"] = bool(form.get("active"))
    changes = {k: v for k, v in data.items() if (bool(cur[k]) if k == "active" else cur[k]) != v}
    have = specialties_of(db, eid)
    spec_changed = cur["kind"] == "subcontractor" and have != specialties
    if not changes and not spec_changed:
        return
    with tx(db):
        if changes:
            db.execute(f"UPDATE entities SET {', '.join(f'{k} = ?' for k in changes)} WHERE id = ?",
                       (*changes.values(), eid))
        if spec_changed:
            db.execute("DELETE FROM entity_specialties WHERE entity_id = ?", (eid,))
            for s in specialties:
                db.execute("INSERT INTO entity_specialties(entity_id, specialty_code) VALUES (?, ?)", (eid, s))
            changes["specialties"] = {"from": have, "to": specialties}
        audit.log(db, actor_id, "entity_updated", "entity", eid, code=cur["code"],
                  **{k: ({"from": cur[k], "to": v} if k != "specialties" else v) for k, v in changes.items()})


def specialties_of(db, eid) -> list[str]:
    return sorted(r[0] for r in db.execute("SELECT specialty_code FROM entity_specialties WHERE entity_id = ?", (eid,)))


def addresses(db, eid):
    return db.execute("SELECT * FROM entity_addresses WHERE entity_id = ? ORDER BY label DESC, id", (eid,)).fetchall()


def add_address(db, eid, form, actor_id):
    if entity(db, eid) is None:
        raise AuthError(_("This entity doesn't exist."))
    lab, city, details = form.get("label") or "", (form.get("city") or "").strip(), (form.get("details") or "").strip()
    if lab not in ADDRESS_LABELS:
        raise AuthError(_("Choose the address type."))
    if len(city) < 2 or len(details) < 3:
        raise AuthError(_("Enter the city and the address."))
    with tx(db):
        aid = db.execute("INSERT INTO entity_addresses(entity_id, label, city, details, created_at) VALUES (?,?,?,?,?) "
                         "RETURNING id", (eid, lab, city, details, utcnow())).fetchone()[0]
        audit.log(db, actor_id, "entity_address_added", "entity", eid, label=lab, city=city, details=details)
    return aid


def remove_address(db, eid, aid, actor_id):
    row = db.execute("SELECT * FROM entity_addresses WHERE id = ? AND entity_id = ?", (aid, eid)).fetchone()
    if row is None:
        raise AuthError(_("This address doesn't exist."))
    with tx(db):
        db.execute("DELETE FROM entity_addresses WHERE id = ?", (aid,))
        audit.log(db, actor_id, "entity_address_removed", "entity", eid, label=row["label"], city=row["city"],
                  details=row["details"])


def people(db, eid, active_only=False):
    sql = "SELECT * FROM entity_people WHERE entity_id = ?" + (" AND active = TRUE" if active_only else "")
    return db.execute(sql + " ORDER BY code", (eid,)).fetchall()


def _clean_person(form):
    d = {k: (form.get(k) or "").strip() for k in ("full_name", "job_title", "phone", "email")}
    d["email"] = d["email"].lower()
    if len(d["full_name"]) < 3:
        raise AuthError(_("Enter the person's full name."))
    if len(d["job_title"]) < 2:
        raise AuthError(_("Enter the job title."))
    if len(d["phone"]) < 7:
        raise AuthError(_("Enter the phone number."))
    if not EMAIL_RE.match(d["email"]):
        raise AuthError(_("Enter a valid email address."))
    return d


def add_person(db, eid, form, actor_id) -> tuple[int, str]:
    ent = entity(db, eid)
    if ent is None:
        raise AuthError(_("This entity doesn't exist."))
    d = _clean_person(form)
    with tx(db):
        code = f"{ent['code']}-R{next_counter(db, f'entity-person-{eid}'):02d}"
        pid = db.execute("INSERT INTO entity_people(entity_id, code, full_name, job_title, phone, email, created_at) "
                         "VALUES (?,?,?,?,?,?,?) RETURNING id",
                         (eid, code, d["full_name"], d["job_title"], d["phone"], d["email"], utcnow())).fetchone()[0]
        audit.log(db, actor_id, "entity_person_added", "entity", eid, code=code, full_name=d["full_name"])
    return pid, code


def update_person(db, eid, person_id, form, actor_id):
    cur = db.execute("SELECT * FROM entity_people WHERE id = ? AND entity_id = ?", (person_id, eid)).fetchone()
    if cur is None:
        raise AuthError(_("This person doesn't exist."))
    d = _clean_person(form)
    d["active"] = bool(form.get("active"))
    changes = {k: v for k, v in d.items() if (bool(cur[k]) if k == "active" else cur[k]) != v}
    if not changes:
        return
    if changes.get("active") is False and db.execute(
            "SELECT 1 FROM project_representatives r JOIN projects p ON p.id = r.project_id "
            "WHERE r.person_id = ? AND p.status != 'closed'", (person_id,)).fetchone():
        raise AuthError(_("This person represents the entity in an open project. Replace them there first."))
    with tx(db):
        db.execute(f"UPDATE entity_people SET {', '.join(f'{k} = ?' for k in changes)} WHERE id = ?",
                   (*changes.values(), person_id))
        audit.log(db, actor_id, "entity_person_updated", "entity", eid, code=cur["code"],
                  **{k: {"from": cur[k], "to": v} for k, v in changes.items()})


# ---------- أطراف المشروع ----------

def representatives(db, pid):
    return db.execute(
        "SELECT p.*, e.kind, e.id AS entity_id FROM project_representatives r JOIN entity_people p ON p.id = r.person_id "
        "JOIN entities e ON e.id = p.entity_id WHERE r.project_id = ? ORDER BY e.kind, p.code", (pid,)).fetchall()


def parties_complete(db, pid) -> bool:
    p = db.execute("SELECT owner_entity_id, consultant_entity_id FROM projects WHERE id = ?", (pid,)).fetchone()
    if p is None or not p["owner_entity_id"]:
        return False
    reps = representatives(db, pid)
    for eid in (p["owner_entity_id"], p["consultant_entity_id"]):
        if eid and sum(1 for r in reps if r["entity_id"] == eid) < MIN_REPRESENTATIVES:
            return False
    return True


def set_project_parties(db, pid, form, actor_id):
    """المالك إلزامي والاستشاري اختياري، ولكل جهة مختارة ممثلان على الأقل من أشخاصها (المادة 2)."""
    p = db.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    if p is None:
        raise AuthError(_("This project doesn't exist."))
    chosen, reps = {}, set()
    for kind, field in (("owner", "owner_entity_id"), ("consultant", "consultant_entity_id")):
        raw = str(form.get(field) or "")
        if not raw:
            if kind == "owner":
                raise AuthError(_("Choose the project owner."))
            chosen[field] = None
            continue
        ent = entity(db, int(raw)) if raw.isdigit() else None
        if ent is None or ent["kind"] != kind or not ent["active"]:
            raise AuthError(_("Choose an active entity of the right type."))
        allowed = {r["id"] for r in people(db, ent["id"], active_only=True)}
        picked = {int(x) for x in _getlist(form, f"{kind}_reps") if str(x).isdigit() and int(x) in allowed}
        if len(picked) < MIN_REPRESENTATIVES:
            raise AuthError(_("Choose at least {n} representatives for {party}.", n=MIN_REPRESENTATIVES,
                              party=_(ENTITY_KINDS[kind][0])))
        chosen[field] = ent
        reps |= picked
    have = {r["id"] for r in representatives(db, pid)}
    owner, consultant = chosen["owner_entity_id"], chosen["consultant_entity_id"]
    new_ids = (owner["id"], consultant["id"] if consultant else None)
    if (p["owner_entity_id"], p["consultant_entity_id"]) == new_ids and have == reps:
        return
    with tx(db):
        # الاسم النصي القديم يبقى متزامنًا مع الجهة حتى تبقى الشاشات والتقارير القديمة صحيحة
        db.execute("UPDATE projects SET owner_entity_id = ?, consultant_entity_id = ?, client = ?, consultant = ? "
                   "WHERE id = ?", (new_ids[0], new_ids[1], owner["name"], consultant["name"] if consultant else None, pid))
        for person in have - reps:
            db.execute("DELETE FROM project_representatives WHERE project_id = ? AND person_id = ?", (pid, person))
        for person in reps - have:
            db.execute("INSERT INTO project_representatives(project_id, person_id, assigned_at, assigned_by) "
                       "VALUES (?,?,?,?)", (pid, person, utcnow(), actor_id))
        audit.log(db, actor_id, "project_parties_updated", "project", pid, pid,
                  client=owner["name"], consultant=consultant["name"] if consultant else None,
                  representatives=len(reps))
