# -*- coding: utf-8 -*-
from odoo import api, fields, models

from . import pfr_utils as U


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    employee_work_station = fields.Selection(
        [('headoffice', 'Headoffice'), ('retail', 'Retail'), ('factory', 'Factory')],
        string="Employee Work Station", default='factory', tracking=True,
        help="Headoffice: fixed schedule, 0.5h break. Factory: flexible, Monday rest rule, 1h break. "
             "Retail: flexible, Friday rest rule, 1h break.")
    break_duration_hours = fields.Float(
        string="Break Duration (Hours)", default=1.0, tracking=True,
        help="Lunch break subtracted from shifts. Overrides the station default.")
    allow_annual_leave_lateness_deduction = fields.Boolean(
        string="Accept Annual Deduction", default=True, tracking=True,
        help="Allow lateness to be settled from the Annual Leave balance (step 2).")
    annual_deduction_approval_document = fields.Binary(string="Approval Document", attachment=True)
    annual_deduction_approval_filename = fields.Char(string="Approval Document Filename")

    @api.onchange('employee_work_station')
    def _onchange_employee_work_station(self):
        for emp in self:
            emp.break_duration_hours = 0.5 if emp.employee_work_station == 'headoffice' else 1.0

    def _get_lunch_break_duration(self):
        self.ensure_one()
        if self.break_duration_hours is not None and self.break_duration_hours >= 0.0:
            return self.break_duration_hours
        return 0.5 if self.employee_work_station == 'headoffice' else 1.0

    def is_manager_exempt(self):
        """Managers are exempt from hourly lateness/overtime (not from full-day absence)."""
        self.ensure_one()
        return any(f in self._fields and getattr(self, f) for f in ('x_studio_manager', 'is_manager', 'x_manager'))

    def _pfr_tz(self):
        self.ensure_one()
        cal = self.resource_calendar_id or self.company_id.resource_calendar_id
        return U.get_tz(self.tz or (cal.tz if cal else False) or self.env.user.tz)

    def _pfr_is_fixed_schedule(self):
        """Headoffice = fixed schedule. Factory/retail = flexible. A calendar flagged flexible is flexible."""
        self.ensure_one()
        if (self.employee_work_station or 'factory') != 'headoffice':
            return False
        cal = self.resource_calendar_id
        return not bool(cal and ('flexible' in (cal.name or '').lower()
                                 or getattr(cal, 'flexible_hours', False)))

    def _pfr_contract_window(self, date_from, date_to):
        """(start, end) of the contract(s) overlapping the period; None = open/unknown."""
        self.ensure_one()
        versions = self._get_versions_with_contract_overlap_with_period(date_from, date_to)
        starts, ends, open_end = [], [], False
        for v in versions:
            s, e = U.version_dates(v)
            if s:
                starts.append(s)
            if e:
                ends.append(e)
            else:
                open_end = True
        start = min(starts) if starts else None
        end = max(ends) if (ends and not open_end) else None
        return start, end

    def _pfr_get_absent_type(self):
        WET = self.env['hr.work.entry.type'].sudo()
        absent = WET.search([('code', 'in', list(U.ABSENT_CODES))], limit=1) \
            or WET.search([('display_code', 'in', list(U.ABSENT_CODES))], limit=1)
        return absent or WET.create({
            'name': 'Absent', 'display_code': 'ABS', 'code': 'ABSENT',
            'color': 1, 'is_leave': False, 'round_days': 'NO', 'round_days_type': 'DOWN'})

    def _pfr_day_utc_bounds(self, target_date):
        self.ensure_one()
        return U.day_utc_bounds(target_date, self._pfr_tz())
