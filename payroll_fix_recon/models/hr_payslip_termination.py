# -*- coding: utf-8 -*-
"""End-of-service clearance inputs, based on the post-reconciliation balances."""
from odoo import fields, models

from . import pfr_utils as U


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _pfr_is_termination(self):
        self.ensure_one()
        name = (self.struct_id.name or '').lower() if self.struct_id else ''
        return bool(getattr(self, 'termination_clearance', False) or 'termination' in name or 'تيرمنيشن' in name)

    def _pfr_leave_balance_days(self, leave_types, balance_hours):
        """Remaining days of the given leave types (native balance first, allocations as fallback)."""
        emp = self.employee_id
        target = self.date_to or fields.Date.today()
        days = 0.0
        for ltype in leave_types:
            try:
                data, _ = emp._get_consumed_leaves(ltype, target_date=target)
                content = data.get(emp, {}).get(ltype, {})
                val = content.get('virtual_remaining_leaves') or content.get('remaining_leaves') or 0.0
                days += float(val or sum(v.get('virtual_remaining_leaves', 0.0)
                                         for v in content.values() if isinstance(v, dict)))
            except Exception:
                pass
        return days or max(0.0, sum(balance_hours.get((emp.id, t.id), 0.0) for t in leave_types) / U.DAILY_HOURS)

    def _pfr_set_input(self, code, quantity, amount):
        itype = self.env['hr.payslip.input.type'].sudo().search([('code', '=', code)], limit=1)
        if not itype:
            return
        Input = self.env['hr.payslip.input']
        vals = {'amount': amount}
        if 'quantity' in Input._fields:
            vals['quantity'] = quantity
        line = self.input_line_ids.filtered(lambda l: l.input_type_id == itype)[:1]
        if line:
            self.input_line_ids = [(1, line.id, vals)]
        else:
            self.input_line_ids = [(0, 0, dict(vals, input_type_id=itype.id))]

    def _pfr_apply_termination_inputs(self):
        settlement = self.env['pfr.settlement']
        for slip in self.filtered(lambda s: s.employee_id and s._pfr_is_termination()):
            wage = slip._pfr_wage()
            hourly, daily = wage / U.HOURLY_DIVISOR, wage / U.ANNUAL_DAY_DIVISOR
            types = settlement.leave_types(slip.company_id)
            bal = settlement.balance_hours([slip.employee_id.id], (types['annual'] | types['pto']).ids)

            extra = max(0.0, round(slip.remaining_extra_hours_balance, 2))
            slip._pfr_set_input('CLEAR_EXTRA', extra, round(extra * hourly, 3))

            annual = slip._pfr_leave_balance_days(types['annual'], bal)
            annual = max(0.0, round(annual - (slip.lateness_covered_by_annual_leave or 0.0) / U.DAILY_HOURS, 4))
            slip._pfr_set_input('CLEAR_ANNUAL', annual, round(annual * daily, 3))

            pto = slip._pfr_leave_balance_days(types['pto'], bal)
            slip._pfr_set_input('CLEAR_PTO', pto, round(pto * daily, 3))
