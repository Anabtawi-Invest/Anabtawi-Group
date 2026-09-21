# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ApprovalRequest(models.Model):
    _inherit = "approval.request"

    customer_name = fields.Char(string="Customer Name")
    customer_phone = fields.Char(string="Customer Phone")
    customer_email = fields.Char(string="Customer Email")
    created_partner_id = fields.Many2one(
        "res.partner",
        string="Created Customer",
        readonly=True,
        copy=False,
    )

    @api.constrains("approval_type", "customer_name", "request_status")
    def _check_create_customer_fields(self):
        for request in self:
            if request.approval_type != "create_customer":
                continue
            if request.request_status in ("pending", "approved") and not (request.customer_name or "").strip():
                raise ValidationError(_("Customer Name is required for Create Customer requests."))

    def action_confirm(self):
        for request in self:
            if request.approval_type == "create_customer" and not (request.customer_name or "").strip():
                raise UserError(_("Please enter the customer name before submitting."))
        return super().action_confirm()

    def action_approve(self, approver=None):
        res = super().action_approve(approver)
        self._create_customer_partner_if_approved()
        return res

    def _action_force_approval(self):
        res = super()._action_force_approval()
        self._create_customer_partner_if_approved()
        return res

    def _create_customer_partner_if_approved(self):
        self.invalidate_recordset(["request_status"])
        to_create = self.filtered(
            lambda r: r.approval_type == "create_customer"
            and r.request_status == "approved"
            and not r.created_partner_id
        )
        to_create._create_customer_partner()

    def _create_customer_partner(self):
        Partner = self.env["res.partner"].sudo()
        for request in self:
            name = (request.customer_name or "").strip()
            if not name:
                raise UserError(_("Customer Name is required to create the partner."))
            partner = Partner.create(
                {
                    "name": name,
                    "phone": (request.customer_phone or "").strip() or False,
                    "email": (request.customer_email or "").strip() or False,
                    "customer_rank": 1,
                    "company_id": request.company_id.id or False,
                }
            )
            request.sudo().write(
                {
                    "created_partner_id": partner.id,
                    "partner_id": partner.id,
                }
            )
            request.message_post(
                body=_("Customer %(name)s has been created.", name=partner.display_name)
            )

    def action_open_created_partner(self):
        self.ensure_one()
        if not self.created_partner_id:
            raise UserError(_("No customer has been created for this request yet."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Customer"),
            "res_model": "res.partner",
            "view_mode": "form",
            "res_id": self.created_partner_id.id,
            "target": "current",
        }
