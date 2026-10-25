"""النسخ الورقية الموقّعة (قرار م. محمد 2026-10-25): يرفع المهندس ملف PDF للنسخة الموقّعة من أمر الشراء أو عقد الباطن أو
المستخلص أو الفاتورة، ويعتمدها مهندس تحكم تكلفة، ثم المدير التنفيذي لما فوق 10,000 ريال. لا يعتمدها من رفعها، والمُرجَعة
تُرفع لها نسخة جديدة وتبقى السابقة محفوظة."""
from . import audit, files
from .db import tx, utcnow
from .errors import AuthError
from .i18n import _
from .procurement import LIMIT

DOCS = {"commitment": "commitments", "payable": "payables"}
STATUS = {"review": "Waiting for cost control", "cc_ok": "Waiting for the Director", "accepted": "Accepted",
          "returned": "Returned"}


def _doc(db, pid, kind, doc_id):
    if kind not in DOCS:
        raise AuthError(_("This document doesn't exist."))
    d = db.execute(f"SELECT * FROM {DOCS[kind]} WHERE id = ? AND project_id = ?", (doc_id, pid)).fetchone()
    if d is None:
        raise AuthError(_("This document doesn't exist."))
    return d


def latest(db, pid) -> dict:
    """لكل مستند: آخر نسخة موقّعة رُفعت له، بمفتاح (النوع، المعرّف)."""
    out = {}
    for s in db.execute("SELECT * FROM signed_copies WHERE project_id = ? ORDER BY rev", (pid,)).fetchall():
        out[(s["doc_kind"], s["doc_id"])] = s
    return out


def upload(db, pid, kind, doc_id, stream, filename, actor_id) -> str:
    d = _doc(db, pid, kind, doc_id)
    last = db.execute("SELECT status, rev FROM signed_copies WHERE doc_kind = ? AND doc_id = ? ORDER BY rev DESC LIMIT 1",
                      (kind, doc_id)).fetchone()
    if last and last["status"] != "returned":
        raise AuthError(_("A signed copy is already uploaded. A new one is uploaded only after it is returned."))
    data = files.read_pdf(stream)
    rev = last["rev"] + 1 if last else 1
    project = db.execute("SELECT code FROM projects WHERE id = ?", (pid,)).fetchone()["code"]
    key = f"{project}/signed/{d['code']}-S{rev:02d}.pdf"
    amount = d["total"] if kind == "commitment" else d["net"]
    files.put(key, data)
    with tx(db):
        db.execute("INSERT INTO signed_copies(project_id, doc_kind, doc_id, rev, file_name, size_bytes, storage_key, needs_director, "
                   "uploaded_at, uploaded_by) VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (pid, kind, doc_id, rev, (filename or "signed.pdf")[:120], len(data), key, amount > LIMIT, utcnow(), actor_id))
        audit.log(db, actor_id, "signed_copy_uploaded", "project", pid, pid, code=d["code"])
    return d["code"]


def _copy(db, pid, sid):
    s = db.execute("SELECT * FROM signed_copies WHERE id = ? AND project_id = ?", (sid, pid)).fetchone()
    if s is None:
        raise AuthError(_("This signed copy doesn't exist."))
    return s


def decide(db, pid, sid, accept, reason, actor_id, director=False):
    s = _copy(db, pid, sid)
    if s["status"] != ("cc_ok" if director else "review"):
        raise AuthError(_("This is not waiting for you."))
    if actor_id in (s["uploaded_by"], s["cc_by"]):
        raise AuthError(_("Whoever uploads or approved before can't approve again."))
    code = _doc(db, pid, s["doc_kind"], s["doc_id"])["code"]
    if not accept:
        reason = (reason or "").strip()
        if len(reason) < 5:
            raise AuthError(_("Write the reason for returning."))
        sets, args = "status = 'returned', return_reason = ?", (reason,)
    elif director:
        sets, args = "status = 'accepted', dir_at = ?, dir_by = ?", (utcnow(), actor_id)
    else:
        sets, args = "status = ?, cc_at = ?, cc_by = ?", ("cc_ok" if s["needs_director"] else "accepted", utcnow(), actor_id)
    with tx(db):
        db.execute(f"UPDATE signed_copies SET {sets} WHERE id = ?", (*args, sid))
        audit.log(db, actor_id, "signed_copy_accepted" if accept else "signed_copy_returned", "project", pid, pid, code=code,
                  **({} if accept else {"reason": reason}))


def content(db, pid, sid) -> tuple[bytes, str]:
    s = _copy(db, pid, sid)
    return files.get(s["storage_key"]), s["storage_key"].rsplit("/", 1)[-1]
