"""نطاق العمل (الدستور، البند 3.7): وصف نطاق كل بند ومخططاته المرجعية، وخطوات تنفيذه بالترتيب وأوزانها وجهة تنفيذ كل خطوة."""
from . import audit
from .boq import is_locked
from .contracts import fmt_pct, parse_pct
from .db import next_counter, tx, utcnow
from .documents import DRAWING_TYPES, SPEC_TYPES
from .errors import AuthError
from .i18n import _

PARTIES = {"crew": "Company crew", "subcontractor": "Subcontractor"}
METHODS = {"self": "By company crews", "sub": "Subcontracted", "mixed": "Mixed"}
FULL = 10000


def _item(db, pid, iid):
    item = db.execute("SELECT * FROM boq_items WHERE id = ? AND project_id = ?", (iid, pid)).fetchone()
    if item is None:
        raise AuthError(_("Item not found."))
    return item


def scope_of(db, iid):
    return db.execute("SELECT * FROM item_scopes WHERE boq_item_id = ?", (iid,)).fetchone()


def scope_docs(db, iid):
    return db.execute("SELECT d.* FROM item_scope_docs s JOIN documents d ON d.id = s.document_id "
                      "WHERE s.boq_item_id = ? ORDER BY d.code", (iid,)).fetchall()


def steps(db, iid):
    return db.execute(
        "SELECT s.*, c.name AS crew_name, c.code AS crew_code, e.name AS entity_name, e.code AS entity_code, "
        "q.code AS eq_code, q.catalog_code AS eq_catalog, q.label AS eq_label, "
        "(SELECT COUNT(*) FROM allocations a WHERE a.step_id = s.id) AS n_allocs "
        "FROM scope_steps s LEFT JOIN crews c ON c.id = s.crew_id LEFT JOIN entities e ON e.id = s.entity_id "
        "LEFT JOIN equipment q ON q.id = s.equipment_id WHERE s.boq_item_id = ? ORDER BY s.seq, s.id", (iid,)).fetchall()


def method(rows) -> str | None:
    """طريقة تنفيذ البند من جهات خطواته: ذاتي، أو مسند، أو مختلط."""
    parties = {r["party"] for r in rows}
    if not parties:
        return None
    return "mixed" if len(parties) > 1 else ("sub" if parties == {"subcontractor"} else "self")


def checks(db, iid) -> list[tuple[bool, str]]:
    """شروط اكتمال نطاق البند، بالترتيب الذي تُعرض به."""
    sc, docs, rows = scope_of(db, iid), scope_docs(db, iid), steps(db, iid)
    total = sum(r["weight_bp"] for r in rows)
    return [
        (sc is not None, _("A brief description and what the item includes")),
        (any(d["doc_type"] in DRAWING_TYPES for d in docs), _("At least one reference drawing")),
        (bool(rows), _("Execution steps in order")),
        (total == FULL, _("Step weights add up to 100% (now {pct})", pct=fmt_pct(total))),
    ]


def overview(db, pid) -> list[dict]:
    out = []
    for item in db.execute("SELECT * FROM boq_items WHERE project_id = ? ORDER BY code", (pid,)).fetchall():
        rows, sc = steps(db, item["id"]), scope_of(db, item["id"])
        ok = all(c for c, _t in checks(db, item["id"]))
        out.append({"item": item, "scope": sc, "steps": len(rows), "weight": sum(r["weight_bp"] for r in rows),
                    "method": method(rows), "complete": ok, "reviewed": bool(sc and sc["reviewed_at"])})
    return out


def _ensure_open(db, iid):
    sc = scope_of(db, iid)
    if sc is not None and sc["reviewed_at"]:
        raise AuthError(_("This scope is reviewed and locked. Reopen it first."))


def save_scope(db, pid, iid, form, actor_id):
    item = _item(db, pid, iid)
    _ensure_open(db, iid)
    d = {"summary": (form.get("summary") or "").strip(), "includes": (form.get("includes") or "").strip(),
         "excludes": (form.get("excludes") or "").strip() or None}
    if len(d["summary"]) < 5:
        raise AuthError(_("Write a brief description of the scope."))
    if len(d["includes"]) < 5:
        raise AuthError(_("Write what the item includes."))
    getlist = form.getlist if hasattr(form, "getlist") else (lambda k: form.get(k) or [])
    allowed = {r["id"]: r["doc_type"] for r in db.execute(
        "SELECT id, doc_type FROM documents WHERE project_id = ?", (pid,)).fetchall()}
    chosen = sorted({int(x) for x in getlist("documents") if str(x).isdigit() and int(x) in allowed})
    if not any(allowed[x] in DRAWING_TYPES for x in chosen):
        raise AuthError(_("Choose at least one reference drawing. Register the drawings in the project documents first."))
    with tx(db):
        if scope_of(db, iid) is None:
            db.execute("INSERT INTO item_scopes(boq_item_id, project_id, summary, includes, excludes, updated_at, updated_by) "
                       "VALUES (?,?,?,?,?,?,?)", (iid, pid, d["summary"], d["includes"], d["excludes"], utcnow(), actor_id))
        else:
            db.execute("UPDATE item_scopes SET summary = ?, includes = ?, excludes = ?, updated_at = ?, updated_by = ? "
                       "WHERE boq_item_id = ?", (d["summary"], d["includes"], d["excludes"], utcnow(), actor_id, iid))
        db.execute("DELETE FROM item_scope_docs WHERE boq_item_id = ?", (iid,))
        for x in chosen:
            db.execute("INSERT INTO item_scope_docs(boq_item_id, document_id) VALUES (?, ?)", (iid, x))
        audit.log(db, actor_id, "scope_saved", "project", pid, pid, code=item["code"], count=len(chosen))


def _clean_step(db, pid, iid, form, step_id=None):
    s = {"name": (form.get("name") or "").strip(), "party": form.get("party") or "",
         "notes": (form.get("notes") or "").strip() or None,
         "weight_bp": parse_pct(form.get("weight_pct"), _("the step weight"), required=True)}
    if len(s["name"]) < 2:
        raise AuthError(_("Enter the step name."))
    if s["weight_bp"] < 1:
        raise AuthError(_("{what} must be a percentage between 0 and 100.", what=_("the step weight")))
    others = db.execute("SELECT COALESCE(SUM(weight_bp), 0) FROM scope_steps WHERE boq_item_id = ? AND id != ?",
                        (iid, step_id or 0)).fetchone()[0]
    if others + s["weight_bp"] > FULL:
        raise AuthError(_("The weights would exceed 100%. The other steps already take {pct}.", pct=fmt_pct(others)))
    if s["party"] not in PARTIES:
        raise AuthError(_("Choose who executes the step: a company crew or a subcontractor."))
    s["crew_id"] = s["entity_id"] = None
    if s["party"] == "crew":
        raw = str(form.get("crew_id") or "")
        if not raw.isdigit() or not db.execute("SELECT 1 FROM crews WHERE id = ? AND active = TRUE", (int(raw),)).fetchone():
            raise AuthError(_("Choose the company crew."))
        s["crew_id"] = int(raw)
    else:
        raw = str(form.get("entity_id") or "")
        if not raw.isdigit() or not db.execute(
                "SELECT 1 FROM entities WHERE id = ? AND kind = 'subcontractor' AND approval_status = 'approved' "
                "AND active = TRUE", (int(raw),)).fetchone():
            raise AuthError(_("Only an approved subcontractor can be chosen."))
        s["entity_id"] = int(raw)
    raw = str(form.get("equipment_id") or "")
    s["equipment_id"] = int(raw) if raw.isdigit() else None
    if s["equipment_id"] and not db.execute("SELECT 1 FROM equipment WHERE id = ? AND status != 'out'",
                                            (s["equipment_id"],)).fetchone():
        raise AuthError(_("This equipment is out of service and can't be allocated."))
    raw = str(form.get("seq") or "")
    if raw:
        if not raw.isdigit() or int(raw) < 1:
            raise AuthError(_("Enter the order as a whole number."))
        s["seq"] = int(raw)
    return s


def add_step(db, pid, iid, form, actor_id) -> tuple[int, str]:
    item = _item(db, pid, iid)
    _ensure_open(db, iid)
    s = _clean_step(db, pid, iid, form)
    s.setdefault("seq", db.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM scope_steps WHERE boq_item_id = ?",
                                   (iid,)).fetchone()[0])
    counter = "st-%d" % iid
    with tx(db):
        code = f"{item['code']}-ST{next_counter(db, counter):02d}"
        sid = db.execute(f"INSERT INTO scope_steps(project_id, boq_item_id, code, {', '.join(s)}, created_at, created_by) "
                         f"VALUES (?, ?, ?, {', '.join('?' for _ in s)}, ?, ?) RETURNING id",
                         (pid, iid, code, *s.values(), utcnow(), actor_id)).fetchone()[0]
        audit.log(db, actor_id, "step_added", "project", pid, pid, code=code, name=s["name"], weight_bp=s["weight_bp"])
    return sid, code


def _step(db, pid, sid):
    row = db.execute("SELECT * FROM scope_steps WHERE id = ? AND project_id = ?", (sid, pid)).fetchone()
    if row is None:
        raise AuthError(_("This step doesn't exist."))
    return row


def update_step(db, pid, sid, form, actor_id):
    cur = _step(db, pid, sid)
    _ensure_open(db, cur["boq_item_id"])
    s = _clean_step(db, pid, cur["boq_item_id"], form, sid)
    if s["party"] != cur["party"] and db.execute("SELECT 1 FROM allocations WHERE step_id = ? AND status != 'cancelled'",
                                                 (sid,)).fetchone():
        raise AuthError(_("Resources are allocated to this step. Cancel them before changing who executes it."))
    changes = {k: v for k, v in s.items() if cur[k] != v}
    if not changes:
        return
    with tx(db):
        db.execute(f"UPDATE scope_steps SET {', '.join(f'{k} = ?' for k in changes)} WHERE id = ?", (*changes.values(), sid))
        audit.log(db, actor_id, "step_updated", "project", pid, pid, code=cur["code"],
                  **{k: {"from": cur[k], "to": v} for k, v in changes.items() if k in ("name", "weight_bp", "party", "seq")})


def delete_step(db, pid, sid, actor_id):
    cur = _step(db, pid, sid)
    _ensure_open(db, cur["boq_item_id"])
    if db.execute("SELECT 1 FROM allocations WHERE step_id = ?", (sid,)).fetchone():
        raise AuthError(_("Resources are allocated to this step, so it can't be deleted."))
    with tx(db):
        db.execute("DELETE FROM scope_steps WHERE id = ?", (sid,))
        audit.log(db, actor_id, "step_deleted", "project", pid, pid, code=cur["code"])


def review_scope(db, pid, iid, actor_id):
    """مراجعة مهندس تحكم تكلفة: النطاق مكتمل، ومن أعدّه لا يراجعه. بعد المراجعة يُقفل."""
    item = _item(db, pid, iid)
    sc = scope_of(db, iid)
    if sc is None or sc["reviewed_at"]:
        raise AuthError(_("Write the scope first.") if sc is None else _("This scope is already reviewed."))
    if not all(ok for ok, _t in checks(db, iid)):
        raise AuthError(_("The scope is not complete yet."))
    if sc["updated_by"] == actor_id:
        raise AuthError(_("Whoever prepares the scope can't review it."))
    with tx(db):
        db.execute("UPDATE item_scopes SET reviewed_at = ?, reviewed_by = ? WHERE boq_item_id = ?", (utcnow(), actor_id, iid))
        audit.log(db, actor_id, "scope_reviewed", "project", pid, pid, code=item["code"])


def reopen_scope(db, pid, iid, reason, actor_id, may_approve=False):
    """فتح نطاق مُراجَع للتعديل بسبب مكتوب. بعد اعتماد الميزانية يحتاج صلاحية اعتماد التغيير."""
    item = _item(db, pid, iid)
    sc = scope_of(db, iid)
    if sc is None or not sc["reviewed_at"]:
        raise AuthError(_("This scope is not reviewed."))
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise AuthError(_("Write the reason for reopening."))
    if is_locked(db, pid) and not may_approve:
        raise AuthError(_("After the budget approval, only the Director can reopen a reviewed scope."))
    with tx(db):
        db.execute("UPDATE item_scopes SET reviewed_at = NULL, reviewed_by = NULL WHERE boq_item_id = ?", (iid,))
        audit.log(db, actor_id, "scope_reopened", "project", pid, pid, code=item["code"], reason=reason)


def project_steps(db, pid):
    """كل خطوات المشروع للاختيار في التخصيص."""
    return db.execute("SELECT s.id, s.code, s.name, s.party, s.boq_item_id, s.crew_id, s.entity_id FROM scope_steps s "
                      "JOIN boq_items b ON b.id = s.boq_item_id WHERE s.project_id = ? ORDER BY b.code, s.seq, s.id",
                      (pid,)).fetchall()
