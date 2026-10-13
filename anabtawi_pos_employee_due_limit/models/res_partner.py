# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.tools import float_compare
from odoo.tools.misc import formatLang

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    pos_customer_account_due = fields.Monetary(
        string="POS Customer Account Due",
        currency_field="currency_id",
        readonly=True,
        copy=False,
        help="Unpaid POS Customer Account sales of this employee (all companies). "
        "This is the due compared with the Partner Limit in the POS.",
    )

    def _refresh_pos_customer_account_due(self):
        """Store the current POS Customer Account due on the work contacts of these partners."""
        commercial_partners = self.commercial_partner_id
        if not commercial_partners:
            return
        employees = self.env["hr.employee"].sudo().with_context(active_test=False).search([
            ("work_contact_id.commercial_partner_id", "in", commercial_partners.ids),
        ])
        for partner in employees.work_contact_id:
            company = employees.filtered(lambda e: e.work_contact_id == partner)[:1].company_id
            currency = (company or self.env.company).currency_id
            posted, open_sessions = partner._get_pos_customer_account_due(currency)
            due = currency.round(posted + open_sessions)
            if float_compare(partner.pos_customer_account_due, due, precision_rounding=currency.rounding):
                partner.sudo().pos_customer_account_due = due

    def _get_due_limit_employee(self, company):
        self.ensure_one()
        partners = self | self.commercial_partner_id
        employees = self.env["hr.employee"].sudo().search([("work_contact_id", "in", partners.ids)])
        return employees.filtered(lambda e: e.company_id == company)[:1] or employees[:1]

    def _get_pos_customer_account_due(self, currency, exclude_order=None):
        """Unpaid POS Customer Account sales of this customer, in `currency`, all companies.

        Returns (posted, open_sessions):
        - posted: open balance of receivable lines created by POS (session closing entries and
          invoices of POS orders), so payments reconciled with them reduce it.
        - open_sessions: Customer Account payments of orders in sessions not closed yet
          (not invoiced, since an invoice already carries its own receivable).
        Other receivable entries (manual entries, sales invoices, payroll...) are ignored.
        """
        self.ensure_one()
        today = fields.Date.today()
        commercial_partner = self.commercial_partner_id

        lines = self.env["account.move.line"].sudo().search([
            ("parent_state", "=", "posted"),
            ("reconciled", "=", False),
            ("account_id.account_type", "=", "asset_receivable"),
            ("partner_id", "child_of", commercial_partner.id),
            "|",
            ("move_id.pos_session_ids", "!=", False),
            ("move_id.pos_order_ids", "!=", False),
        ])
        posted = 0.0
        for line in lines:
            line_currency = line.company_id.currency_id
            posted += line_currency._convert(line.amount_residual, currency, line.company_id, today)

        payments = self.env["pos.payment"].sudo().search([
            ("pos_order_id.partner_id", "child_of", commercial_partner.id),
            ("pos_order_id.state", "=", "paid"),
            ("pos_order_id.account_move", "=", False),
            ("session_id.state", "!=", "closed"),
        ]).filtered(lambda p: p.payment_method_id.type == "pay_later")
        if exclude_order:
            payments = payments.filtered(lambda p: p.pos_order_id != exclude_order)
        open_sessions = 0.0
        for payment in payments:
            payment_currency = payment.currency_id or payment.company_id.currency_id
            open_sessions += payment_currency._convert(payment.amount, currency, payment.company_id, today)

        return currency.round(posted), currency.round(open_sessions)

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
        posted_due, open_due = self._get_pos_customer_account_due(currency, exclude_order)
        due = posted_due + open_due
        remaining = limit - due
        blocked = float_compare(due + amount, limit, precision_rounding=currency.rounding) > 0

        _logger.info(
            "[EMPLOYEE_DUE_LIMIT] partner %s (%s) employee %s (%s) company %s: wage=%s deduction=%s%% "
            "max=%s%% limit=%s | POS customer account due: posted=%s open_sessions=%s "
            "(excluding order %s) total=%s | this_order=%s due+order=%s -> %s",
            self.id, self.name, employee.id, employee.name, employee.company_id.name, wage,
            employee.company_id.employee_due_deduction_percent,
            employee.company_id.employee_due_max_percent, limit, posted_due, open_due,
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
