# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import ValidationError


class ApprovalRequest(models.Model):
    _inherit = "approval.request"

    # =========================
    # Fields (Approval Request)
    # =========================
    x_contact_type = fields.Selection(
        [("person", "Individual"), ("company", "Company")],
        string="Contact Type",
        required=True,
        default="person",
    )
    x_contact_name = fields.Char(string="New Contact Name", required=True)
    x_contact_phone = fields.Char(string="Phone", required=True)
    x_contact_email = fields.Char(string="Email")  # optional
    x_contact_vat = fields.Char(string="Tax ID (VAT)", required=True)

    # One contact per request
    x_created_partner_id = fields.Many2one(
        "res.partner",
        string="Created Contact",
        readonly=True,
        copy=False,
    )

    # =========================
    # Helpers
    # =========================
    def _is_contact_creation_category(self):
        """Run logic only for categories where checkbox is enabled."""
        self.ensure_one()
        return bool(self.category_id and self.category_id.x_create_contact_on_approve)

    def _count_attachments(self):
        """Count attachments linked to this approval.request record."""
        self.ensure_one()
        return self.env["ir.attachment"].sudo().search_count([
            ("res_model", "=", "approval.request"),
            ("res_id", "=", self.id),
        ])

    def _validate_before_approved(self):
        """
        Strict validation (no assumptions):
        - name required
        - phone required
        - VAT required
        - contact type required
        - at least 1 attachment required
        """
        for rec in self:
            if not rec._is_contact_creation_category():
                continue

            if not rec.x_contact_name:
                raise ValidationError(_("New Contact Name is mandatory."))
            if not rec.x_contact_phone:
                raise ValidationError(_("Phone is mandatory."))
            if not rec.x_contact_vat:
                raise ValidationError(_("Tax ID (VAT) is mandatory."))
            if not rec.x_contact_type:
                raise ValidationError(_("Contact Type (Individual/Company) is mandatory."))

            if rec._count_attachments() < 1:
                raise ValidationError(_("At least one attachment is required before approval."))

    def _create_contact_sudo_once(self):
        """
        Always create a NEW contact (even if duplicate exists),
        but create only ONCE per approval request.
        """
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
            "x_approval_request_id": self.id,  # link back to approval on partner
        })

        self.x_created_partner_id = partner.id
        return partner

    def _post_approval_create_contact_if_needed(self):
        """
        Single place to create contact after request is fully approved.
        This is called from action_approve (main) and write() (fallback).
        """
        for rec in self:
            if not rec._is_contact_creation_category():
                continue
            if rec.request_status != "approved":
                continue

            rec._validate_before_approved()
            rec._create_contact_sudo_once()

    # =========================
    # Main trigger: Approve button
    # =========================
    def action_approve(self, approver=None):
        """
        Strong trigger for approvals in Odoo:
        After super(), if request_status is now 'approved' => create contact.
        """
        res = super().action_approve(approver=approver)
        self._post_approval_create_contact_if_needed()
        return res

    # =========================
    # Fallback trigger: status changed by other flows
    # =========================
    def write(self, vals):
        """
        Fallback: if something sets request_status to approved directly,
        we still create the contact.
        """
        going_approved = ("request_status" in vals and vals["request_status"] == "approved")

        # validate BEFORE moving to approved
        if going_approved:
            self._validate_before_approved()

        res = super().write(vals)

        # create AFTER the record becomes approved
        if going_approved:
            self._post_approval_create_contact_if_needed()

        return res

    # =========================
    # Smart button to open created contact
    # =========================
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
