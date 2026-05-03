# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


def _normalized_employee_name(name):
    if not name or not isinstance(name, str):
        return ""
    return " ".join(name.split())


_EXPIRY_FLAGS = {
    "id_card_expiry_date": "id_card_expiry_mail_sent",
    "driving_license_expiry_date": "driving_license_expiry_mail_sent",
    "sim_card_copy_expiry_date": "sim_card_copy_expiry_mail_sent",
    "internet_subscription_invoice_expiry_date": "internet_subscription_invoice_expiry_mail_sent",
}

# (label for email, expiry field, mail_sent field)
_EXPIRY_DOC_ROWS = (
    ("ID Card Copy", "id_card_expiry_date", "id_card_expiry_mail_sent"),
    ("Driving License", "driving_license_expiry_date", "driving_license_expiry_mail_sent"),
    ("SIM Card Copy", "sim_card_copy_expiry_date", "sim_card_copy_expiry_mail_sent"),
    ("Internet Subscription Invoice", "internet_subscription_invoice_expiry_date", "internet_subscription_invoice_expiry_mail_sent"),
)


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # Document binaries: id_card / driving_license (hr); sim_card / internet_invoice (hr_payroll, BE salary UI).

    id_card_expiry_date = fields.Date(
        string="ID Card Expiry",
        groups="hr.group_hr_user",
    )
    driving_license_expiry_date = fields.Date(
        string="Driving License Expiry",
        groups="hr.group_hr_user",
    )
    sim_card_copy_expiry_date = fields.Date(
        string="SIM Card Expiry",
        groups="hr.group_hr_user",
    )
    internet_subscription_invoice_expiry_date = fields.Date(
        string="Internet Invoice Expiry",
        groups="hr.group_hr_user",
    )

    id_card_expiry_mail_sent = fields.Boolean(
        groups="hr.group_hr_user",
        default=False,
        copy=False,
        help="Technical: HR was notified for current ID card expiry.",
    )
    driving_license_expiry_mail_sent = fields.Boolean(
        groups="hr.group_hr_user",
        default=False,
        copy=False,
    )
    sim_card_copy_expiry_mail_sent = fields.Boolean(
        groups="hr.group_hr_user",
        default=False,
        copy=False,
    )
    internet_subscription_invoice_expiry_mail_sent = fields.Boolean(
        groups="hr.group_hr_user",
        default=False,
        copy=False,
    )

    @api.constrains("name", "company_id")
    def _check_unique_employee_name(self):
        for emp in self:
            normalized = _normalized_employee_name(emp.name)
            if not normalized:
                continue
            dup = self.search(
                [
                    ("id", "!=", emp.id),
                    ("company_id", "=", emp.company_id.id),
                    ("name", "=ilike", normalized),
                    ("active", "=", True),
                ],
                limit=1,
            )
            if dup:
                raise ValidationError(
                    _('An employee named "%s" already exists in this company (%s).')
                    % (normalized, dup.display_name)
                )

    @api.constrains("identification_id", "company_id")
    def _check_unique_identification_id(self):
        for emp in self:
            nid = (emp.identification_id or "").strip()
            if not nid:
                continue
            dup = self.search(
                [
                    ("id", "!=", emp.id),
                    ("company_id", "=", emp.company_id.id),
                    ("identification_id", "=ilike", nid),
                ],
                limit=1,
            )
            if dup:
                raise ValidationError(
                    _('Identification number "%s" is already assigned to employee %s in this company.')
                    % (nid, dup.display_name)
                )

    def write(self, vals):
        vals = dict(vals or {})
        for exp_field, sent_field in _EXPIRY_FLAGS.items():
            if exp_field in vals:
                vals[sent_field] = False
        return super().write(vals)

    def _pending_expired_documents_for_cron(self, today):
        """Return list of (label, expiry_date, sent_field_name) overdue and not yet mailed."""
        self.ensure_one()
        out = []
        for label, exp_fname, sent_fname in _EXPIRY_DOC_ROWS:
            due = self[exp_fname]
            if due and due <= today and not self[sent_fname]:
                out.append((label, due, sent_fname))
        return out

    def _send_document_expiry_mail_to_hr(self, items):
        """items: list of (label, expiry_date, sent_field_name)."""
        self.ensure_one()
        if not items:
            return
        Mail = self.env["mail.mail"].sudo()
        group = self.env.ref("hr.group_hr_manager", raise_if_not_found=False)
        if not group:
            return
        emails_list = group.users.filtered(lambda u: bool(u.email)).mapped("email")
        emails = ",".join(emails_list)
        if not emails:
            return

        rows_html = "".join(
            "<li><b>%s:</b> %s</li>"
            % (
                label,
                fields.Date.to_string(ed) if ed else "",
            )
            for label, ed, _sent in items
        )
        body_html = (
            "<p>%s</p><ul>%s</ul>"
            % (
                self.env._("The following employee documents are at or past expiry."),
                rows_html,
            )
        )
        employee_name = self.name or self.env._("(no name)")
        subject = self.env._("[%s] Employee documents expired") % employee_name
        Mail.create(
            {
                "subject": subject,
                "body_html": "<div>%s</div>"
                % (
                    body_html
                    + "<p><b>%s</b> %s</p>"
                    % (
                        self.env._("Employee:"),
                        employee_name,
                    )
                ),
                "email_to": emails,
                "auto_delete": True,
            }
        ).send()
        write_vals = {fname: True for _l, _d, fname in items}
        self.write(write_vals)

    @api.model
    def _cron_notify_document_expiry_to_hr(self):
        """Daily: one email per employee listing documents past expiry (not yet notified per flag)."""
        today = fields.Date.context_today(self)
        for emp in self.sudo().search([]):
            pending = emp._pending_expired_documents_for_cron(today)
            if pending:
                emp._send_document_expiry_mail_to_hr(pending)
