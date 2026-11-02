# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields, models, _
from odoo.exceptions import ValidationError

from odoo.addons.payroll_fix_recon.models.pfr_utils import OT_MIN_HOURS


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _recompute_paid_cycle(self):
        """Unpaid, cancel, approve extra hours, draft, reset work entries, compute, validate, paid."""
        self.ensure_one()
        slip = self.with_context(
            tracking_disable=True, mail_notrack=True, mail_create_nolog=True,
            mail_activity_automation_skip=True,
        )
        if slip.state == 'paid':
            slip.action_payslip_unpaid()
        slip.invalidate_recordset()
        if slip.state == 'validated':
            slip.action_payslip_cancel()
        slip.invalidate_recordset()
        if slip.state == 'cancel':
            slip._recompute_approve_extra_hours()
            slip.action_payslip_draft()
        elif slip.state == 'draft':
            slip._recompute_approve_extra_hours()
        slip.invalidate_recordset()
        if slip.state == 'draft':
            slip._recompute_reset_work_entries()
            slip.invalidate_recordset()
            slip.compute_sheet()
        slip.invalidate_recordset()
        if slip.error_count:
            raise ValidationError(slip._get_error_message() or _("Payslip has errors."))
        if slip.state == 'draft':
            slip.action_payslip_done()
        slip.invalidate_recordset()
        if slip.state == 'validated':
            slip.action_payslip_paid()

    def _recompute_approve_extra_hours(self):
        """Green-check extra hours for this employee inside the payslip period.

        Runs after cancel, before the payslip is set back to draft. Attendances
        already approved, or under the 0.75 hour minimum, are left as they are.
        """
        self.ensure_one()
        if not self.employee_id or not self.date_from or not self.date_to:
            return
        if 'hr.attendance' not in self.env:
            return
        Attendance = self.env['hr.attendance'].sudo()
        if 'daily_overtime_hours' not in Attendance._fields or not hasattr(Attendance, 'action_approve_factory_overtime'):
            return
        attendances = Attendance.search([
            ('employee_id', '=', self.employee_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('daily_overtime_hours', '>=', OT_MIN_HOURS),
            ('overtime_status', '!=', 'approved'),
        ])
        if attendances:
            attendances.action_approve_factory_overtime()

    def _recompute_reset_work_entries(self):
        """Rebuild this employee's work entries for the payslip period.

        Days that still have a validated work entry are left as they are.
        Uses the calendar reset when that wizard is installed.
        """
        self.ensure_one()
        employee = self.employee_id
        date_from, date_to = self.date_from, self.date_to
        if not employee or not date_from or not date_to or date_from > date_to:
            return
        WorkEntry = self.env['hr.work.entry'].sudo()
        entries = WorkEntry.search([
            ('employee_id', '=', employee.id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
        ])
        locked_days = set(entries.filtered(lambda entry: entry.state == 'validated').mapped('date'))
        slots = []
        day = date_from
        while day <= date_to:
            if day not in locked_days:
                slots.append({
                    'date': fields.Date.to_string(day),
                    'employee_id': employee.id,
                })
            day += timedelta(days=1)
        if not slots:
            return
        open_entries = entries.filtered(lambda entry: entry.date not in locked_days)
        if 'hr.work.entry.regeneration.wizard' in self.env.registry:
            self.env['hr.work.entry.regeneration.wizard'].sudo().regenerate_work_entries(
                slots, open_entries.ids)
            return
        self._recompute_reset_work_entries_direct(employee, slots, open_entries)

    def _recompute_reset_work_entries_direct(self, employee, slots, entries):
        """Archive open entries and generate them again for each continuous range."""
        WorkEntry = self.env['hr.work.entry'].sudo()
        dates = [fields.Date.from_string(slot['date']) for slot in slots]
        ranges = []
        start = end = dates[0]
        for current in dates[1:]:
            if current - end != timedelta(days=1):
                ranges.append((start, end))
                start = current
            end = current
        ranges.append((start, end))
        null_vals = {'active': False}
        if 'attendance_id' in WorkEntry._fields:
            null_vals['attendance_id'] = False
        for start, end in ranges:
            chunk = entries.filtered(lambda entry, s=start, t=end: entry.date and s <= entry.date <= t)
            if chunk:
                chunk.write(null_vals)
            versions = employee._get_versions_with_contract_overlap_with_period(start, end)
            created = versions.sudo().generate_work_entries(start, end)
            if isinstance(created, list):
                vals = [row for row in created if isinstance(row, dict)]
                if vals:
                    WorkEntry.create(vals)
            if hasattr(employee, '_pfr_create_absent_entries'):
                employee._pfr_create_absent_entries(start, end)
            if hasattr(employee, '_create_absent_work_entries_for_period'):
                employee._create_absent_work_entries_for_period(start, end)
        if hasattr(employee, '_lat_prepare_recompute_map') and hasattr(employee, '_lat_recompute_from_map'):
            recompute_map = employee._lat_prepare_recompute_map()
            recompute_map[employee.id].update(dates)
            employee._lat_recompute_from_map(recompute_map)
