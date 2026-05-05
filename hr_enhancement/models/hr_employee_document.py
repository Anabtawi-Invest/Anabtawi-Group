# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import _, api, fields, models

AE_DOCUMENT_SPECS = [
    ("National ID Copy", None, "ae_doc_id_expiry", "ae_doc_id_expiry_notify"),
    ("Driving license", None, "ae_doc_driving_license_expiry", "ae_doc_driving_license_expiry_notify"),
    ("Health certificate", "ae_doc_health_certificate", "ae_doc_health_certificate_expiry", "ae_doc_health_certificate_notify"),
    ("Non-conviction certificate", "ae_doc_non_conviction", "ae_doc_non_conviction_expiry", "ae_doc_non_conviction_notify"),
    ("Probation period completion", "ae_doc_probation_end", "ae_doc_probation_end_expiry", "ae_doc_probation_end_notify"),
    ("Children card (Gaza Strip)", "ae_doc_children_gaza", "ae_doc_children_gaza_expiry", "ae_doc_children_gaza_notify"),
    ("Children card (Jordanian mother)", "ae_doc_children_jordanian_mother", "ae_doc_children_jordanian_mother_expiry", "ae_doc_children_jordanian_mother_notify"),
    ("Work permit", "ae_doc_work_permit", "ae_doc_work_permit_expiry", "ae_doc_work_permit_notify"),
    ("Passport copy", "ae_doc_passport", "ae_doc_passport_expiry", "ae_doc_passport_notify"),
    ("Family book", "ae_doc_family_book", "ae_doc_family_book_expiry", "ae_doc_family_book_notify"),
    ("General permit", "ae_doc_permit_general", "ae_doc_permit_general_expiry", "ae_doc_permit_general_notify"),
    ("Engineers syndicate membership", "ae_doc_engineers_syndicate", "ae_doc_engineers_syndicate_expiry", "ae_doc_engineers_syndicate_notify"),
]


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    ae_doc_id_expiry = fields.Date(groups="hr.group_hr_user", string="National ID expiry")
    ae_doc_driving_license_expiry = fields.Date(groups="hr.group_hr_user", string="Driving license expiry")

    ae_doc_health_certificate = fields.Binary(groups="hr.group_hr_user", string="Health certificate")
    ae_doc_health_certificate_filename = fields.Char(groups="hr.group_hr_user")
    ae_doc_health_certificate_expiry = fields.Date(groups="hr.group_hr_user")

    ae_doc_non_conviction = fields.Binary(groups="hr.group_hr_user", string="Non-conviction certificate")
    ae_doc_non_conviction_filename = fields.Char(groups="hr.group_hr_user")
    ae_doc_non_conviction_expiry = fields.Date(groups="hr.group_hr_user")

    ae_doc_probation_end = fields.Binary(groups="hr.group_hr_user", string="Probation period completion")
    ae_doc_probation_end_filename = fields.Char(groups="hr.group_hr_user")
    ae_doc_probation_end_expiry = fields.Date(groups="hr.group_hr_user")

    ae_doc_children_gaza = fields.Binary(groups="hr.group_hr_user", string="Children card (Gaza Strip)")
    ae_doc_children_gaza_filename = fields.Char(groups="hr.group_hr_user")
    ae_doc_children_gaza_expiry = fields.Date(groups="hr.group_hr_user")

    ae_doc_children_jordanian_mother = fields.Binary(groups="hr.group_hr_user", string="Children card (Jordanian mother)")
    ae_doc_children_jordanian_mother_filename = fields.Char(groups="hr.group_hr_user")
    ae_doc_children_jordanian_mother_expiry = fields.Date(groups="hr.group_hr_user")

    ae_doc_work_permit = fields.Binary(groups="hr.group_hr_user", string="Work permit")
    ae_doc_work_permit_filename = fields.Char(groups="hr.group_hr_user")
    ae_doc_work_permit_expiry = fields.Date(groups="hr.group_hr_user")

    ae_doc_passport = fields.Binary(groups="hr.group_hr_user", string="Passport copy")
    ae_doc_passport_filename = fields.Char(groups="hr.group_hr_user")
    ae_doc_passport_expiry = fields.Date(groups="hr.group_hr_user")

    ae_doc_family_book = fields.Binary(groups="hr.group_hr_user", string="Family book")
    ae_doc_family_book_filename = fields.Char(groups="hr.group_hr_user")
    ae_doc_family_book_expiry = fields.Date(groups="hr.group_hr_user")

    ae_doc_permit_general = fields.Binary(groups="hr.group_hr_user", string="General permit")
    ae_doc_permit_general_filename = fields.Char(groups="hr.group_hr_user")
    ae_doc_permit_general_expiry = fields.Date(groups="hr.group_hr_user")

    ae_doc_engineers_syndicate = fields.Binary(groups="hr.group_hr_user", string="Engineers syndicate membership")
    ae_doc_engineers_syndicate_filename = fields.Char(groups="hr.group_hr_user")
    ae_doc_engineers_syndicate_expiry = fields.Date(groups="hr.group_hr_user")

    # Notify stage: 0 = none; 1 = soon (within window); 2 = overdue
    ae_doc_id_expiry_notify = fields.Integer(groups="hr.group_hr_user", default=0, copy=False)
    ae_doc_driving_license_expiry_notify = fields.Integer(groups="hr.group_hr_user", default=0, copy=False)
    ae_doc_health_certificate_notify = fields.Integer(groups="hr.group_hr_user", default=0, copy=False)
    ae_doc_non_conviction_notify = fields.Integer(groups="hr.group_hr_user", default=0, copy=False)
    ae_doc_probation_end_notify = fields.Integer(groups="hr.group_hr_user", default=0, copy=False)
    ae_doc_children_gaza_notify = fields.Integer(groups="hr.group_hr_user", default=0, copy=False)
    ae_doc_children_jordanian_mother_notify = fields.Integer(groups="hr.group_hr_user", default=0, copy=False)
    ae_doc_work_permit_notify = fields.Integer(groups="hr.group_hr_user", default=0, copy=False)
    ae_doc_passport_notify = fields.Integer(groups="hr.group_hr_user", default=0, copy=False)
    ae_doc_family_book_notify = fields.Integer(groups="hr.group_hr_user", default=0, copy=False)
    ae_doc_permit_general_notify = fields.Integer(groups="hr.group_hr_user", default=0, copy=False)
    ae_doc_engineers_syndicate_notify = fields.Integer(groups="hr.group_hr_user", default=0, copy=False)

    @api.model
    def _ae_doc_expiry_field_to_notify_field(self):
        return {spec[2]: spec[3] for spec in AE_DOCUMENT_SPECS}

    def write(self, vals):
        vals = dict(vals or {})
        mapping = self._ae_doc_expiry_field_to_notify_field()
        for exp_field, notif_field in mapping.items():
            if exp_field in vals:
                vals[notif_field] = 0
        return super().write(vals)

    def _ae_manager_users(self):
        self.ensure_one()
        users = self.env["res.users"]
        if self.parent_id and self.parent_id.user_id:
            users |= self.parent_id.user_id
        dm = self.department_id.manager_id if self.department_id else False
        if dm and dm.user_id:
            users |= dm.user_id
        return users

    def _ae_doc_build_pending_notices(self, today, warn_days=30):
        self.ensure_one()
        pending = []
        for label, binary_field, exp_field, notif_field in AE_DOCUMENT_SPECS:
            exp_date = self[exp_field]
            if not exp_date:
                continue
            stage = self[notif_field] or 0
            if today > exp_date:
                if stage < 2:
                    pending.append(
                        {
                            "label": _(label),
                            "expiry": exp_date,
                            "kind": "expired",
                            "notif_field": notif_field,
                            "target_stage": 2,
                        }
                    )
            elif today >= exp_date - timedelta(days=warn_days):
                if stage < 1:
                    pending.append(
                        {
                            "label": _(label),
                            "expiry": exp_date,
                            "kind": "soon",
                            "notif_field": notif_field,
                            "target_stage": 1,
                        }
                    )
        return pending

    def _ae_send_manager_document_notices(self, items):
        self.ensure_one()
        if not items:
            return
        managers = self._ae_manager_users()
        min_expiry = min(i["expiry"] for i in items)

        body_lines = []
        for it in items:
            if it["kind"] == "expired":
                body_lines.append(
                    _("%s — expired on %s") % (it["label"], it["expiry"]),
                )
            else:
                body_lines.append(
                    _("%s — expires on %s") % (it["label"], it["expiry"]),
                )
        note_body = "<ul>%s</ul>" % "".join("<li>%s</li>" % line for line in body_lines)
        note_body = "<p><b>%s</b></p>%s" % (_("Employee: %s") % (self.name or ""), note_body)

        if managers:
            has_expired = any(i["kind"] == "expired" for i in items)
            summary = (
                _("Employee document(s) expired or past due")
                if has_expired
                else _("Employee document(s) expiring soon")
            )
            for user in managers:
                self.activity_schedule(
                    "mail.mail_activity_data_todo",
                    date_deadline=min_expiry,
                    summary=summary,
                    note=note_body,
                    user_id=user.id,
                )

        Mail = self.env["mail.mail"].sudo()
        emails = []
        for u in managers:
            addr = u.partner_id.email_normalized
            if addr:
                emails.append(addr)
        if not emails:
            group = self.env.ref("hr.group_hr_manager", raise_if_not_found=False)
            if group:
                emails = sorted({
                    u.partner_id.email_normalized
                    for u in group.users
                    if u.partner_id.email_normalized
                })

        if emails:
            Mail.create(
                {
                    "subject": _("[%s] Employee documents require attention") % (self.name or self.id),
                    "body_html": "<div>%s</div>" % note_body,
                    "email_to": ",".join(emails),
                    "auto_delete": True,
                }
            ).send()

        write_vals = {}
        for it in items:
            cur = self[it["notif_field"]] or 0
            write_vals[it["notif_field"]] = max(cur, it["target_stage"])
        self.write(write_vals)

    @api.model
    def _cron_ae_notify_employee_document_expiries(self):
        today = fields.Date.context_today(self)
        for emp in self.sudo().search([("active", "=", True)]):
            pending = emp._ae_doc_build_pending_notices(today)
            if pending:
                emp._ae_send_manager_document_notices(pending)
