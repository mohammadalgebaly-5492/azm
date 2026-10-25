"""هيكل WBS وجدول الكميات وخط الأساس."""
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from . import audit
from .errors import AuthError
from .i18n import _
from .db import tx, utcnow

# المفتاح: (الاسم بالإنجليزية، رمز الكود)
TYPES = {"supply": ("Supply", "S"), "exec": ("Execution", "E"), "both": ("Supply & Execution", "SE")}
TYPE_ALIASES = {
    "توريد": "supply", "supply": "supply", "s": "supply",
    "تنفيذ": "exec", "تركيب": "exec", "exec": "exec", "execution": "exec", "e": "exec", "install": "exec",
    "توريد وتنفيذ": "both", "توريد وتركيب": "both", "both": "both", "se": "both",
    "supply & install": "both", "supply and install": "both", "s&i": "both",
}
MAX_LEVEL = 4
ITEM_STEP = 10

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")


def _dec(v, places: int, what: str) -> Decimal:
    if isinstance(v, (int, float)):
        s = repr(float(v)) if isinstance(v, float) else str(v)
    else:
        s = str(v or "").strip().translate(_AR_DIGITS).replace(",", "").replace(" ", "")
    if not s:
        raise AuthError(_("Enter the {what}.", what=what))
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise AuthError(_("The {what} format is not valid: {v}", what=what, v=v))
    if d < 0:
        raise AuthError(_("The {what} can't be negative.", what=what))
    return d.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def parse_qty(v) -> int:
    q = int(_dec(v, 3, _("quantity")) * 1000)
    if q <= 0:
        raise AuthError(_("The quantity must be greater than zero."))
    return q


def parse_rate(v) -> int:
    return int(_dec(v, 2, _("unit rate")) * 100)


def amount_of(qty_milli: int, rate: int) -> int:
    return (qty_milli * rate + 500) // 1000


def fmt_qty(q: int) -> str:
    s = f"{q // 1000:,}"
    frac = q % 1000
    return s + (("." + f"{frac:03d}".rstrip("0")) if frac else "")


def norm_type(v, default=None):
    if v is None or str(v).strip() == "":
        return default
    t = TYPE_ALIASES.get(str(v).strip().lower())
    if t is None:
        raise AuthError(_("Unknown item type: {v}. Types: Supply, Execution, Supply & Execution.", v=v))
    return t


def is_locked(db, pid) -> bool:
    r = db.execute("SELECT baseline_approved_at FROM projects WHERE id = ?", (pid,)).fetchone()
    return bool(r and r[0])


def _ensure_unlocked(db, pid):
    if is_locked(db, pid):
        raise AuthError(_("The baseline is approved and frozen. Changes after approval go through budget transfers "
                          "or change orders."))


# ---------- WBS ----------

def wbs_nodes(db, pid):
    return db.execute("SELECT * FROM wbs_nodes WHERE project_id = ? ORDER BY code", (pid,)).fetchall()


def add_wbs(db, pid, name, parent_id, actor_id, _in_tx=False):
    name = (name or "").strip()
    if len(name) < 2:
        raise AuthError(_("Enter the WBS section name."))
    _ensure_unlocked(db, pid)
    parent = None
    if parent_id:
        parent = db.execute("SELECT * FROM wbs_nodes WHERE id = ? AND project_id = ?", (parent_id, pid)).fetchone()
        if parent is None:
            raise AuthError(_("The parent section doesn't exist in this project."))
        if parent["level"] >= MAX_LEVEL:
            raise AuthError(_("The WBS can be at most {n} levels deep.", n=MAX_LEVEL))
    level = parent["level"] + 1 if parent else 1

    def _do():
        if parent:
            sib = db.execute("SELECT code FROM wbs_nodes WHERE parent_id = ?", (parent["id"],)).fetchall()
        else:
            sib = db.execute("SELECT code FROM wbs_nodes WHERE project_id = ? AND parent_id IS NULL", (pid,)).fetchall()
        n = max([int(r[0].rsplit(".", 1)[-1]) for r in sib], default=0) + 1
        if n > 99:
            raise AuthError(_("A level can hold at most 99 sections."))
        code = f"{parent['code']}.{n:02d}" if parent else f"{n:02d}"
        wid = db.execute("INSERT INTO wbs_nodes(project_id, parent_id, code, name, level, created_at, created_by) "
                         "VALUES (?,?,?,?,?,?,?) RETURNING id", (pid, parent["id"] if parent else None, code, name,
                                                                 level, utcnow(), actor_id)).fetchone()[0]
        audit.log(db, actor_id, "wbs_added", "wbs", wid, pid, code=code, name=name)
        return wid, code

    if _in_tx:
        return _do()
    with tx(db):
        return _do()


def rename_wbs(db, pid, wbs_id, name, actor_id):
    name = (name or "").strip()
    if len(name) < 2:
        raise AuthError(_("Enter the WBS section name."))
    with tx(db):
        cur = db.execute("UPDATE wbs_nodes SET name = ? WHERE id = ? AND project_id = ?", (name, wbs_id, pid))
        if not cur.rowcount:
            raise AuthError(_("Section not found."))
        audit.log(db, actor_id, "wbs_renamed", "wbs", wbs_id, pid, name=name)


def delete_wbs(db, pid, wbs_id, actor_id):
    _ensure_unlocked(db, pid)
    node = db.execute("SELECT * FROM wbs_nodes WHERE id = ? AND project_id = ?", (wbs_id, pid)).fetchone()
    if node is None:
        raise AuthError(_("Section not found."))
    if db.execute("SELECT 1 FROM wbs_nodes WHERE parent_id = ?", (wbs_id,)).fetchone():
        raise AuthError(_("Delete the sub-sections first."))
    if db.execute("SELECT 1 FROM boq_items WHERE wbs_id = ?", (wbs_id,)).fetchone():
        raise AuthError(_("This section has items. Move or delete them first."))
    with tx(db):
        db.execute("DELETE FROM wbs_nodes WHERE id = ?", (wbs_id,))
        audit.log(db, actor_id, "wbs_deleted", "wbs", wbs_id, pid, code=node["code"])


# ---------- البنود ----------

def _next_item_code(db, wbs, item_type):
    rows = db.execute("SELECT code FROM boq_items WHERE wbs_id = ?", (wbs["id"],)).fetchall()
    n = max([int(r[0].rsplit("-", 1)[-1]) for r in rows], default=0)
    n = (n // ITEM_STEP + 1) * ITEM_STEP
    return f"{wbs['code']}-{TYPES[item_type][1]}-{n:03d}"


def _clean_item(f):
    desc = (f.get("description") or "").strip()
    unit = (f.get("unit") or "").strip()
    if len(desc) < 3:
        raise AuthError(_("Enter the item description."))
    if not unit:
        raise AuthError(_("Enter the item unit."))
    item_type = norm_type(f.get("item_type"))
    if item_type is None:
        raise AuthError(_("Choose the item type."))
    qty = parse_qty(f.get("qty"))
    rate = parse_rate(f.get("unit_rate"))
    return {"description": desc, "unit": unit, "item_type": item_type, "qty_milli": qty, "unit_rate": rate,
            "amount": amount_of(qty, rate), "ref_no": (str(f.get("ref_no") or "").strip() or None),
            "notes": (f.get("notes") or "").strip() or None}


def add_item(db, pid, wbs_id, form, actor_id, _in_tx=False):
    _ensure_unlocked(db, pid)
    wbs = db.execute("SELECT * FROM wbs_nodes WHERE id = ? AND project_id = ?", (wbs_id, pid)).fetchone()
    if wbs is None:
        raise AuthError(_("Choose a WBS section from this project."))
    d = _clean_item(form)

    def _do():
        code = _next_item_code(db, wbs, d["item_type"])
        iid = db.execute(
            "INSERT INTO boq_items(project_id, wbs_id, code, ref_no, description, item_type, unit, qty_milli, "
            "unit_rate, amount, notes, created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id",
            (pid, wbs["id"], code, d["ref_no"], d["description"], d["item_type"], d["unit"], d["qty_milli"],
             d["unit_rate"], d["amount"], d["notes"], utcnow(), actor_id)).fetchone()[0]
        if not _in_tx:
            audit.log(db, actor_id, "boq_item_added", "boq_item", iid, pid, code=code, amount=d["amount"])
        return iid, code

    if _in_tx:
        return _do()
    with tx(db):
        return _do()


def update_item(db, pid, item_id, form, actor_id):
    _ensure_unlocked(db, pid)
    cur = db.execute("SELECT * FROM boq_items WHERE id = ? AND project_id = ?", (item_id, pid)).fetchone()
    if cur is None:
        raise AuthError(_("Item not found."))
    d = _clean_item(form)
    if d["item_type"] != cur["item_type"]:
        raise AuthError(_("The item type is part of its code and can't change. Delete the item and add it again "
                          "with the right type."))
    changes = {k: v for k, v in d.items() if cur[k] != v}
    if not changes:
        return
    with tx(db):
        db.execute(f"UPDATE boq_items SET {', '.join(f'{k} = ?' for k in changes)}, updated_at = ? WHERE id = ?",
                   (*changes.values(), utcnow(), item_id))
        audit.log(db, actor_id, "boq_item_updated", "boq_item", item_id, pid, code=cur["code"],
                  **{k: {"from": cur[k], "to": v} for k, v in changes.items()})


def delete_item(db, pid, item_id, actor_id):
    _ensure_unlocked(db, pid)
    cur = db.execute("SELECT code FROM boq_items WHERE id = ? AND project_id = ?", (item_id, pid)).fetchone()
    if cur is None:
        raise AuthError(_("Item not found."))
    if db.execute("SELECT 1 FROM allocations WHERE boq_item_id = ?", (item_id,)).fetchone():
        raise AuthError(_("Resources are allocated to this item, so it can't be deleted. Its allocations stay in the record."))
    with tx(db):
        db.execute("DELETE FROM boq_items WHERE id = ?", (item_id,))
        audit.log(db, actor_id, "boq_item_deleted", "boq_item", item_id, pid, code=cur["code"])


def items(db, pid):
    return db.execute("SELECT * FROM boq_items WHERE project_id = ? ORDER BY code", (pid,)).fetchall()


def summary(db, pid):
    """إجماليات لكل عنصر WBS (شاملة الفروع) وإجمالي المشروع."""
    nodes = wbs_nodes(db, pid)
    direct = {r[0]: (r[1], r[2]) for r in db.execute(
        "SELECT wbs_id, CAST(SUM(amount) AS BIGINT), COUNT(*) FROM boq_items WHERE project_id = ? GROUP BY wbs_id", (pid,))}
    totals = {}
    for n in nodes:
        amt = cnt = 0
        for m in nodes:
            if m["code"] == n["code"] or m["code"].startswith(n["code"] + "."):
                a, c = direct.get(m["id"], (0, 0))
                amt += a
                cnt += c
        totals[n["id"]] = (amt, cnt)
    total = sum(a for a, _ in direct.values())
    by_type = {t: 0 for t in TYPES}
    for r in db.execute("SELECT item_type, CAST(SUM(amount) AS BIGINT) FROM boq_items WHERE project_id = ? GROUP BY item_type", (pid,)):
        by_type[r[0]] = r[1]
    return totals, total, by_type


# ---------- خط الأساس ----------

def baseline_checks(db, pid):
    p = db.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    total = summary(db, pid)[1]
    n_items = db.execute("SELECT COUNT(*) FROM boq_items WHERE project_id = ?", (pid,)).fetchone()[0]
    zero_rate = db.execute("SELECT COUNT(*) FROM boq_items WHERE project_id = ? AND unit_rate = 0", (pid,)).fetchone()[0]
    empty_wbs = db.execute(
        "SELECT COUNT(*) FROM wbs_nodes w WHERE project_id = ? AND NOT EXISTS (SELECT 1 FROM boq_items b WHERE b.wbs_id = w.id) "
        "AND NOT EXISTS (SELECT 1 FROM wbs_nodes c WHERE c.parent_id = w.id)", (pid,)).fetchone()[0]
    checks = [
        (n_items > 0, _("The BOQ has {n} items", n=n_items), True),
        (zero_rate == 0, _("All items are priced") if zero_rate == 0 else _("{n} items have a zero rate", n=zero_rate),
         True),
        (empty_wbs == 0, _("No empty WBS sections") if empty_wbs == 0 else
         _("{n} WBS sections have no items", n=empty_wbs), False),
    ]
    if p["contract_value"]:
        diff = p["contract_value"] - total
        checks.append((diff == 0, _("The BOQ total equals the contract value") if diff == 0 else
                       (_("The BOQ total is {amount} SAR below the contract value", amount=f"{abs(diff) / 100:,.2f}")
                        if diff > 0 else
                        _("The BOQ total is {amount} SAR above the contract value", amount=f"{abs(diff) / 100:,.2f}")),
                       False))
    blocking_ok = all(ok for ok, _, blocking in checks if blocking)
    return checks, blocking_ok, total


def approve_baseline(db, pid, actor_id):
    _ensure_unlocked(db, pid)
    checks, ok, total = baseline_checks(db, pid)
    if not ok:
        raise AuthError(_("Can't approve yet: {reasons}", reasons=_("; ").join(t for c, t, b in checks if b and not c)))
    with tx(db):
        db.execute("UPDATE projects SET baseline_total = ?, baseline_approved_at = ?, baseline_approved_by = ?, "
                   "status = CASE WHEN status = 'setup' THEN 'active' ELSE status END WHERE id = ?",
                   (total, utcnow(), actor_id, pid))
        audit.log(db, actor_id, "baseline_approved", "project", pid, pid, total=total)
    return total


# ---------- الاستيراد ----------

HEADERS = {
    "ref_no": ("رقم البند", "البند", "م", "رقم", "item", "item no", "item no.", "no", "no.", "ref", "ref.", "s.n", "sn"),
    "description": ("الوصف", "وصف البند", "البيان", "description", "desc", "description of work"),
    "unit": ("الوحدة", "وحدة", "unit", "uom"),
    "qty": ("الكمية", "كمية", "qty", "qty.", "quantity"),
    "unit_rate": ("سعر الوحدة", "الفئة", "السعر", "فئة", "rate", "unit rate", "unit price", "price"),
    "item_type": ("النوع", "نوع البند", "type"),
    "amount": ("الإجمالي", "الاجمالي", "القيمة", "المبلغ", "total", "amount"),
}


def _norm_header(v):
    return re.sub(r"\s+", " ", str(v or "").strip().lower().replace("\n", " "))


def detect_columns(row):
    cols = {}
    for i, cell in enumerate(row):
        h = _norm_header(cell)
        for key, names in HEADERS.items():
            if key not in cols and h in names:
                cols[key] = i
    return cols


def read_rows(filename, stream):
    name = (filename or "").lower()
    if name.endswith(".xlsx"):
        import openpyxl
        wb = openpyxl.load_workbook(stream, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        return [list(r) for r in ws.iter_rows(values_only=True)]
    if name.endswith(".csv"):
        import csv
        import io
        text = stream.read().decode("utf-8-sig", errors="replace")
        return [r for r in csv.reader(io.StringIO(text))]
    raise AuthError(_("The file must be Excel (.xlsx) or CSV."))


def parse_import(rows, default_type):
    """يرجع قائمة صفوف: {kind: 'heading'|'item', ...} وقائمة أخطاء. صف بدون كمية = عنوان قسم (WBS)."""
    header_idx, cols = None, {}
    for i, r in enumerate(rows[:30]):
        c = detect_columns(r)
        if "description" in c and "qty" in c and "unit_rate" in c:
            header_idx, cols = i, c
            break
    if header_idx is None:
        raise AuthError(_("Couldn't find the header row. It needs the columns: Description, Qty, Rate "
                          "(or الوصف، الكمية، سعر الوحدة)."))
    out, errors = [], []
    for n, r in enumerate(rows[header_idx + 1:], start=header_idx + 2):
        get = lambda k: (r[cols[k]] if k in cols and cols[k] < len(r) else None)
        desc = str(get("description") or "").strip()
        qty, rate = get("qty"), get("unit_rate")
        if not desc and qty in (None, "") and rate in (None, ""):
            continue
        if qty in (None, "") and rate in (None, ""):
            if desc:
                out.append({"kind": "heading", "row": n, "name": desc[:120], "ref_no": str(get("ref_no") or "").strip()})
            continue
        try:
            item = _clean_item({"description": desc, "unit": str(get("unit") or "").strip(), "qty": qty,
                                "unit_rate": rate, "item_type": norm_type(get("item_type"), default_type),
                                "ref_no": get("ref_no")})
        except AuthError as e:
            errors.append((n, str(e)))
            continue
        given = get("amount")
        if given not in (None, ""):
            try:
                g = parse_rate(given)
                if abs(g - item["amount"]) > 100:
                    errors.append((n, _("The file's total {given} doesn't equal quantity × rate {calc}",
                                        given=f"{g / 100:,.2f}", calc=f"{item['amount'] / 100:,.2f}")))
                    continue
            except AuthError:
                pass
        out.append({"kind": "item", "row": n, **item})
    if not any(x["kind"] == "item" for x in out) and not errors:
        raise AuthError(_("The file has no items with quantities and rates."))
    return out, errors


def commit_import(db, pid, parsed, root_wbs_id, actor_id):
    """يحفظ الصفوف دفعة واحدة: كل عنوان يصبح عنصر WBS (رئيسيًا أو تحت العنصر المختار)، والبنود تحت آخر عنوان قبلها."""
    _ensure_unlocked(db, pid)
    n_items = n_heads = 0
    with tx(db):
        current = root_wbs_id
        for row in parsed:
            if row["kind"] == "heading":
                current = add_wbs(db, pid, row["name"], root_wbs_id, actor_id, _in_tx=True)[0]
                n_heads += 1
            else:
                if current is None:  # بنود قبل أي عنوان قسم
                    current = add_wbs(db, pid, _("General items"), None, actor_id, _in_tx=True)[0]
                    n_heads += 1
                add_item(db, pid, current, {**row, "qty": Decimal(row["qty_milli"]) / 1000,
                                            "unit_rate": Decimal(row["unit_rate"]) / 100}, actor_id, _in_tx=True)
                n_items += 1
        audit.log(db, actor_id, "boq_imported", "project", pid, pid, items=n_items, sections=n_heads)
    return n_items, n_heads
