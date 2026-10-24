"""صورة الحساب: صورة جاهزة من مجموعة هندسية، أو صورة يرفعها المستخدم، أو الحرف الأول من الاسم."""
import io

from .db import tx, utcnow
from .errors import AuthError
from .i18n import _

# المفتاح: (الاسم بالإنجليزية، رسم SVG على شبكة 24×24). الألوان في style.css (.avatar.p-<المفتاح>)
PRESETS = {
    "helmet": ("Hard hat", '<path d="M3.5 17.5h17"/><path d="M5 17.5a7 7 0 0 1 14 0"/><path d="M10 10.8V7.5h4v3.3"/>'),
    "crane": ("Tower crane", '<path d="M7 20V4l12 3"/><path d="M4 7h16"/><path d="M17 7v5"/><rect x="15.5" y="12" width="3" height="2.5" rx=".4"/><path d="M4.5 20h5"/>'),
    "compass": ("Drafting compass", '<circle cx="12" cy="5" r="1.6"/><path d="M11.3 6.5 7.2 19.5M12.7 6.5l4.1 13"/><path d="M8.7 14.6h6.6"/>'),
    "blueprint": ("Blueprint", '<rect x="4" y="5" width="16" height="14" rx="1.5"/><path d="M4 10.5h5V19M9 14.5h11M14.5 5v5.5"/>'),
    "square": ("Set square", '<path d="M5 19V5l14 14z"/><path d="M8.5 15.5V12l3.5 3.5z"/>'),
    "beam": ("Steel beam", '<path d="M6 5h12M6 19h12M12 5v14"/><path d="M8.5 5v2M15.5 5v2M8.5 19v-2M15.5 19v-2"/>'),
    "building": ("Building", '<path d="M5.5 20V5h8v15M13.5 10h5v10"/><path d="M8.5 8.5h2M8.5 12h2M8.5 15.5h2M16 13.5h0M16 16.5h0"/><path d="M3.5 20h17"/>'),
    "level": ("Spirit level", '<rect x="3" y="9" width="18" height="6" rx="1.5"/><rect x="10" y="10.5" width="4" height="3" rx="1.5"/><path d="M12 10.5v3"/>'),
}

MAX_BYTES = 4 * 1024 * 1024
SIZE = 256


def set_preset(db, user_id: int, key: str):
    if key not in PRESETS:
        raise AuthError(_("Choose one of the available avatars."))
    with tx(db):
        db.execute("UPDATE users SET avatar = ? WHERE id = ?", (f"p:{key}", user_id))
        db.execute("DELETE FROM user_avatars WHERE user_id = ?", (user_id,))


def clear(db, user_id: int):
    with tx(db):
        db.execute("UPDATE users SET avatar = NULL WHERE id = ?", (user_id,))
        db.execute("DELETE FROM user_avatars WHERE user_id = ?", (user_id,))


def save_upload(db, user_id: int, stream):
    """يتحقق من الصورة ويقصّها مربعًا ويصغّرها إلى 256×256 JPEG قبل الحفظ."""
    import warnings
    from PIL import Image, ImageOps
    raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise AuthError(_("The photo must be smaller than 4 MB."))
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            img = Image.open(io.BytesIO(raw))
            if img.format not in ("JPEG", "PNG", "WEBP"):
                raise ValueError(img.format)
            img.load()
    except Exception:
        raise AuthError(_("The file must be a JPEG, PNG or WebP photo."))
    img = ImageOps.exif_transpose(img).convert("RGB")
    img = ImageOps.fit(img, (SIZE, SIZE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=86, optimize=True, progressive=True)
    row = db.execute("SELECT avatar FROM users WHERE id = ?", (user_id,)).fetchone()
    old = row[0] if row else None
    version = int(old[2:]) + 1 if old and old.startswith("u:") and old[2:].isdigit() else 1
    with tx(db):
        db.execute("DELETE FROM user_avatars WHERE user_id = ?", (user_id,))
        db.execute("INSERT INTO user_avatars(user_id, content_type, data, updated_at) VALUES (?, ?, ?, ?)",
                   (user_id, "image/jpeg", out.getvalue(), utcnow()))
        db.execute("UPDATE users SET avatar = ? WHERE id = ?", (f"u:{version}", user_id))


def load(db, user_id: int):
    row = db.execute("SELECT content_type, data FROM user_avatars WHERE user_id = ?", (user_id,)).fetchone()
    return (row[0], bytes(row[1])) if row else None
