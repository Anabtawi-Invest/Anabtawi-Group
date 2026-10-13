# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.tools import float_compare
from odoo.tools.misc import formatLang

_logger = logging.getLogger(__name__)


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
        if not employee:
            _logger.info(
                "[EMPLOYEE_DUE_LIMIT] partner %s (%s) / commercial partner %s is not the work contact "
                "of any employee -> not checked",
                self.id, self.name, self.commercial_partner_id.id,
            )
            return status
        if not employee.company_id.employee_due_limit_enabled:
            _logger.info(
                "[EMPLOYEE_DUE_LIMIT] employee %s (%s) company %s (%s) has the due limit disabled "
                "-> not checked (POS config company: %s)",
                employee.id, employee.name, employee.company_id.id, employee.company_id.name,
                config.company_id.name,
            )
            return status

        currency = config.currency_id
        wage = employee._get_employee_due_wage()
        if not wage:
            _logger.info(
                "[EMPLOYEE_DUE_LIMIT] employee %s (%s) has no wage (version %s) -> blocked",
                employee.id, employee.name, employee.sudo().current_version_id.id,
            )
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
        total_due = self.sudo().get_total_due(config.id)["res.partner"][0]["total_due"]
        excluded = 0.0
        if exclude_order and exclude_order.state == "paid" and exclude_order.session_id.state != "closed":
            excluded = sum(
                exclude_order.payment_ids.filtered(
                    lambda p: p.payment_method_id.type == "pay_later"
                ).mapped("amount")
            )
        due = total_due - excluded
        remaining = limit - due
        blocked = float_compare(due + amount, limit, precision_rounding=currency.rounding) > 0

        _logger.info(
            "[EMPLOYEE_DUE_LIMIT] partner %s (%s) employee %s (%s) company %s: wage=%s deduction=%s%% "
            "max=%s%% limit=%s | total_due=%s excluded_current_order=%s (order %s) due=%s "
            "| this_order=%s due+order=%s -> %s",
            self.id, self.name, employee.id, employee.name, employee.company_id.name, wage,
            employee.company_id.employee_due_deduction_percent,
            employee.company_id.employee_due_max_percent, limit, total_due, excluded,
            exclude_order.id if exclude_order else None, due, amount, due + amount,
            "BLOCKED" if blocked else "allowed",
        )

        if blocked:
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
        _logger.info(
            "[EMPLOYEE_DUE_LIMIT] POS check called: partner_id=%s config_id=%s amount=%s user=%s",
            partner_id, config_id, amount, self.env.user.login,
        )
        partner = self.browse(partner_id).exists()
        config = self.env["pos.config"].browse(config_id).exists()
        if not partner or not config or amount <= 0:
            _logger.info(
                "[EMPLOYEE_DUE_LIMIT] POS check skipped: partner found=%s config found=%s amount=%s",
                bool(partner), bool(config), amount,
            )
            return {"blocked": False, "message": ""}
        return partner._get_employee_due_limit_status(config, amount)
