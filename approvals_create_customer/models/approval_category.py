# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ApprovalCategory(models.Model):
    _inherit = "approval.category"

    approval_type = fields.Selection(
        selection_add=[("create_customer", "Create Customer")],
        ondelete={"create_customer": "set null"},
    )

    @api.onchange("approval_type")
    def _onchange_approval_type_create_customer(self):
        if self.approval_type == "create_customer":
            self.has_partner = "no"
            self.has_product = "no"
            self.has_quantity = "no"
            self.has_amount = "no"
            self.has_date = "no"
            self.has_period = "no"
            self.has_location = "no"
            self.has_reference = "no"
            self.has_payment_method = "no"
            self.requirer_document = "required"

    @api.model
    def _create_customer_category_vals(self, company):
        """Defaults for a per-company Create Customer approval category."""
        vals = {
            "name": "Create Customer",
            "approval_type": "create_customer",
            "company_id": company.id,
            "sequence": 85,
            "description": "Request creation of a new customer contact",
            "has_date": "no",
            "has_period": "no",
            "has_product": "no",
            "has_quantity": "no",
            "has_amount": "no",
            "has_reference": "no",
            "has_partner": "no",
            "has_payment_method": "no",
            "has_location": "no",
            "requirer_document": "required",
            "approval_minimum": 1,
            "automated_sequence": True,
            "sequence_code": "APCUST",
            "active": True,
        }
        admin = self.env.ref("base.user_admin", raise_if_not_found=False)
        if admin:
            vals["approver_ids"] = [(0, 0, {"user_id": admin.id, "required": True})]
        return vals

    @api.model
    def _ensure_create_customer_categories(self, companies=None):
        """Create one Create Customer category per company when missing.

        Called on module install (post_init) and as a safety net when a portal
        user submits from a company that still has no category.
        """
        Company = self.env["res.company"].sudo()
        companies = companies if companies is not None else Company.search([])
        Category = self.sudo()
        created = Category.browse()
        for company in companies:
            existing = Category.search(
                [
                    ("approval_type", "=", "create_customer"),
                    ("company_id", "=", company.id),
                    ("active", "=", True),
                ],
                limit=1,
            )
            if existing:
                category = existing
            else:
                category = Category.create(self._create_customer_category_vals(company))
                created |= category
            if (
                "x_create_contact_on_approve" in category._fields
                and category.x_create_contact_on_approve
            ):
                category.x_create_contact_on_approve = False
        return created
