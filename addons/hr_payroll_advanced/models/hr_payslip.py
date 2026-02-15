from odoo import models, fields, api


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # =====================================================
    # SMART LEDGER FIELDS
    # =====================================================

    reconciliation_state = fields.Selection(
        [("pending", "Pending"), ("reconciled", "Reconciled")],
        default="pending",
    )

    late_hours = fields.Float(string="Late Hours", store=True)
    ot_total_amount = fields.Float(string="OT Total Amount", store=True)

    ot_deduct_hours = fields.Float(string="OT Deduct Hours", store=True)
    leave_deduct_hours = fields.Float(string="Leave Deduct Hours", store=True)
    salary_deduct_hours = fields.Float(string="Salary Deduct Hours", store=True)

    leave_hours_available = fields.Float(string="Annual Leave Available", store=True)

    late_salary_deduction_amount = fields.Float(
        string="Auto Salary Deduction Amount",
        store=True,
    )

    # =====================================================
    # HELPERS
    # =====================================================

    def _get_hour_rate(self):
        self.ensure_one()
        contract = self.contract_id
        if not contract or not contract.wage:
            return 0.0
        return contract.wage / 240.0

    def _get_late_hours(self):
        total = 0.0
        for w in self.worked_days_line_ids:
            if w.code == "LAT":
                total += w.number_of_hours or 0.0
        return total

    def _get_ot_total_amount(self):
        total = 0.0
        for l in self.line_ids:
            if l.code == "OT_TOTAL":
                total += l.total or 0.0
        return total

    # =====================================================
    # INPUT CREATOR
    # =====================================================

    def _upsert_input(self, code, amount):
        self.ensure_one()

        line = self.input_line_ids.filtered(lambda x: x.code == code)[:1]

        if line:
            line.write({"amount": amount})
        else:
            self.env["hr.payslip.input"].create({
                "payslip_id": self.id,
                "code": code,
                "name": code,
                "amount": amount,
            })

    # =====================================================
    # SMART LEDGER ENGINE
    # =====================================================

    def _smart_ledger_update(self):

        for slip in self:

            employee = slip.employee_id

            late_hours = slip._get_late_hours()
            ot_total_amount = slip._get_ot_total_amount()
            hour_rate = slip._get_hour_rate()

            slip.late_hours = late_hours
            slip.ot_total_amount = ot_total_amount

            if hour_rate <= 0:
                continue

            # -----------------------------------
            # ADD OT TO EMPLOYEE BANK
            # -----------------------------------

            ot_hours_generated = ot_total_amount / hour_rate if hour_rate else 0.0

            employee.overtime_bank_hours += ot_hours_generated
            employee.overtime_bank_amount += ot_total_amount

            # -----------------------------------
            # AUTO CONSUME LATENESS FROM OT BANK
            # -----------------------------------

            consume_ot = min(employee.overtime_bank_hours, late_hours)

            employee.overtime_bank_hours -= consume_ot
            employee.overtime_bank_amount -= (consume_ot * hour_rate)

            remaining_late = late_hours - consume_ot

            slip.ot_deduct_hours = consume_ot
            slip.salary_deduct_hours = remaining_late

            salary_ded_amount = remaining_late * hour_rate

            slip.late_salary_deduction_amount = salary_ded_amount

            # WRITE INPUT FOR LAT_REC RULE
            slip._upsert_input("LAT_SAL_DED", -salary_ded_amount)

            slip.reconciliation_state = "reconciled"

    # =====================================================
    # AUTO RUN ENGINE
    # =====================================================

    def compute_sheet(self):
        res = super().compute_sheet()

        # SMART LEDGER AUTO ENGINE
        self._smart_ledger_update()

        return res

    # =====================================================
    # BUTTON COMPATIBILITY (if called from older views)
    # =====================================================

    def action_reconcile_lateness_engine(self):
        self._smart_ledger_update()
        return True
