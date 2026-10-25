import json

from flask import has_request_context, request

from .db import utcnow
from .i18n import _


def log(db, actor_id, action, entity=None, entity_id=None, project_id=None, **details):
    ip = request.remote_addr if has_request_context() else None
    db.execute(
        "INSERT INTO audit_log(at, actor_id, action, entity, entity_id, project_id, details, ip) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (utcnow(), actor_id, action, entity, entity_id, project_id,
         json.dumps(details, ensure_ascii=False) if details else None, ip),
    )


ACTION_LABELS = {
    "login": "Signed in",
    "login_failed": "Failed sign-in attempt",
    "account_locked": "Account locked after failed attempts",
    "logout": "Signed out",
    "password_changed": "Password changed",
    "user_created": "Account created",
    "user_updated": "Account updated",
    "password_reset": "Password reset",
    "user_disabled": "Account disabled",
    "user_enabled": "Account re-enabled",
    "project_created": "Project created",
    "project_updated": "Project details updated",
    "member_added": "Member assigned to project",
    "member_removed": "Member removed from project",
    "wbs_added": "WBS section added",
    "wbs_renamed": "WBS section renamed",
    "wbs_deleted": "WBS section deleted",
    "boq_item_added": "BOQ item added",
    "boq_item_updated": "BOQ item updated",
    "boq_item_deleted": "BOQ item deleted",
    "boq_imported": "BOQ imported from Excel",
    "baseline_approved": "Baseline approved and frozen",
    "settings_updated": "Platform settings updated",
    "permissions_updated": "Role permissions updated",
    "session_revoked": "Session ended by admin",
    "sessions_revoked_all": "All other sessions ended",
    "role_created": "Role created",
    "role_updated": "Role updated",
    "role_deleted": "Role deleted",
    "invite_created": "Sign-up link created",
    "invite_revoked": "Sign-up link revoked",
    "invite_used": "Account created from a sign-up link",
    "entity_created": "Entity created",
    "entity_updated": "Entity updated",
    "entity_address_added": "Entity address added",
    "entity_address_removed": "Entity address removed",
    "entity_person_added": "Person added to an entity",
    "entity_person_updated": "Entity person updated",
    "catalog_item_added": "Lookup list entry added",
    "catalog_item_updated": "Lookup list entry updated",
    "project_parties_updated": "Project parties updated",
    "contract_created": "Main contract recorded",
    "contract_updated": "Main contract updated",
    "guarantee_added": "Bank guarantee added",
    "guarantee_released": "Bank guarantee released",
    "insurance_added": "Insurance policy added",
    "vo_created": "Change order recorded",
    "vo_approved": "Change order approved",
    "vo_rejected": "Change order rejected",
    "person_created": "Person registered", "person_updated": "Person updated",
    "crew_created": "Crew created", "crew_updated": "Crew updated",
    "equipment_created": "Equipment registered", "equipment_updated": "Equipment updated",
    "position_added": "Position added to the organization chart", "position_ended": "Position ended",
    "allocation_added": "Resource allocation recorded", "allocation_approved": "Resource allocation approved",
    "allocation_cancelled": "Resource allocation cancelled",
}


def action_label(action: str) -> str:
    return _(ACTION_LABELS[action]) if action in ACTION_LABELS else action


# ---------- عرض التفاصيل بلغة الواجهة ----------
# التفاصيل تُخزن JSON بمفاتيح ثابتة، وتُعرض للمستخدم كجمل مقروءة مترجمة بدل الكود.
FIELD_LABELS = {
    "role": "Role", "full_name": "Full name", "email": "Email", "phone": "Mobile", "job_title": "Job title",
    "status": "Status", "name": "Name", "code": "Code", "username": "Username", "amount": "Amount", "total": "Total",
    "items": "Items", "sections": "Sections", "count": "Count", "reason": "Reason", "client": "Client",
    "consultant": "Consultant", "location": "Location", "contract_no": "Main contract no.", "contract_value": "Contract value",
    "start_date": "Start date", "end_date": "End date", "description": "Description", "unit": "Unit", "qty_milli": "Quantity",
    "unit_rate": "Unit rate", "item_type": "Type", "ref_no": "Ref.", "notes": "Notes", "added": "Added", "removed": "Removed",
    "name_ar": "Name (Arabic)", "name_en": "Name (English)", "external": "External party",
    "platform_name_ar": "Platform name (Arabic)", "platform_name_en": "Platform name (English)",
    "company_name_ar": "Company name (Arabic)", "company_name_en": "Company name (English)",
    "session_idle_minutes": "Inactivity timeout (minutes)", "session_absolute_hours": "Maximum session length (hours)",
    "signup_enabled": "Sign-up links", "expires_at": "Expires", "max_uses": "Uses allowed", "user": "Username",
    "kind": "Type", "list": "List", "cr_no": "Commercial registration no.", "vat_no": "VAT number",
    "classification": "Classification grade", "approval_status": "Approval status", "website": "Website",
    "city": "City", "label": "Address type", "details": "Address", "specialties": "Specialties", "active": "Active",
    "parent_code": "Equipment type", "cost_unit": "Cost unit", "representatives": "Representatives",
    "number": "Number", "policy_no": "Policy number", "days": "Days", "signed_on": "Signing date",
    "value_ex_vat": "Contract value before VAT", "vat_bp": "VAT rate", "scope": "Brief description of the works",
    "site_handover_on": "Site handover date", "start_on": "Start date", "duration_days": "Duration in days",
    "warranty_months": "Warranty period in months", "advance_bp": "Advance payment",
    "advance_recovery_bp": "Advance recovery from each certificate", "retention_bp": "Retention from each certificate",
    "retention_cap_bp": "Retention cap of the contract value", "payment_days": "Payment period after certificate approval (days)",
    "penalty_method": "Penalty method", "penalty_value": "Penalty value (percentage or SAR per day)",
    "penalty_cap_bp": "Penalty cap of the contract value",
    "profession_code": "Profession", "job_title_code": "Job title", "id_no": "ID or residence number",
    "nationality": "Nationality", "daily_cost": "Daily cost", "user_id": "Account on the platform",
    "catalog_code": "Equipment name", "make_model": "Manufacturer and model", "plate_serial": "Plate or serial no.",
    "ownership": "Ownership", "lessor": "Lessor (if rented)",
}
REASONS = {
    "system owner role introduced": "System Owner role introduced",
    "set by programmer": "Set by the platform administrator",
    "disabled": "Account disabled",
}
STATUS_LABELS = {"active": "Active", "disabled": "Disabled", "setup": "Setup", "closed": "Closed"}


def _value(key, v):
    from .boq import TYPES, fmt_qty
    from .projects import fmt_money
    from .rbac import PERMISSIONS, role_label
    if v is None or v == "":
        return "—"
    if isinstance(v, bool):
        return _("Yes") if v else _("No")
    if key == "role":
        return role_label(v)
    if key == "status":
        from .resources import EQUIPMENT_STATUS, PERSON_STATUS
        labels = {**PERSON_STATUS, **EQUIPMENT_STATUS, **STATUS_LABELS}
        return _(labels[v]) if v in labels else str(v)
    if key in ("amount", "total", "contract_value", "unit_rate"):
        return fmt_money(v)
    if key == "qty_milli":
        return fmt_qty(v)
    if key == "item_type":
        return _(TYPES[v][0]) if v in TYPES else str(v)
    if key == "reason":
        return _(REASONS[v]) if v in REASONS else str(v)
    from .contracts import GUARANTEES, INSURANCES, KINDS, PENALTY_METHODS, fmt_pct
    from .registers import ADDRESS_LABELS, APPROVAL, CATALOGS, COST_UNITS, ENTITY_KINDS
    if key.endswith("_bp") and isinstance(v, int):
        return fmt_pct(v)
    if key in ("value_ex_vat", "daily_cost"):
        return fmt_money(v)
    from .resources import OWNERSHIP
    if key == "ownership" and v in OWNERSHIP:
        return _(OWNERSHIP[v])
    named = {"kind": {**{k: t[0] for k, t in ENTITY_KINDS.items()}, **KINDS, **GUARANTEES, **INSURANCES},
             "approval_status": APPROVAL, "label": ADDRESS_LABELS, "penalty_method": PENALTY_METHODS,
             "list": {k: t[0] for k, t in CATALOGS.items()}, "cost_unit": COST_UNITS}
    if key in named and v in named[key]:
        return _(named[key][v])
    if key == "specialties" and isinstance(v, list):
        return "، ".join(v) if v else "—"
    if key in ("added", "removed") and isinstance(v, list):
        names = [_(PERMISSIONS[p.split(":")[-1]][0]) if p.split(":")[-1] in PERMISSIONS else p for p in v]
        return "، ".join(names) if names else "—"
    if isinstance(v, str) and len(v) >= 19 and v[4] == "-" and v[10] == "T":
        return v[:16].replace("T", " ")
    return str(v)


def describe(details) -> list[str]:
    """يحوّل تفاصيل العملية إلى سطور مقروءة: «الحقل: القديم ← الجديد» أو «الحقل: القيمة»."""
    if not details:
        return []
    try:
        data = json.loads(details) if isinstance(details, str) else details
    except ValueError:
        return []
    out = []
    for key, v in data.items():
        label = _(FIELD_LABELS[key]) if key in FIELD_LABELS else key
        if isinstance(v, dict) and set(v) == {"from", "to"}:
            out.append(f"{label}: {_value(key, v['from'])} ← {_value(key, v['to'])}")
        else:
            out.append(f"{label}: {_value(key, v)}")
    return out
