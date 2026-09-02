# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PosAdvanceOrderEmployeePricelistWizard(models.TransientModel):
    _name = "pos.advance.order.employee_pricelist.wizard"
    _description = "POS Advance Order - Employee Pricelist Authorization"

    advance_order_id = fields.Many2one(
        "pos.advance.order",
        string="Advance Order",
        required=True,
        ondelete="cascade",
    )
    pos_config_id = fields.Many2one(
        "pos.config",
        string="Picking POS",
        related="advance_order_id.pos_config_id",
        readonly=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        related="advance_order_id.partner_id",
        readonly=True,
    )
    employee_pricelist_id = fields.Many2one(
        "product.pricelist",
        string="Employee Pricelist",
        compute="_compute_employee_pricelist_id",
        readonly=True,
    )

    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee",
        compute="_compute_employee_id",
        readonly=True,
    )
    password = fields.Char(string="Password", required=True)

    @api.depends("advance_order_id.pos_config_id")
    def _compute_employee_pricelist_id(self):
        for wiz in self:
            # employee_pricelist_id is defined by the employee_request module on pos.config
            wiz.employee_pricelist_id = getattr(wiz.pos_config_id, "employee_pricelist_id", False)

    @api.depends("partner_id", "advance_order_id.company_id")
    def _compute_employee_id(self):
        for wiz in self:
            wiz.employee_id = False
            partner = wiz.partner_id
            if not partner:
                continue

            domain = [("active", "=", True)]
            company = wiz.advance_order_id.company_id
            if company:
                domain += ["|", ("company_id", "=", False), ("company_id", "=", company.id)]

            employee_model = self.env["hr.employee"]

            employee = False
            # Preferred mapping: employee.work_contact_id == partner (field exists in your HR version)
            if "work_contact_id" in employee_model._fields:
                employee = employee_model.sudo().search(domain + [("work_contact_id", "=", partner.id)], limit=1)

            # Alternate mapping: employee.user_id.partner_id == partner (if employee has a linked user)
            if not employee and "user_id" in employee_model._fields:
                employee = employee_model.sudo().search(domain + [("user_id.partner_id", "=", partner.id)], limit=1)

            if not employee and partner.name:
                # Fallback mapping: same name (best effort)
                employee = employee_model.sudo().search(domain + [("name", "=", partner.name)], limit=1)

            wiz.employee_id = employee

    def action_apply(self):
        self.ensure_one()
        order = self.advance_order_id
        if not order:
            raise UserError(_("Advance Order not found."))
        if order.state != "draft":
            raise UserError(_("You can only apply employee pricelist on a Draft advance order."))

        employee_pricelist = self.employee_pricelist_id
        if not employee_pricelist:
            raise UserError(_("No Employee Pricelist is configured on the selected Picking POS."))

        if not self.employee_id:
            raise UserError(
                _(
                    "No employee record was found for this customer. "
                    "Please link the employee to the customer (Work Contact or linked User) or ensure names match."
                )
            )

        # Validate password with the same helper used by the POS flow (employee_request module)
        is_valid = self.env["hr.employee"].pos_employee_request_check_password(self.employee_id.id, self.password)
        if not is_valid:
            raise UserError(_("Employee name and password do not match."))

        # Mark authorization first, then reprice using the order's shared pricing helper.
        # We intentionally do NOT store the password anywhere.
        order.write({
            "is_employee_pricelist": True,
            "employee_pricelist_employee_id": self.employee_id.id,
        })
        order._apply_pricelist_to_lines(employee_pricelist)

        return {"type": "ir.actions.act_window_close"}

