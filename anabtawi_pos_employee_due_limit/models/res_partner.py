# -*- coding: utf-8 -*-

import logging

import pytz
from dateutil.relativedelta import relativedelta

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

    def _get_company_calendar_month_bounds(self, company):
        """UTC datetime bounds of the current calendar month in the company timezone."""
        tz_name = company.partner_id.tz or self.env.context.get("tz") or self.env.user.tz or "UTC"
        try:
            tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            tz = pytz.UTC
        now_utc = fields.Datetime.now()
        if isinstance(now_utc, str):
            now_utc = fields.Datetime.from_string(now_utc)
        now_local = pytz.utc.localize(now_utc).astimezone(tz)
        start_local = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_local = start_local + relativedelta(months=1)
        start_utc = start_local.astimezone(pytz.utc).replace(tzinfo=None)
        end_utc = end_local.astimezone(pytz.utc).replace(tzinfo=None)
        return start_utc, end_utc

    def _get_pos_customer_account_due_this_month(self, currency, company, exclude_order=None):
        """Sum of Customer Account payments on POS orders dated in the current calendar month.

        Older months are ignored completely, even if still unpaid. Settlements of older months
        do not free this month's allowance. Amounts are converted to `currency`.
        """
        self.ensure_one()
        start_utc, end_utc = self._get_company_calendar_month_bounds(company)
        commercial_partner = self.commercial_partner_id
        domain = [
            ("partner_id", "child_of", commercial_partner.id),
            ("state", "in", ["paid", "done"]),
            ("date_order", ">=", start_utc),
            ("date_order", "<", end_utc),
        ]
        orders = self.env["pos.order"].sudo().search(domain)
        if exclude_order:
            orders -= exclude_order

        today = fields.Date.today()
        total = 0.0
        for payment in orders.payment_ids.filtered(
            lambda p: p.amount > 0 and p.payment_method_id.type == "pay_later"
        ):
            payment_currency = payment.currency_id or payment.company_id.currency_id
            total += payment_currency._convert(
                payment.amount, currency, payment.company_id, today
            )
        return currency.round(total), start_utc, end_utc

    def _get_employee_due_limit_status(self, config, amount, exclude_order=None):
        """Check whether adding `amount` on Customer Account keeps the employee under his monthly limit.

        Amounts are in the POS currency. Partners that are not employees are never blocked.
        Only POS Customer Account sales of the current calendar month (company timezone, by
        order date) are counted. Older unpaid dues are ignored.
        """
        self.ensure_one()
        status = {"blocked": False, "message": ""}
        employee = self._get_due_limit_employee(config.company_id)
        if not employee:
            _logger.info(
                "[EMPLOYEE_DUE_LIMIT] partner %s (%s) is not an employee work contact -> not checked",
                self.id, self.name,
            )
            return status
        if not employee.company_id.employee_due_limit_enabled:
            _logger.info(
                "[EMPLOYEE_DUE_LIMIT] employee %s company %s has due limit disabled -> not checked",
                employee.id, employee.company_id.name,
            )
            return status

        currency = config.currency_id
        wage = employee._get_employee_due_wage()
        if not wage:
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
            limit = employee_currency._convert(
                limit, currency, config.company_id, fields.Date.today()
            )

        due, month_start, month_end = self._get_pos_customer_account_due_this_month(
            currency, employee.company_id or config.company_id, exclude_order=exclude_order
        )
        remaining = limit - due
        blocked = float_compare(due + amount, limit, precision_rounding=currency.rounding) > 0

        _logger.info(
            "[EMPLOYEE_DUE_LIMIT] partner %s (%s) employee %s: wage=%s limit=%s | "
            "month [%s, %s) this_month_due=%s this_order=%s due+order=%s -> %s",
            self.id, self.name, employee.name, wage, limit,
            month_start, month_end, due, amount, due + amount,
            "BLOCKED" if blocked else "allowed",
        )

        if blocked:
            status.update(
                blocked=True,
                message=_(
                    "Employee %(employee)s exceeds his monthly due limit.\n\n"
                    "This month's Customer Account: %(due)s\n"
                    "This order: %(amount)s\n"
                    "Monthly limit: %(limit)s\n"
                    "Remaining this month: %(remaining)s",
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
            "[EMPLOYEE_DUE_LIMIT] POS check called: partner_id=%s config_id=%s amount=%s",
            partner_id, config_id, amount,
        )
        partner = self.browse(partner_id).exists()
        config = self.env["pos.config"].browse(config_id).exists()
        if not partner or not config or amount <= 0:
            return {"blocked": False, "message": ""}
        return partner._get_employee_due_limit_status(config, amount)
