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
    def _must_require_contact_fields(self):
        self.ensure_one()
        return bool(self.x_is_contact_creation_category)

    def _get_request_attachments(self):
        """
        Robust attachment collector for Odoo 19:
        - Direct attachments on approval.request (res_model/res_id)
        - Chatter attachments stored on mail.message (message_ids.attachment_ids)
        """
        self.ensure_one()
        Attachment = self.env["ir.attachment"].sudo()

        direct = Attachment.search([
            ("res_model", "=", "approval.request"),
            ("res_id", "=", self.id),
        ])

        chatter = self.message_ids.mapped("attachment_ids").sudo()

        return (direct | chatter)

    def _count_attachments(self):
        self.ensure_one()
        return len(self._get_request_attachments())

    # -------------------------
    # Conditional required fields (OK on Save)
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
    # Submit/Approve validation (Attachments enforced here)
    # -------------------------
    def _validate_before_submit_or_approve(self):
        for rec in self:
            if not rec._must_require_contact_fields():
                continue
            if rec._count_attachments() < 1:
                raise ValidationError(_("At least one attachment is required before submitting/approving."))

    # -------------------------
    # Copy attachments to Contact (VISIBLE in Contact chatter)
    # -------------------------
    def _copy_attachments_to_partner_chatter(self, partner):
        """
        Copy attachments from approval request to partner AND post them in partner chatter.
        This guarantees they appear to users exactly like approval chatter attachments (thumbnail + download).
        """
        self.ensure_one()
        attachments = self._get_request_attachments()
        if not attachments:
            return

        new_attachment_ids = []
        for att in attachments:
            # Create a true copy (new ir.attachment record)
            new_att = att.copy()
            new_attachment_ids.append(new_att.id)

        # Post message on partner with those copied attachments
        partner.sudo().message_post(
            body=_("Attachments copied automatically from Approval Request: %s") % (self.display_name,),
            attachment_ids=new_attachment_ids,
        )

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

        # Copy attachments into partner chatter (guaranteed visible)
        self._copy_attachments_to_partner_chatter(partner)

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
    # -------------------------
    def action_confirm(self):
        for rec in self:
            if rec._must_require_contact_fields():
                rec._validate_before_submit_or_approve()
        return super().action_confirm()

    # -------------------------
    # Approve trigger
    # -------------------------
    def action_approve(self, approver=None):
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
