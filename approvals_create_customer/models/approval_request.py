# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ApprovalRequest(models.Model):
    _inherit = "approval.request"

    customer_name = fields.Char(string="Customer Name")
    customer_phone = fields.Char(string="Customer Phone")
    customer_email = fields.Char(string="Customer Email")
    customer_portal_allow_payment_term = fields.Boolean(
        string="Allow Payment Term",
        default=True,
        help="Credit customer requests always allow payment terms. "
        "Created partner is standalone with Salesperson = van portal user.",
    )
    customer_payment_term_id = fields.Many2one(
        "account.payment.term",
        string="Default Payment Term",
        help="Default payment term written on the credit customer.",
    )
    created_partner_id = fields.Many2one(
        "res.partner",
        string="Created Customer",
        readonly=True,
        copy=False,
    )

    @api.constrains(
        "approval_type",
        "customer_name",
        "customer_portal_allow_payment_term",
        "customer_payment_term_id",
        "request_status",
    )
    def _check_create_customer_fields(self):
        for request in self:
            if request.approval_type != "create_customer":
                continue
            if request.request_status in ("pending", "approved") and not (request.customer_name or "").strip():
                raise ValidationError(_("Customer Name is required for Create Customer requests."))
            if request.request_status in ("pending", "approved") and not request.customer_payment_term_id:
                raise ValidationError(
                    _("Default Payment Term is required for credit customer requests.")
                )

    def action_confirm(self):
        for request in self:
            if request.approval_type != "create_customer":
                continue
            if not (request.customer_name or "").strip():
                raise UserError(_("Please enter the customer name before submitting."))
            if not request.customer_payment_term_id:
                raise UserError(_("Please set a Default Payment Term before submitting."))
            # Count via sudo search — more reliable than attachment_number for portal/sudo flows.
            attachment_count = (
                self.env["ir.attachment"]
                .sudo()
                .search_count(
                    [
                        ("res_model", "=", "approval.request"),
                        ("res_id", "=", request.id),
                        ("res_field", "=", False),
                    ]
                )
            )
            if not attachment_count:
                raise UserError(
                    _("Please attach at least one Commercial Register (السجل التجاري) document.")
                )
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

    def _portal_assigned_parent(self, owner):
        """Parent contact for customers created from this portal user's requests."""
        owner = owner.sudo()
        if "van_customer_id" in owner._fields and owner.van_customer_id:
            return owner.van_customer_id
        return owner.partner_id

    def _create_customer_partner(self):
        Partner = self.env["res.partner"].sudo()
        for request in self:
            name = (request.customer_name or "").strip()
            if not name:
                raise UserError(_("Customer Name is required to create the partner."))
            if not request.customer_payment_term_id:
                raise UserError(_("Default Payment Term is required to create the credit customer."))
            owner = request.request_owner_id.sudo()
            company = request.company_id or owner.company_id
            if not company:
                raise UserError(_("The requester has no company; cannot create the customer."))
            vals = {
                "name": name,
                "phone": (request.customer_phone or "").strip() or False,
                "email": (request.customer_email or "").strip() or False,
                "customer_rank": 1,
                "parent_id": False,
                "type": "contact",
                "is_company": True,
                "company_id": company.id,
                "user_id": owner.id,
                "portal_allow_payment_term": True,
                "property_payment_term_id": request.customer_payment_term_id.id,
            }
            partner = Partner.with_company(company).create(vals)
            request.sudo().write(
                {
                    "created_partner_id": partner.id,
                    "partner_id": partner.id,
                    "customer_portal_allow_payment_term": True,
                }
            )
            request.message_post(
                body=_(
                    "Credit customer %(name)s has been created with salesperson %(user)s.",
                    name=partner.display_name,
                    user=owner.display_name,
                )
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
