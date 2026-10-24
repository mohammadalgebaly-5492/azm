"""هيكل WBS وجدول الكميات وخط الأساس."""
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from . import audit
from .auth import AuthError
from .db import tx, utcnow

TYPES = {"supply": ("توريد", "S"), "exec": ("تنفيذ", "E"), "both": ("توريد وتنفيذ", "SE")}
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
        raise AuthError(f"أدخل {what}.")
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise AuthError(f"صيغة {what} غير صحيحة: {v}")
    if d < 0:
        raise AuthError(f"{what} لا يمكن أن تكون سالبة.")
    return d.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def parse_qty(v) -> int:
    q = int(_dec(v, 3, "الكمية") * 1000)
    if q <= 0:
        raise AuthError("الكمية يجب أن تكون أكبر من صفر.")
    return q


def parse_rate(v) -> int:
    return int(_dec(v, 2, "سعر الوحدة") * 100)


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
        raise AuthError(f"نوع البند غير معروف: {v}. الأنواع: توريد، تنفيذ، توريد وتنفيذ.")
    return t


def is_locked(db, pid) -> bool:
    r = db.execute("SELECT baseline_approved_at FROM projects WHERE id = ?", (pid,)).fetchone()
    return bool(r and r[0])


def _ensure_unlocked(db, pid):
    if is_locked(db, pid):
        raise AuthError("الميزانية الأصلية معتمدة ومجمّدة. أي تغيير بعد الاعتماد يتم عبر تحويلات أو أوامر تغيير.")


# ---------- WBS ----------

def wbs_nodes(db, pid):
    return db.execute("SELECT * FROM wbs_nodes WHERE project_id = ? ORDER BY code", (pid,)).fetchall()


def add_wbs(db, pid, name, parent_id, actor_id, _in_tx=False):
    name = (name or "").strip()
    if len(name) < 2:
        raise AuthError("أدخل اسم عنصر الـ WBS.")
    _ensure_unlocked(db, pid)
    parent = None
    if parent_id:
        parent = db.execute("SELECT * FROM wbs_nodes WHERE id = ? AND project_id = ?", (parent_id, pid)).fetchone()
        if parent is None:
            raise AuthError("العنصر الأب غير موجود في هذا المشروع.")
        if parent["level"] >= MAX_LEVEL:
            raise AuthError(f"الحد الأقصى لعمق الـ WBS هو {MAX_LEVEL} مستويات.")
    level = parent["level"] + 1 if parent else 1

    def _do():
        if parent:
            sib = db.execute("SELECT code FROM wbs_nodes WHERE parent_id = ?", (parent["id"],)).fetchall()
        else:
            sib = db.execute("SELECT code FROM wbs_nodes WHERE project_id = ? AND parent_id IS NULL", (pid,)).fetchall()
        n = max([int(r[0].rsplit(".", 1)[-1]) for r in sib], default=0) + 1
        if n > 99:
            raise AuthError("الحد الأقصى 99 عنصرًا في نفس المستوى.")
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
        raise AuthError("أدخل اسم عنصر الـ WBS.")
    with tx(db):
        cur = db.execute("UPDATE wbs_nodes SET name = ? WHERE id = ? AND project_id = ?", (name, wbs_id, pid))
        if not cur.rowcount:
            raise AuthError("العنصر غير موجود.")
        audit.log(db, actor_id, "wbs_renamed", "wbs", wbs_id, pid, name=name)


def delete_wbs(db, pid, wbs_id, actor_id):
    _ensure_unlocked(db, pid)
    node = db.execute("SELECT * FROM wbs_nodes WHERE id = ? AND project_id = ?", (wbs_id, pid)).fetchone()
    if node is None:
        raise AuthError("العنصر غير موجود.")
    if db.execute("SELECT 1 FROM wbs_nodes WHERE parent_id = ?", (wbs_id,)).fetchone():
        raise AuthError("احذف العناصر الفرعية أولًا.")
    if db.execute("SELECT 1 FROM boq_items WHERE wbs_id = ?", (wbs_id,)).fetchone():
        raise AuthError("العنصر فيه بنود. انقلها أو احذفها أولًا.")
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
        raise AuthError("أدخل وصف البند.")
    if not unit:
        raise AuthError("أدخل وحدة البند.")
    item_type = norm_type(f.get("item_type"))
    if item_type is None:
        raise AuthError("اختر نوع البند.")
    qty = parse_qty(f.get("qty"))
    rate = parse_rate(f.get("unit_rate"))
    return {"description": desc, "unit": unit, "item_type": item_type, "qty_milli": qty, "unit_rate": rate,
            "amount": amount_of(qty, rate), "ref_no": (str(f.get("ref_no") or "").strip() or None),
            "notes": (f.get("notes") or "").strip() or None}


def add_item(db, pid, wbs_id, form, actor_id, _in_tx=False):
    _ensure_unlocked(db, pid)
    wbs = db.execute("SELECT * FROM wbs_nodes WHERE id = ? AND project_id = ?", (wbs_id, pid)).fetchone()
    if wbs is None:
        raise AuthError("اختر عنصر WBS من نفس المشروع.")
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
        raise AuthError("البند غير موجود.")
    d = _clean_item(form)
    if d["item_type"] != cur["item_type"]:
        raise AuthError("نوع البند جزء من كوده ولا يتغير. احذف البند وأضفه بالنوع الصحيح.")
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
        raise AuthError("البند غير موجود.")
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
    _, total, _ = summary(db, pid)
    n_items = db.execute("SELECT COUNT(*) FROM boq_items WHERE project_id = ?", (pid,)).fetchone()[0]
    zero_rate = db.execute("SELECT COUNT(*) FROM boq_items WHERE project_id = ? AND unit_rate = 0", (pid,)).fetchone()[0]
    empty_wbs = db.execute(
        "SELECT COUNT(*) FROM wbs_nodes w WHERE project_id = ? AND NOT EXISTS (SELECT 1 FROM boq_items b WHERE b.wbs_id = w.id) "
        "AND NOT EXISTS (SELECT 1 FROM wbs_nodes c WHERE c.parent_id = w.id)", (pid,)).fetchone()[0]
    checks = [
        (n_items > 0, f"جدول الكميات فيه {n_items} بند", True),
        (zero_rate == 0, "كل البنود مسعّرة" if zero_rate == 0 else f"{zero_rate} بند بسعر صفر", True),
        (empty_wbs == 0, "لا توجد عناصر WBS فارغة" if empty_wbs == 0 else f"{empty_wbs} عنصر WBS بدون بنود", False),
    ]
    if p["contract_value"]:
        diff = p["contract_value"] - total
        checks.append((diff == 0, "إجمالي الجدول يساوي قيمة العقد" if diff == 0 else
                       f"الفرق عن قيمة العقد {abs(diff) / 100:,.2f} ريال ({'أقل' if diff > 0 else 'أكبر'})", False))
    blocking_ok = all(ok for ok, _, blocking in checks if blocking)
    return checks, blocking_ok, total


def approve_baseline(db, pid, actor_id):
    _ensure_unlocked(db, pid)
    checks, ok, total = baseline_checks(db, pid)
    if not ok:
        raise AuthError("لا يمكن الاعتماد: " + "، ".join(t for c, t, b in checks if b and not c))
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
    raise AuthError("الملف لازم يكون Excel (.xlsx) أو CSV.")


def parse_import(rows, default_type):
    """يرجع قائمة صفوف: {kind: 'heading'|'item', ...} وقائمة أخطاء. صف بدون كمية = عنوان قسم (WBS)."""
    header_idx, cols = None, {}
    for i, r in enumerate(rows[:30]):
        c = detect_columns(r)
        if "description" in c and "qty" in c and "unit_rate" in c:
            header_idx, cols = i, c
            break
    if header_idx is None:
        raise AuthError("لم أجد صف العناوين. لازم يكون فيه أعمدة: الوصف، الكمية، سعر الوحدة (أو Description, Qty, Rate).")
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
                    errors.append((n, f"الإجمالي في الملف {g / 100:,.2f} لا يساوي الكمية × السعر {item['amount'] / 100:,.2f}"))
                    continue
            except AuthError:
                pass
        out.append({"kind": "item", "row": n, **item})
    if not any(x["kind"] == "item" for x in out) and not errors:
        raise AuthError("الملف لا يحتوي على بنود بكميات وأسعار.")
    return out, errors


def commit_import(db, pid, parsed, root_wbs_id, actor_id):
    """يحفظ الصفوف دفعة واحدة: كل عنوان يصبح عنصر WBS (رئيسيًا أو تحت العنصر المختار)، والبنود تحت آخر عنوان قبلها."""
    _ensure_unlocked(db, pid)
    n_items = n_heads = 0
    with tx(db):
        current = root_wbs_id
        for row in parsed:
            if row["kind"] == "heading":
                current, _ = add_wbs(db, pid, row["name"], root_wbs_id, actor_id, _in_tx=True)
                n_heads += 1
            else:
                if current is None:  # بنود قبل أي عنوان قسم
                    current, _ = add_wbs(db, pid, "بنود عامة", None, actor_id, _in_tx=True)
                    n_heads += 1
                add_item(db, pid, current, {**row, "qty": Decimal(row["qty_milli"]) / 1000,
                                            "unit_rate": Decimal(row["unit_rate"]) / 100}, actor_id, _in_tx=True)
                n_items += 1
        audit.log(db, actor_id, "boq_imported", "project", pid, pid, items=n_items, sections=n_heads)
    return n_items, n_heads
