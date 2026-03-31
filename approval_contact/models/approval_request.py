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

    def _get_direct_attachments(self):
        """Attachments directly linked to approval.request (res_model/res_id)."""
        self.ensure_one()
        return self.env["ir.attachment"].sudo().search([
            ("res_model", "=", "approval.request"),
            ("res_id", "=", self.id),
        ])

    def _get_chatter_attachments(self):
        """Attachments linked to chatter messages (mail.message)."""
        self.ensure_one()
        return self.message_ids.mapped("attachment_ids").sudo()

    def _get_all_request_attachments(self):
        """Union of direct + chatter attachments."""
        self.ensure_one()
        return (self._get_direct_attachments() | self._get_chatter_attachments())

    def _count_attachments(self):
        self.ensure_one()
        return len(self._get_all_request_attachments())

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
    # MOVE attachments to Contact (NO duplicates)
    # -------------------------
    def _move_attachments_to_partner(self, partner):
        """
        Move (not copy) attachments from approval.request to res.partner:
        - Remove attachments from approval chatter messages (so they disappear from approval)
        - Re-link the same ir.attachment to partner (res_model/res_id)
        - Post them into partner chatter (without copying) so user sees them on contact
        """
        self.ensure_one()
        Attachment = self.env["ir.attachment"].sudo()

        # 1) Collect attachments
        direct_attachments = self._get_direct_attachments()
        chatter_attachments = self._get_chatter_attachments()
        all_attachments = (direct_attachments | chatter_attachments)

        if not all_attachments:
            return

        # 2) Detach chatter attachments from approval messages (remove relation)
        # This ensures they won't still appear in the approval chatter after move.
        if chatter_attachments:
            for msg in self.message_ids.sudo():
                if msg.attachment_ids:
                    # remove only the ones we are moving
                    to_remove = msg.attachment_ids & chatter_attachments
                    if to_remove:
                        msg.write({"attachment_ids": [(3, att_id) for att_id in to_remove.ids]})

        # 3) Re-link attachments to partner (MOVE)
        all_attachments.write({
            "res_model": "res.partner",
            "res_id": partner.id,
        })

        # 4) Post a message on partner chatter with the SAME attachments (no copy)
        partner.sudo().message_post(
            body=_("Documents moved automatically from Approval Request: %s") % (self.display_name,),
            attachment_ids=all_attachments.ids,
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

        # ✅ MOVE attachments (no duplicates)
        self._move_attachments_to_partner(partner)

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
