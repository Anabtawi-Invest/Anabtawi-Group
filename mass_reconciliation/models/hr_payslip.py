# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

OT_PRIORITY_CODES = ['OTR', 'PHO', 'OTW']  # Weekend, Public Holiday, Weekday


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    # Clean field names (no dashboard_*)
    lateness_hours = fields.Float(string='Lateness (hrs)', compute='_compute_lateness_and_ot', store=False)
    overtime_hours = fields.Float(string='Overtime (hrs)', compute='_compute_lateness_and_ot', store=False)
    remaining_lateness_hours = fields.Float(string='Remaining Lateness (hrs)', compute='_compute_remaining_lateness', store=False)

    # ---- Helpers -------------------------------------------------------------

    def _get_worked_day_hours_by_code(self):
        """Return (lateness_hours, overtime_buckets_dict)"""
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

    # ---- Computes ------------------------------------------------------------

    @api.depends('worked_days_line_ids.number_of_hours', 'worked_days_line_ids.work_entry_type_id.code')
    def _compute_lateness_and_ot(self):
        for slip in self:
            lateness, buckets = slip._get_worked_day_hours_by_code()
            slip.lateness_hours = lateness
            slip.overtime_hours = sum(buckets.values())

    @api.depends('input_line_ids.amount', 'input_line_ids.code', 'worked_days_line_ids.number_of_hours',
                 'worked_days_line_ids.work_entry_type_id.code')
    def _compute_remaining_lateness(self):
        """
        Remaining after reconciliation is stored in payslip input code REMLATE.
        If not present yet, fallback to current lateness.
        """
        for slip in self:
            inp = slip.input_line_ids.filtered(lambda l: (l.code or '').strip() == 'REMLATE')
            if inp:
                slip.remaining_lateness_hours = sum(inp.mapped('amount'))
            else:
                slip.remaining_lateness_hours = slip.lateness_hours

    # ---- Main Action ---------------------------------------------------------

    def action_reconcile_lateness_no_ot_bank(self):
        """
        Core reconciliation:
        1) Consume OT hours in order OTR -> PHO -> OTW by reducing worked days OT hours.
        2) If still remaining, deduct from Annual Leave (hours) using Time Off so balance decreases.
        3) Store remaining hours into payslip input line code REMLATE (salary deduction rule).
        """
        Leave = self.env['hr.leave'].sudo()
        LeaveType = self.env['hr.leave.type'].sudo()

        for slip in self:
            lateness, buckets = slip._get_worked_day_hours_by_code()
            remaining = lateness

            # 1) Consume OT buckets by reducing worked days lines (number_of_hours)
            for code in OT_PRIORITY_CODES:
                if remaining <= 0:
                    break

                available = buckets.get(code, 0.0)
                if available <= 0:
                    continue

                consume = min(available, remaining)

                # Reduce hours from worked days lines for that code (FIFO by id)
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

            # 2) If remaining > 0, deduct from Annual Leave (hours) via Time Off
            if remaining > 0:
                # ✅ FIX: read the correct key
                leave_type_id = int(
                    self.env['ir.config_parameter'].sudo().get_param(
                        'mass_reconciliation.annual_leave_type_id'
                    ) or 0
                )
                if not leave_type_id:
                    raise UserError(_(
                        'Annual Leave Type for lateness coverage is not configured.\n'
                        'Please set system parameter:\n'
                        'mass_reconciliation.annual_leave_type_id = <Leave Type ID>'
                    ))

                leave_type = LeaveType.browse(leave_type_id).exists()
                if not leave_type:
                    raise UserError(_(
                        'Configured Annual Leave Type not found.\n'
                        'Please reconfigure system parameter:\n'
                        'mass_reconciliation.annual_leave_type_id'
                    ))

                # Create a validated leave in hours so balance decreases
                leave_vals = {
                    'name': _('Lateness Coverage (%s)') % (slip.number or slip.name),
                    'employee_id': slip.employee_id.id,
                    'holiday_status_id': leave_type.id,
                    'request_date_from': slip.date_from,
                    'request_date_to': slip.date_to,
                    'request_unit_hours': True,
                    'request_hour_from': 0.0,
                    'request_hour_to': 0.0,
                    'number_of_hours_display': remaining,
                }
                leave = Leave.create(leave_vals)

                # confirm & validate to impact balance
                leave.action_confirm()
                if hasattr(leave, 'action_validate'):
                    leave.action_validate()
                elif hasattr(leave, 'action_approve'):
                    leave.action_approve()

                remaining = 0.0

            # 3) Store remaining lateness for payroll deduction rule (input line)
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

        # ✅ FIX: return valid action dict (avoid RPC issues)
        return {'type': 'ir.actions.client', 'tag': 'reload'}
    
