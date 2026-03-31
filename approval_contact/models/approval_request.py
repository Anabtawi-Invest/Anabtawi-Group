# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ApprovalRequest(models.Model):
    _inherit = "approval.request"

    # Safe boolean (stored) for logic + UI
    x_is_contact_creation_category = fields.Boolean(
        string="Is Contact Creation Category",
        related="category_id.x_create_contact_on_approve",
        store=True,
        readonly=True,
    )

    # Fields (NOT required=True at model level)
    x_contact_type = fields.Selection(
        [("person", "Individual"), ("company", "Company")],
        string="Contact Type",
        default="person",
    )
    x_contact_name = fields.Char(string="New Contact Name")
    x_contact_phone = fields.Char(string="Phone")
    x_contact_email = fields.Char(string="Email")  # optional
    x_contact_vat = fields.Char(string="Tax ID (VAT)")

    x_created_partner_id = fields.Many2one(
        "res.partner",
        string="Created Contact",
        readonly=True,
        copy=False,
    )

    # -------------------------
    # Helpers
    # -------------------------
    def _count_attachments(self):
        self.ensure_one()
        return self.env["ir.attachment"].sudo().search_count([
            ("res_model", "=", "approval.request"),
            ("res_id", "=", self.id),
        ])

    def _must_require_contact_fields(self):
        self.ensure_one()
        return bool(self.x_is_contact_creation_category)

    # -------------------------
    # CONDITIONAL REQUIRED FIELDS (OK on Save)
    # NOTE: This constraint will run on save, but it checks only fields,
    # NOT attachments, so user can save then add attachment.
    # -------------------------
    @api.constrains("x_is_contact_creation_category", "x_contact_type", "x_contact_name", "x_contact_phone", "x_contact_vat")
    def _constrains_contact_fields_when_enabled(self):
        for rec in self:
            if not rec._must_require_contact_fields():
                continue

            missing = []
            if not rec.x_contact_type:
                missing.append(_("Contact Type"))
            if not rec.x_contact_name:
                missing.append(_("New Contact Name"))
            if not rec.x_contact_phone:
                missing.append(_("Phone"))
            if not rec.x_contact_vat:
                missing.append(_("Tax ID (VAT)"))

            if missing:
                raise ValidationError(
                    _("Missing mandatory fields for this Approval Category:\n- %s") % "\n- ".join(missing)
                )

    # -------------------------
    # Submission/Approval validation (Attachments enforced here)
    # -------------------------
    def _validate_before_submit_or_approve(self):
        """
        Enforce attachments ONLY at submit/approve time (NOT at save).
        This matches Odoo logic: save first, then attach, then submit/approve.
        """
        for rec in self:
            if not rec._must_require_contact_fields():
                continue

            # Attachments required here
            if rec._count_attachments() < 1:
                raise ValidationError(_("At least one attachment is required before submitting/approving."))

    # -------------------------
    # Contact creation logic (on Approved)
    # -------------------------
    def _create_contact_sudo_once(self):
        self.ensure_one()
        if self.x_created_partner_id:
            return self.x_created_partner_id

        Partner = self.env["res.partner"].sudo()
        company_type = "company" if self.x_contact_type == "company" else "person"

        partner = Partner.create({
            "name": (self.x_contact_name or "").strip(),
            "phone": (self.x_contact_phone or "").strip(),
            "email": (self.x_contact_email or "").strip() or False,
            "vat": (self.x_contact_vat or "").strip(),
            "company_type": company_type,
            "x_approval_request_id": self.id,
        })
        self.x_created_partner_id = partner.id
        return partner

    def _post_approval_create_contact_if_needed(self):
        for rec in self:
            if not rec._must_require_contact_fields():
                continue
            if rec.request_status != "approved":
                continue
            rec._create_contact_sudo_once()

    # -------------------------
    # Submit trigger (Pending)
    # Odoo approvals usually has action_confirm to submit
    # -------------------------
    def action_confirm(self):
        """
        Allow save without attachment, but block submit if attachment missing.
        """
        for rec in self:
            if rec._must_require_contact_fields():
                rec._validate_before_submit_or_approve()
        return super().action_confirm()

    # -------------------------
    # Approve trigger
    # -------------------------
    def action_approve(self, approver=None):
        """
        Block approve if no attachment, then proceed.
        After approve, if request_status becomes 'approved' -> create contact.
        """
        for rec in self:
            if rec._must_require_contact_fields():
                rec._validate_before_submit_or_approve()

        res = super().action_approve(approver=approver)
        self._post_approval_create_contact_if_needed()
        return res

    # Fallback: if request_status set to approved by another flow
    def write(self, vals):
        going_approved = ("request_status" in vals and vals["request_status"] == "approved")
        res = super().write(vals)
        if going_approved:
            # At this point, ensure attachments exist for enabled category
            for rec in self:
                if rec._must_require_contact_fields():
                    rec._validate_before_submit_or_approve()
            self._post_approval_create_contact_if_needed()
        return res

    def action_open_created_contact(self):
        self.ensure_one()
        if not self.x_created_partner_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "name": _("Created Contact"),
            "res_model": "res.partner",
            "view_mode": "form",
            "res_id": self.x_created_partner_id.id,
            "target": "current",
        }
