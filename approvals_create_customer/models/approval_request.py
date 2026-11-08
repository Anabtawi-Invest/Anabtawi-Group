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
            if request.approval_type != "create_customer":
                continue
            if not (request.customer_name or "").strip():
                raise UserError(_("Please enter the customer name before submitting."))
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
            parent = self._portal_assigned_parent(request.request_owner_id)
            if not parent:
                raise UserError(
                    _("The requester has no assigned contact to attach the new customer under.")
                )
            # Keep partner in the request owner's company to avoid multi-company crossover
            # with the van user / approval request.
            company = (
                request.company_id
                or request.request_owner_id.company_id
                or parent.company_id
            )
            if parent.company_id and company and parent.company_id != company:
                raise UserError(
                    _(
                        "Assigned van customer %(parent)s belongs to %(parent_company)s, "
                        "but the request belongs to %(request_company)s. "
                        "Set the van customer on the portal user to a contact in the same company.",
                        parent=parent.display_name,
                        parent_company=parent.company_id.display_name,
                        request_company=company.display_name,
                    )
                )
            vals = {
                "name": name,
                "phone": (request.customer_phone or "").strip() or False,
                "email": (request.customer_email or "").strip() or False,
                "customer_rank": 1,
                "parent_id": parent.id,
                "type": "contact",
                "is_company": False,
                "company_id": company.id if company else False,
            }
            partner = Partner.with_company(company).create(vals) if company else Partner.create(vals)
            request.sudo().write(
                {
                    "created_partner_id": partner.id,
                    "partner_id": partner.id,
                }
            )
            request.message_post(
                body=_(
                    "Customer %(name)s has been created under %(parent)s.",
                    name=partner.display_name,
                    parent=parent.display_name,
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
