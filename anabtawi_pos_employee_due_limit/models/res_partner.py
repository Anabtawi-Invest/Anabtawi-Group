# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.tools import float_compare
from odoo.tools.misc import formatLang


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _get_due_limit_employee(self, company):
        self.ensure_one()
        partners = self | self.commercial_partner_id
        employees = self.env["hr.employee"].sudo().search([("work_contact_id", "in", partners.ids)])
        return employees.filtered(lambda e: e.company_id == company)[:1] or employees[:1]

    def _get_employee_due_limit_status(self, config, amount, exclude_order=None):
        """Check whether adding `amount` on Customer Account keeps the employee under his limit.

        Amounts are in the POS currency. Partners that are not employees are never blocked.
        `exclude_order` is the order being checked when it is already saved as paid, so its
        Customer Account payments are not counted twice in the current due.
        """
        self.ensure_one()
        status = {"blocked": False, "message": ""}
        employee = self._get_due_limit_employee(config.company_id)
        if not employee or not employee.company_id.employee_due_limit_enabled:
            return status

        currency = config.currency_id
        if not employee._get_employee_due_wage():
            status.update(
                blocked=True,
                message=_(
                    "Employee %(employee)s has no wage set, so he cannot buy on Customer Account.",
                    employee=employee.name,
                ),
            )
            return status

        employee_currency = employee.company_id.currency_id
        limit = employee._get_employee_due_limit()
        if employee_currency != currency:
            limit = employee_currency._convert(limit, currency, config.company_id, fields.Date.today())
        due = self.sudo().get_total_due(config.id)["res.partner"][0]["total_due"]
        if exclude_order and exclude_order.state == "paid" and exclude_order.session_id.state != "closed":
            due -= sum(
                exclude_order.payment_ids.filtered(
                    lambda p: p.payment_method_id.type == "pay_later"
                ).mapped("amount")
            )
        remaining = limit - due

        if float_compare(due + amount, limit, precision_rounding=currency.rounding) > 0:
            status.update(
                blocked=True,
                message=_(
                    "Employee %(employee)s exceeds his due limit.\n\n"
                    "Current due: %(due)s\n"
                    "This order: %(amount)s\n"
                    "Limit: %(limit)s\n"
                    "Remaining allowed: %(remaining)s",
                    employee=employee.name,
                    due=formatLang(self.env, due, currency_obj=currency),
                    amount=formatLang(self.env, amount, currency_obj=currency),
                    limit=formatLang(self.env, limit, currency_obj=currency),
                    remaining=formatLang(self.env, max(remaining, 0.0), currency_obj=currency),
                ),
            )
        return status

    @api.model
    def pos_check_employee_due_limit(self, partner_id, config_id, amount):
        partner = self.browse(partner_id).exists()
        config = self.env["pos.config"].browse(config_id).exists()
        if not partner or not config or amount <= 0:
            return {"blocked": False, "message": ""}
        return partner._get_employee_due_limit_status(config, amount)
