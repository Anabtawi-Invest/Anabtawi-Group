from odoo import api, fields, models
from odoo.tools import float_is_zero


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    termination_clearance = fields.Boolean(
        string="Termination Clearance",
        help="Technical compatibility field used by custom payslip views.",
    )
    pos_debt_total_open = fields.Monetary(
        string="Open POS Debt",
        compute="_compute_pos_debt_totals",
        currency_field="currency_id",
    )
    pos_debt_deduction_amount = fields.Monetary(
        string="POS Debt Deduction Amount",
        readonly=True,
        copy=False,
        currency_field="currency_id",
    )

    @api.depends("employee_id")
    def _compute_pos_debt_totals(self):
        move_line_model = self.env["account.move.line"].sudo()
        for slip in self:
            slip.pos_debt_total_open = 0.0
            partner = slip._get_pos_due_partner()
            if not partner:
                continue
            due_lines = move_line_model.search(
                [
                    ("partner_id", "=", partner.id),
                    ("is_pos_payroll_due", "=", True),
                    ("account_id.account_type", "=", "asset_receivable"),
                    ("parent_state", "=", "posted"),
                    ("reconciled", "=", False),
                    ("amount_residual", ">", 0),
                    ("company_id", "=", slip.company_id.id),
                ]
            )
            slip.pos_debt_total_open = sum(due_lines.mapped("amount_residual"))

    def _get_pos_debt_input_type(self):
        return self.env.ref("pos_employee_payroll_deduction.input_type_pos_debt", raise_if_not_found=False)

    def _get_pos_due_partner(self):
        self.ensure_one()
        if not self.employee_id:
            return self.env["res.partner"]

        if self.employee_id.pos_debt_partner_id:
            return self.employee_id.pos_debt_partner_id

        if "work_contact_id" in self.employee_id._fields and self.employee_id.work_contact_id:
            return self.employee_id.work_contact_id

        if "address_home_id" in self.employee_id._fields and self.employee_id.address_home_id:
            return self.employee_id.address_home_id

        return self.env["res.partner"]

    def _get_open_pos_due_lines(self):
        self.ensure_one()
        partner = self._get_pos_due_partner()
        if not partner:
            return self.env["account.move.line"]
        return self.env["account.move.line"].sudo().search(
            [
                ("partner_id", "=", partner.id),
                ("is_pos_payroll_due", "=", True),
                ("account_id.account_type", "=", "asset_receivable"),
                ("parent_state", "=", "posted"),
                ("reconciled", "=", False),
                ("amount_residual", ">", 0),
                ("company_id", "=", self.company_id.id),
            ],
            order="date asc, id asc",
        )

    def _calculate_pos_debt_amount_for_input(self, debts):
        self.ensure_one()
        amount = sum(debts.mapped("amount_residual"))
        limit = self.employee_id.pos_debt_monthly_limit or 0.0
        if limit > 0.0:
            amount = min(amount, limit)
        return self.currency_id.round(amount)

    def _upsert_pos_debt_input_line(self):
        self.ensure_one()
        input_type = self._get_pos_debt_input_type()
        if not input_type:
            return

        existing_lines = self.input_line_ids.filtered(lambda l: l.input_type_id == input_type)
        amount = self._calculate_pos_debt_amount_for_input(self._get_open_pos_due_lines())
        rounding = self.currency_id.rounding

        if float_is_zero(amount, precision_rounding=rounding):
            existing_lines.unlink()
            self.pos_debt_deduction_amount = 0.0
            return

        vals = {
            "amount": amount,
            "input_type_id": input_type.id,
        }
        if "name" in self.env["hr.payslip.input"]._fields:
            vals["name"] = input_type.name
        if "contract_id" in self.env["hr.payslip.input"]._fields and self.contract_id:
            vals["contract_id"] = self.contract_id.id

        if existing_lines:
            existing_lines[0].write(vals)
            if len(existing_lines) > 1:
                existing_lines[1:].unlink()
        else:
            vals["payslip_id"] = self.id
            self.env["hr.payslip.input"].create(vals)

        self.pos_debt_deduction_amount = amount

    def _reconcile_pos_due_from_payslip(self):
        input_type = self._get_pos_debt_input_type()
        if not input_type:
            return

        for slip in self:
            if not slip.employee_id or not slip.move_id:
                continue

            input_lines = slip.input_line_ids.filtered(lambda l: l.input_type_id == input_type)
            amount = sum(input_lines.mapped("amount"))
            if float_is_zero(amount, precision_rounding=slip.currency_id.rounding):
                continue

            partner = slip._get_pos_due_partner()
            if not partner:
                continue

            due_lines = slip._get_open_pos_due_lines()
            if not due_lines:
                continue

            credit_receivable_lines = slip.move_id.line_ids.filtered(
                lambda line: (
                    line.partner_id == partner
                    and line.account_id.account_type == "asset_receivable"
                    and not line.reconciled
                    and line.balance < 0
                )
            )
            if not credit_receivable_lines:
                continue

            for credit_line in credit_receivable_lines:
                candidate_due_lines = due_lines.filtered(
                    lambda line: line.account_id == credit_line.account_id and not line.reconciled
                )
                if candidate_due_lines:
                    (credit_line | candidate_due_lines).reconcile()

    def compute_sheet(self):
        for slip in self:
            slip._upsert_pos_debt_input_line()
        return super().compute_sheet()

    def action_payslip_done(self):
        result = super().action_payslip_done()
        self._reconcile_pos_due_from_payslip()
        return result

    def action_payslip_cancel(self):
        return super().action_payslip_cancel()
