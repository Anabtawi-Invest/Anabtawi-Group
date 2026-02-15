# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

OT_PRIORITY_CODES = ['OTR', 'PHO', 'OTW']  # Weekend, Public Holiday, Weekday


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    # Clean field names (no dashboard_*)
    lateness_hours = fields.Float(string='Lateness (hrs)', compute='_compute_lateness_and_ot', store=False)
    overtime_hours = fields.Float(string='Overtime (hrs)', compute='_compute_lateness_and_ot', store=False)
    remaining_lateness_hours = fields.Float(string='Remaining Lateness (hrs)', compute='_compute_remaining_lateness', store=False)

    def _get_worked_day_hours_by_code(self):
        self.ensure_one()
        buckets = {code: 0.0 for code in OT_PRIORITY_CODES}
        lateness = 0.0

        for line in self.worked_days_line_ids:
            code = (line.work_entry_type_id.code or '').strip()

            # OT buckets
            if code in buckets:
                buckets[code] += line.number_of_hours or 0.0

            # Lateness codes (adjust if your lateness code differs)
            if code in ('LAT', 'LATE', 'Lateness', 'L'):
                lateness += line.number_of_hours or 0.0

        return lateness, buckets

    @api.depends('worked_days_line_ids.number_of_hours', 'worked_days_line_ids.work_entry_type_id.code')
    def _compute_lateness_and_ot(self):
        for slip in self:
            lateness, buckets = slip._get_worked_day_hours_by_code()
            slip.lateness_hours = lateness
            slip.overtime_hours = sum(buckets.values())

    @api.depends('input_line_ids.amount', 'input_line_ids.code',
                 'worked_days_line_ids.number_of_hours', 'worked_days_line_ids.work_entry_type_id.code')
    def _compute_remaining_lateness(self):
        # Remaining after reconciliation is stored in a payroll input line (code: REMLATE)
        # If not present, fallback to lateness as "remaining"
        for slip in self:
            inp = slip.input_line_ids.filtered(lambda l: (l.code or '').strip() == 'REMLATE')
            if inp:
                slip.remaining_lateness_hours = sum(inp.mapped('amount'))
            else:
                slip.remaining_lateness_hours = slip.lateness_hours

    def _get_configured_annual_leave_type_id(self):
        """Prefer mass_reconciliation key, fallback to old lateness_coverage key (for older deployments)."""
        ICP = self.env['ir.config_parameter'].sudo()
        val = ICP.get_param('mass_reconciliation.annual_leave_type_id') or ICP.get_param('lateness_coverage.annual_leave_type_id') or 0
        try:
            return int(val)
        except Exception:
            return 0

    def action_reconcile_lateness_no_ot_bank(self):
        """
        Core reconciliation:
        1) Consume OT hours in order OTR -> PHO -> OTW by reducing worked days OT hours.
        2) If still remaining, create a Time Off (hr.leave) request in HOURS against configured Annual Leave type,
           so balance decreases.
        3) If still remaining, store remaining hours into payslip input line code REMLATE (for salary deduction rule).
        """
        Leave = self.env['hr.leave'].sudo()
        LeaveType = self.env['hr.leave.type'].sudo()

        for slip in self:
            lateness, buckets = slip._get_worked_day_hours_by_code()
            remaining = lateness

            # 1) consume OT buckets by reducing worked days lines (number_of_hours)
            for code in OT_PRIORITY_CODES:
                if remaining <= 0:
                    break

                available = buckets.get(code, 0.0)
                if available <= 0:
                    continue

                consume = min(available, remaining)

                # Reduce hours from worked days lines for that code (FIFO)
                lines = slip.worked_days_line_ids.filtered(
                    lambda l: (l.work_entry_type_id.code or '').strip() == code
                ).sorted('id')

                to_consume = consume
                for line in lines:
                    if to_consume <= 0:
                        break
                    h = line.number_of_hours or 0.0
                    if h <= 0:
                        continue
                    cut = min(h, to_consume)
                    line.number_of_hours = h - cut
                    to_consume -= cut

                remaining -= consume

            # 2) if remaining > 0, deduct from Annual Leave in hours (Time Off)
            if remaining > 0:
                leave_type_id = slip._get_configured_annual_leave_type_id()
                if not leave_type_id:
                    raise UserError(_(
                        "Annual Leave Type for lateness coverage is not configured.\n"
                        "Please set System Parameter:\n"
                        "mass_reconciliation.annual_leave_type_id = <Annual Leave Type ID (Hours)>\n"
                        "(ID 82 in your case)"
                    ))

                leave_type = LeaveType.browse(leave_type_id).exists()
                if not leave_type:
                    raise UserError(_(
                        "Configured Annual Leave Type not found.\n"
                        "Please re-check System Parameter mass_reconciliation.annual_leave_type_id"
                    ))

                # ✅ Version-safe leave creation (NO number_of_hours_display)
                # Create leave using date_from/date_to so Odoo computes the hours.
                dt_from = fields.Datetime.to_datetime(slip.date_from)
                dt_to = dt_from + timedelta(hours=float(remaining))

                leave_vals = {
                    'name': _('Lateness Coverage (%s)') % (getattr(slip, 'number', False) or slip.name),
                    'employee_id': slip.employee_id.id,
                    'holiday_status_id': leave_type.id,
                    'date_from': dt_from,
                    'date_to': dt_to,
                }

                # Extra request_* fields only if they exist in this build (safe)
                if 'request_unit_hours' in Leave._fields:
                    leave_vals['request_unit_hours'] = True
                if 'request_date_from' in Leave._fields:
                    leave_vals['request_date_from'] = slip.date_from
                if 'request_date_to' in Leave._fields:
                    leave_vals['request_date_to'] = slip.date_from
                if 'request_hour_from' in Leave._fields:
                    leave_vals['request_hour_from'] = 0.0
                if 'request_hour_to' in Leave._fields:
                    leave_vals['request_hour_to'] = float(remaining)

                # Safety guard: remove any unsupported fields (future-proof)
                for k in list(leave_vals.keys()):
                    if k not in Leave._fields:
                        leave_vals.pop(k, None)

                leave = Leave.create(leave_vals)

                # Confirm & validate so balance decreases
                leave.action_confirm()
                if hasattr(leave, 'action_validate'):
                    leave.action_validate()
                elif hasattr(leave, 'action_approve'):
                    leave.action_approve()

                remaining = 0.0

            # 3) Store remaining lateness for payroll deduction rule (input line code REMLATE)
            inp = slip.input_line_ids.filtered(lambda l: (l.code or '').strip() == 'REMLATE')
            if inp:
                inp.write({'amount': remaining})
            else:
                input_type = self.env['hr.payslip.input.type'].sudo().search([('code', '=', 'REMLATE')], limit=1)
                if not input_type:
                    input_type = self.env['hr.payslip.input.type'].sudo().create({
                        'name': 'Remaining Lateness (hrs)',
                        'code': 'REMLATE'
                    })

                self.env['hr.payslip.input'].sudo().create({
                    'payslip_id': slip.id,
                    'input_type_id': input_type.id,
                    'name': 'Remaining Lateness (hrs)',
                    'code': 'REMLATE',
                    'amount': remaining,
                })

        # ✅ must return an action dict (avoid RPC errors)
        return {'type': 'ir.actions.client', 'tag': 'reload'}
