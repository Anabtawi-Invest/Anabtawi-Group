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
            if code in buckets:
                buckets[code] += line.number_of_hours or 0.0
            # Common lateness codes - adjust in settings or extend if needed
            if code in ('LAT', 'LATE', 'Lateness', 'L'):
                lateness += line.number_of_hours or 0.0
        return lateness, buckets

    @api.depends('worked_days_line_ids.number_of_hours', 'worked_days_line_ids.work_entry_type_id.code')
    def _compute_lateness_and_ot(self):
        for slip in self:
            lateness, buckets = slip._get_worked_day_hours_by_code()
            slip.lateness_hours = lateness
            slip.overtime_hours = sum(buckets.values())

    @api.depends('worked_days_line_ids.number_of_hours', 'worked_days_line_ids.work_entry_type_id.code')
    def _compute_remaining_lateness(self):
        # Remaining after reconciliation is stored in a payroll input line (code: REMLATE)
        # If not present, fallback to lateness as "remaining"
        for slip in self:
            rem = 0.0
            inp = slip.input_line_ids.filtered(lambda l: (l.code or '').strip() == 'REMLATE')
            if inp:
                rem = sum(inp.mapped('amount'))
            else:
                rem = slip.lateness_hours
            slip.remaining_lateness_hours = rem

    def action_reconcile_lateness_no_ot_bank(self):
        """Core reconciliation:
        - Consume OT hours in order OTR -> PHO -> OTW by reducing worked days OT hours.
        - If still remaining, create a Time Off (hr.leave) request in HOURS against configured Annual Leave type,
          so balance decreases.
        - If still remaining, store remaining hours into payslip input line code REMLATE (for salary deduction rule).
        """
        Leave = self.env['hr.leave']
        LeaveType = self.env['hr.leave.type']
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
                lines = slip.worked_days_line_ids.filtered(lambda l: (l.work_entry_type_id.code or '').strip() == code).sorted('id')
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
                leave_type_id = int(self.env['ir.config_parameter'].sudo().get_param('lateness_coverage.annual_leave_type_id') or 0)
                if not leave_type_id:
                    raise UserError(_(
                        'Annual Leave Type for lateness coverage is not configured.\n'
                        'Go to Settings > Lateness Coverage and set an hour-based Annual Leave Type.'
                    ))
                leave_type = LeaveType.browse(leave_type_id).exists()
                if not leave_type:
                    raise UserError(_('Configured Annual Leave Type not found. Please reconfigure Settings > Lateness Coverage.'))

                # Create a validated leave in hours so balance decreases.
                # NOTE: Depending on company policy, you may want "confirm" only; here we validate.
                # Odoo uses request_unit / request_unit_half_day in recent versions; here we set hours via number_of_hours_display.
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
                leave = Leave.sudo().create(leave_vals)
                # confirm & validate to impact balance
                leave.sudo().action_confirm()
                leave.sudo().action_approve() if hasattr(leave, 'action_approve') else None
                if hasattr(leave, 'action_validate'):
                    leave.sudo().action_validate()
                else:
                    # v19 should have action_validate; keep safe fallback
                    leave.sudo().action_approve()

                remaining = 0.0

            # 3) Store remaining lateness for payroll deduction rule (input line)
            # Always keep input line consistent (even if 0)
            inp = slip.input_line_ids.filtered(lambda l: (l.code or '').strip() == 'REMLATE')
            if inp:
                inp.write({'amount': remaining})
            else:
                self.env['hr.payslip.input'].create({
                    'payslip_id': slip.id,
                    'name': 'Remaining Lateness (hrs)',
                    'code': 'REMLATE',
                    'amount': remaining,
                })
        return True