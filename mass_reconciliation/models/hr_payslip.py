# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

OT_PRIORITY_CODES = ['OTR', 'PHO', 'OTW']  # Weekend, Public Holiday, Weekday


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

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

            # Adjust if your lateness work entry type has another code
            if code in ('LAT', 'LATE', 'LATENESS', 'Lateness', 'L'):
                lateness += line.number_of_hours or 0.0

        return lateness, buckets

    @api.depends('worked_days_line_ids.number_of_hours', 'worked_days_line_ids.work_entry_type_id.code')
    def _compute_lateness_and_ot(self):
        for slip in self:
            lateness, buckets = slip._get_worked_day_hours_by_code()
            slip.lateness_hours = lateness
            slip.overtime_hours = sum(buckets.values())

    @api.depends('input_line_ids.amount', 'input_line_ids.code')
    def _compute_remaining_lateness(self):
        for slip in self:
            inp = slip.input_line_ids.filtered(lambda l: (l.code or '').strip() == 'REMLATE')
            slip.remaining_lateness_hours = sum(inp.mapped('amount')) if inp else slip.lateness_hours

    def _get_annual_leave_type_id(self):
        icp = self.env['ir.config_parameter'].sudo()
        val = icp.get_param('mass_reconciliation.annual_leave_type_id') or icp.get_param('lateness_coverage.annual_leave_type_id') or 0
        try:
            return int(val)
        except Exception:
            return 0

    def _ensure_remaining_input_type(self):
        it = self.env['hr.payslip.input.type'].sudo().search([('code', '=', 'REMLATE')], limit=1)
        if not it:
            it = self.env['hr.payslip.input.type'].sudo().create({'name': 'Remaining Lateness (hrs)', 'code': 'REMLATE'})
        return it

    def _write_remaining_input(self, remaining):
        self.ensure_one()
        inp = self.input_line_ids.filtered(lambda l: (l.code or '').strip() == 'REMLATE')
        if inp:
            inp.write({'amount': remaining})
        else:
            it = self._ensure_remaining_input_type()
            self.env['hr.payslip.input'].sudo().create({
                'payslip_id': self.id,
                'input_type_id': it.id,
                'name': it.name,
                'code': it.code,
                'amount': remaining,
            })

    def action_reconcile_lateness_no_ot_bank(self):
        """Reconcile lateness without OT bank:
        1) Reduce OT hours in order OTR -> PHO -> OTW (worked days lines).
        2) If still remaining, create and validate an hour-based Annual Leave request to reduce balance.
        3) Store any remaining lateness in payslip input REMLATE for salary deduction rule.
        """
        Leave = self.env['hr.leave'].sudo()
        LeaveType = self.env['hr.leave.type'].sudo()

        for slip in self:
            lateness, buckets = slip._get_worked_day_hours_by_code()
            remaining = lateness

            # 1) Consume OT in priority order by reducing worked days line hours
            for code in OT_PRIORITY_CODES:
                if remaining <= 0:
                    break
                available = buckets.get(code, 0.0)
                if available <= 0:
                    continue

                consume = min(available, remaining)
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

            # 2) Deduct remaining from Annual Leave (hours) if configured
            if remaining > 0:
                leave_type_id = slip._get_annual_leave_type_id()
                if not leave_type_id:
                    raise UserError(_(
                        "Annual Leave Type (hours) is not configured.\n"
                        "Set System Parameter: mass_reconciliation.annual_leave_type_id = <Leave Type ID>"
                    ))

                leave_type = LeaveType.browse(leave_type_id).exists()
                if not leave_type:
                    raise UserError(_("Configured Annual Leave Type not found (check mass_reconciliation.annual_leave_type_id)."))

                # Version-safe creation: rely on date_from/date_to so Odoo computes the duration
                dt_from = fields.Datetime.to_datetime(slip.date_from)
                dt_to = dt_from + timedelta(hours=float(remaining))

                leave_vals = {
                    'name': _('Lateness Coverage (%s)') % (getattr(slip, 'number', False) or slip.name),
                    'employee_id': slip.employee_id.id,
                    'holiday_status_id': leave_type.id,
                    'date_from': dt_from,
                    'date_to': dt_to,
                }

                # Add optional request_* fields only if they exist on this build
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

                # Safety: drop any unknown keys
                for k in list(leave_vals.keys()):
                    if k not in Leave._fields:
                        leave_vals.pop(k, None)

                leave = Leave.create(leave_vals)

                # Validate with method-safe calls
                leave_sudo = leave.sudo()
                if hasattr(leave_sudo, 'action_confirm'):
                    leave_sudo.action_confirm()
                elif hasattr(leave_sudo, 'action_submit'):
                    leave_sudo.action_submit()

                if hasattr(leave_sudo, 'action_validate'):
                    leave_sudo.action_validate()
                elif hasattr(leave_sudo, 'action_approve'):
                    leave_sudo.action_approve()
                elif 'state' in leave_sudo._fields:
                    leave_sudo.write({'state': 'validate'})

                remaining = 0.0

            # 3) Store remaining lateness for salary deduction rule
            slip._write_remaining_input(remaining)

        return {'type': 'ir.actions.client', 'tag': 'reload'}
