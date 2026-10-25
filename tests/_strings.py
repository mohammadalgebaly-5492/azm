"""يجمع كل نصوص الواجهة من الكود والقوالب (للاختبار وللمطورين)."""
import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent / "app"
TEMPLATE_CALL = re.compile(r"""_\(\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')""")


def template_strings():
    out = set()
    for f in (ROOT / "templates").rglob("*.html"):
        for m in TEMPLATE_CALL.finditer(f.read_text(encoding="utf-8")):
            out.add((m.group(1) if m.group(1) is not None else m.group(2)).replace("\\'", "'"))
    return out


def python_strings():
    out = set()
    for f in ROOT.rglob("*.py"):
        if f.name == "i18n_ar.py":
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_" and node.args \
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                out.add(node.args[0].value)
    return out


def table_strings():
    """نصوص تُترجم وقت العرض من جداول ثابتة (الصلاحيات، العمليات، الأنواع، الصور، صفحات الخطأ...)."""
    from app import COMPACT_UNITS, ERRORS
    from app.analytics import WIDGETS
    from app.audit import ACTION_LABELS, FIELD_LABELS, REASONS, STATUS_LABELS
    from app.avatars import PRESETS
    from app.boq import TYPES
    from app.rbac import PERMISSION_GROUPS, PERMISSIONS
    out = {v[0] for v in TYPES.values()} | set(ACTION_LABELS.values()) | {v[0] for v in PRESETS.values()}
    out |= set(FIELD_LABELS.values()) | set(REASONS.values()) | set(STATUS_LABELS.values()) | {g[0] for g in PERMISSION_GROUPS}
    out |= {s for pair in PERMISSIONS.values() for s in pair} | {s for pair in ERRORS.values() for s in pair}
    out |= {w.TITLE for w in WIDGETS} | {u for _, u in COMPACT_UNITS}
    from app.registers import ADDRESS_LABELS, APPROVAL, CATALOGS, COST_UNITS, ENTITY_KINDS
    out |= {s for pair in CATALOGS.values() for s in pair} | {v[0] for v in ENTITY_KINDS.values()}
    out |= set(APPROVAL.values()) | set(ADDRESS_LABELS.values()) | set(COST_UNITS.values())
    from app.contracts import GUARANTEES, INSURANCES, KINDS, PENALTY_METHODS, VO_STATUS
    out |= set(GUARANTEES.values()) | set(INSURANCES.values()) | set(KINDS.values()) | set(PENALTY_METHODS.values())
    out |= set(VO_STATUS.values())
    from app.resources import ALLOCATION_STATUS, EQUIPMENT_STATUS, OWNERSHIP, PERSON_STATUS, RESOURCE_KINDS
    out |= set(ALLOCATION_STATUS.values()) | set(EQUIPMENT_STATUS.values()) | set(OWNERSHIP.values())
    out |= set(PERSON_STATUS.values()) | set(RESOURCE_KINDS.values())
    return out


def all_strings():
    return template_strings() | python_strings() | table_strings()


if __name__ == "__main__":
    for s in sorted(all_strings()):
        print(repr(s))
