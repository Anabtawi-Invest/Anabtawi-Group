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
        """Remaining days of the given leave types (matching Time Off Dashboard including excess_days & negative allocations)."""
        emp = self.employee_id
        bal_days = sum(balance_hours.get((emp.id, t.id), 0.0) for t in leave_types) / U.DAILY_HOURS
        days = 0.0
        got_native = False
        for ltype in leave_types:
            try:
                data, to_recheck = emp._get_consumed_leaves(ltype)
                content = data.get(emp, {}).get(ltype, {})
                recheck = to_recheck.get(emp, {}).get(ltype, {}) if isinstance(to_recheck, dict) else {}
                if 'virtual_remaining_leaves' in content or 'remaining_leaves' in content:
                    rem = float(content.get('virtual_remaining_leaves') or content.get('remaining_leaves') or 0.0)
                else:
                    rem = sum(
                        float(v.get('virtual_remaining_leaves', 0.0) or 0.0)
                        for v in content.values()
                        if isinstance(v, dict)
                    )
                excess = float(recheck.get('excess_days', 0.0) or 0.0)
                days += (rem - excess)
                got_native = True
            except Exception:
                pass
        if got_native:
            # If negative allocations exist that _get_consumed_leaves ignored, bal_days will reflect the full net balance
            if bal_days < days and abs(bal_days - days) > 0.001:
                return bal_days
            return days
        return bal_days

    def _pfr_set_input(self, code, quantity, amount):
        itype = self.env['hr.payslip.input.type'].sudo().search([('code', '=', code)], limit=1)
        if not itype:
            try:
                itype = self.env['hr.payslip.input.type'].sudo().create({
                    'code': code,
                    'name': code.replace('_', ' ').title(),
                })
            except Exception:
                return
        Input = self.env['hr.payslip.input']
        vals = {'amount': amount}
        if 'quantity' in Input._fields:
            vals['quantity'] = quantity
        line = self.input_line_ids.filtered(lambda l: l.input_type_id == itype)[:1]
        if line:
            line.sudo().write(vals)
        else:
            self.input_line_ids = [(0, 0, dict(vals, input_type_id=itype.id))]

    def _pfr_apply_termination_inputs(self):
        """Write CLEAR_* inputs at stored (inflated) rates for Other Inputs / salary rules.

        PDF leave boxes divide for display only (PTO / 1.5, Extra Hours / 1.25) in the report
        template — quantity and amount here stay on the full banked figures.
        """
        settlement = self.env['pfr.settlement']
        for slip in self.filtered(lambda s: s.employee_id and s._pfr_is_termination()):
            wage = slip._pfr_wage()
            hourly, daily = wage / U.HOURLY_DIVISOR, wage / U.ANNUAL_DAY_DIVISOR
            types = settlement.leave_types(slip.company_id)
            bal = settlement.balance_hours([slip.employee_id.id], (types['annual'] | types['pto']).ids)

            # Remaining Extra Hours balance is in real hours (divided by 1.25).
            # The termination settlement amount is multiplied by 1.25 (U.OT_RATE).
            extra = max(0.0, round(slip.remaining_extra_hours_balance or 0.0, 2))
            slip._pfr_set_input('CLEAR_EXTRA', extra, round(extra * U.OT_RATE * hourly, 3))

            annual = slip._pfr_leave_balance_days(types['annual'], bal)
            annual = round(annual - (slip.lateness_covered_by_annual_leave or 0.0) / U.DAILY_HOURS, 4)
            slip._pfr_set_input('CLEAR_ANNUAL', annual, round(annual * daily, 3))

            # Remaining PTO balance is in real hours (divided by 1.5).
            # The termination settlement amount is multiplied by 1.5 (U.PH_RATE).
            if 'remaining_pto_balance' in slip._fields:
                pto = max(0.0, round((slip.remaining_pto_balance or 0.0) / U.DAILY_HOURS, 4))
            else:
                pto = slip._pfr_leave_balance_days(types['pto'], bal)
                covered = getattr(slip, 'lateness_covered_by_pto', 0.0) or 0.0
                pto = max(0.0, round(pto - covered / U.DAILY_HOURS, 4))
            slip._pfr_set_input('CLEAR_PTO', pto, round(pto * U.PH_RATE * daily, 3))
