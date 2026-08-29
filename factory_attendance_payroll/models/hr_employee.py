# -*- coding: utf-8 -*-

from collections import defaultdict
from datetime import datetime, time, timedelta
import logging
import pytz

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Complete list of Work Entry Type Codes (Display Codes & Payroll Codes) that represent
# Leaves, Holidays, Excused Time Off, and Special Allowances that must NOT generate absence.
EXCUSED_LEAVE_WORK_ENTRY_CODES = [
    # Display Codes
    "GTO", "CTO", "HW", "STO", "PTO", "SIK", "ANU", "PHD", "BFV", "HIL",
    "FWS", "DIE", "MRD", "NPO", "PID", "HAJ", "MAM", "LDO", "TRV", "MKA", "BRK", "UNP", "ARS", "RST", "RESTDAY", "RestDay", "REST_DAY",
    # Payroll Codes
    "LEAVE100", "LEAVE105", "WORK110", "LEAVE110", "LEAVE120", "SICKLEAVE0",
    "An_le", "un_paid", "REST", "RST", "RESTDAY", "RestDay", "REST_DAY",
    # General / standard leave codes
    "LEAVE", "SICK", "VAC", "ANNUAL", "UNPAID", "HOLIDAY", "REST_DAY", "RESTDAY", "RestDay",
]

ABSENT_WORK_ENTRY_CODES = ["ABS", "ABSENT", "A"]


class IrModelData(models.Model):
    _inherit = 'ir.model.data'

    def _register_hook(self):
        """
        Runs when models are loaded into registry during module upgrade.
        Neutralizes all legacy XML tracking records for factory_attendance_payroll by setting noupdate=True,
        permanently preventing Odoo module upgrader from attempting to delete orphan records on staging databases.
        """
        res = super()._register_hook()
        try:
            legacy_data = self.sudo().search([
                ('module', '=', 'factory_attendance_payroll'),
                ('noupdate', '=', False)
            ])
            if legacy_data:
                legacy_data.write({'noupdate': True})
        except Exception:
            pass
        return res


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    employee_work_station = fields.Selection([
        ('headoffice', 'Headoffice'),
        ('retail', 'Retail'),
        ('factory', 'Factory')
    ], string="Employee Work Station", default='factory', tracking=True,
       help="Work station of the employee. Automatically sets the default lunch break duration.")

    break_duration_hours = fields.Float(
        string="Break Duration (Hours)",
        default=1.0,
        tracking=True,
        help="Lunch/Break duration in hours subtracted from attendance shifts (e.g. 1.0 = 60 min, 0.75 = 45 min, 0.5 = 30 min)."
    )

    allow_annual_leave_lateness_deduction = fields.Boolean(
        string="Accept Annual Deduction",
        default=False,
        tracking=True,
        help="If checked, lateness hours can be deducted from the employee's Annual Leave balance. Requires uploading an approval document."
    )

    annual_deduction_approval_document = fields.Binary(
        string="Approval Document",
        attachment=True,
        help="Upload approval document confirming employee accepts Annual Leave lateness deduction."
    )

    annual_deduction_approval_filename = fields.Char(
        string="Approval Document Filename"
    )

    # Legacy view compatibility aliases
    lunch_break_rule = fields.Selection([
        ('factory', 'Factory / Branches (1.0h Break)'),
        ('office', 'Head Office (0.5h Break)'),
        ('custom', 'Custom Break Duration')
    ], string="Lunch Break Deduction Policy", compute="_compute_legacy_lunch_break_rule", store=False)

    custom_lunch_break_hours = fields.Float(
        related="break_duration_hours",
        string="Custom Lunch Break (Hours)",
        store=False
    )

    def _compute_legacy_lunch_break_rule(self):
        for emp in self:
            if emp.employee_work_station == 'headoffice':
                emp.lunch_break_rule = 'office'
            else:
                emp.lunch_break_rule = 'factory'

    @api.onchange('employee_work_station')
    def _onchange_employee_work_station(self):
        for emp in self:
            if emp.employee_work_station == 'headoffice':
                emp.break_duration_hours = 0.5
            elif emp.employee_work_station in ['retail', 'factory']:
                emp.break_duration_hours = 1.0

    def _get_lunch_break_duration(self):
        """
        Returns the lunch break duration in hours for this employee:
        - Uses the configured break_duration_hours if set (>= 0.0)
        - Otherwise defaults based on employee_work_station (Headoffice: 0.5h, Retail/Factory: 1.0h)
        """
        self.ensure_one()
        if self.break_duration_hours is not None and self.break_duration_hours >= 0.0:
            return self.break_duration_hours
        elif self.employee_work_station == 'headoffice':
            return 0.5
        else:
            return 1.0

    # -------------------------------------------------------------------------
    # ABSENT WORK ENTRY AUTOMATION & 4-DAY MONTHLY GRACE THRESHOLD ENGINE
    # -------------------------------------------------------------------------

    def generate_work_entries(self, date_start, date_stop, force=False):
        """After a force regenerate (Reset), re-apply ABSENT for the full range with monthly 4-day threshold rule."""
        result = super().generate_work_entries(date_start, date_stop, force=force)
        if force:
            employees = self if self else self.search([("active", "=", True)])
            employees._create_absent_work_entries_for_period(date_start, date_stop)
        return result

    @api.model
    def _cron_create_absent_work_entries(self):
        """Daily/Monthly cron: evaluate current/past month up to yesterday and create absent work entries."""
        today = fields.Date.context_today(self)
        yesterday = today - timedelta(days=1)
        first_day_of_month = yesterday.replace(day=1)
        self.search([("active", "=", True)])._create_absent_work_entries_for_period(first_day_of_month, yesterday)

    def _get_absent_work_entry_type(self):
        absent_type = self.env.ref(
            "factory_attendance_payroll.work_entry_type_absent",
            raise_if_not_found=False,
        )
        if not absent_type:
            absent_type = self.env.ref(
                "hr_absent_work_entry_automation.work_entry_type_absent",
                raise_if_not_found=False,
            )
        if not absent_type:
            absent_type = self.env["hr.work.entry.type"].sudo().search([("code", "=", "ABSENT")], limit=1)
        if not absent_type:
            absent_type = self.env["hr.work.entry.type"].sudo().search([("display_code", "=", "ABS")], limit=1)
        if not absent_type:
            absent_type = self.env["hr.work.entry.type"].sudo().create({
                "name": "Absent",
                "display_code": "ABS",
                "code": "ABSENT",
                "color": 1,
                "is_leave": False,
            })
        return absent_type

    def _create_absent_work_entries_for_period(self, date_from, date_to):
        """
        Applies monthly absence evaluation for each employee across the period [date_from, date_to].
        Splits the period by calendar months so the 4-day grace allowance is evaluated strictly per month.
        """
        if not self:
            return
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to)
        if not date_from or not date_to or date_from > date_to:
            return

        # Split [date_from, date_to] into monthly intervals
        months = []
        curr = date_from
        while curr <= date_to:
            next_month = curr.replace(day=28) + timedelta(days=4)
            last_day_of_month = next_month - timedelta(days=next_month.day)
            m_end = min(date_to, last_day_of_month)
            months.append((curr, m_end))
            curr = m_end + timedelta(days=1)

        _logger.info(
            "Factory Absent Automation: evaluating %s employees across %s monthly interval(s) from %s to %s",
            len(self),
            len(months),
            date_from,
            date_to,
        )

        for m_from, m_to in months:
            for employee in self:
                employee._apply_monthly_absence_for_month(m_from, m_to)

    def is_manager_exempt(self):
        """Returns True if the employee is marked as Manager and exempt from overtime/lateness."""
        self.ensure_one()
        for fname in ['x_studio_manager', 'is_manager', 'x_manager']:
            if fname in self._fields and getattr(self, fname):
                return True
        return False

    def _apply_monthly_absence_for_month(self, month_from, month_to):
        """
        Evaluates a single employee for a specific monthly window:
        1. Checks manager / Working Schedule exemption (work_entry_source == 'calendar').
        2. Evaluates each working day in the month up to yesterday.
        3. Identifies candidate un-punched days (expected work hours > 0, NO check-in, NO approved leave/time-off).
        4. Applies 4-Day Monthly Grace Rule:
           - First 4 unpunched days in the month are forgiven (NO absent work entry).
           - 5th unpunched day and all excess days beyond 4 receive an ABSENT work entry.
        """
        self.ensure_one()
        if self.is_manager_exempt():
            return

        versions = self._get_versions_with_contract_overlap_with_period(month_from, month_to)
        if not versions:
            return

        absent_type = self._get_absent_work_entry_type()
        if not absent_type:
            return

        yesterday = fields.Date.context_today(self) - timedelta(days=1)
        eval_to = min(month_to, yesterday)
        if month_from > eval_to:
            return

        candidate_unpunched_days = []
        current = month_from
        while current <= eval_to:
            work_entry_source = self._get_work_entry_source_on_day(current)
            # 1. Calendar (Working Schedule) Mode:
            # Skip automated absence generation; work entries & shift hours are governed by resource calendar.
            if work_entry_source == "calendar":
                current += timedelta(days=1)
                continue

            # 2. Planning Mode:
            # If no planning slot is published on current date, treat as unscheduled day off.
            if work_entry_source == "planning":
                planning_hours = self._get_planning_hours_on_day(current)
                if planning_hours <= 0:
                    current += timedelta(days=1)
                    continue

            # 3. Attendance Mode (Factory Workers / 6 Days + 1 RestDay):
            expected_hours = self._get_expected_hours_on_day(current)
            if expected_hours <= 0:
                # Non-working day (standard calendar weekend or rest day)
                current += timedelta(days=1)
                continue

            # Check if employee has attendance check-in
            if self._has_checkin_on_day(current):
                current += timedelta(days=1)
                continue

            # Check if employee has approved Time Off / Leave (Silver color in UI)
            if self._has_approved_leave_on_day(current):
                current += timedelta(days=1)
                continue

            # No check-in, No approved leave, and Expected hours > 0 -> Candidate unpunched day!
            candidate_unpunched_days.append((current, expected_hours))
            current += timedelta(days=1)

        # 4-Day Monthly Grace Threshold Rule:
        # If total unpunched days <= 4: All days are forgiven (0 absent entries created).
        # If total unpunched days > 4: First 4 days are forgiven; Days from index 4 onwards (5th day+) get ABSENT.
        allowed_grace_days = 4

        # Clean up / remove any unvalidated ABSENT work entries on the forgiven days (first 4 days)
        forgiven_days = [d[0] for d in candidate_unpunched_days[:allowed_grace_days]]
        if forgiven_days:
            forgiven_we = self.env["hr.work.entry"].sudo().search([
                ("employee_id", "=", self.id),
                ("date", "in", forgiven_days),
                ("work_entry_type_id", "=", absent_type.id),
                ("state", "!=", "validated"),
            ])
            if forgiven_we:
                forgiven_we.unlink()

        # Mark excess days (Day 5 onwards) with ABSENT work entries
        excess_absent_days = candidate_unpunched_days[allowed_grace_days:]
        for target_date, exp_hours in excess_absent_days:
            self._apply_absence_for_day(target_date, exp_hours, absent_type)

    def _apply_absence_for_day(self, target_date, duration, absent_type):
        self.ensure_one()
        work_entry_model = self.env["hr.work.entry"].sudo()
        existing_work_entries = work_entry_model.search([
            ("employee_id", "=", self.id),
            ("date", "=", target_date),
            ("state", "!=", "cancelled"),
            ("work_entry_type_id.is_leave", "=", False),
        ])

        if existing_work_entries:
            editable_work_entries = existing_work_entries.filtered(lambda we: we.state != "validated")
            if editable_work_entries:
                editable_work_entries.write({"work_entry_type_id": absent_type.id})
                _logger.info(
                    "Factory Absent Automation: updated %s work entries to ABSENT for employee=%s(%s) date=%s",
                    len(editable_work_entries),
                    self.name,
                    self.id,
                    target_date,
                )
            return

        if work_entry_model.search_count([
            ("employee_id", "=", self.id),
            ("date", "=", target_date),
            ("state", "!=", "cancelled"),
            ("work_entry_type_id", "=", absent_type.id),
        ]):
            return

        dur = min(round(duration, 2), 24.0)
        if dur <= 0:
            return

        version = self._get_versions_with_contract_overlap_with_period(target_date, target_date)[:1]
        if not version:
            return

        work_entry_model.create({
            "employee_id": self.id,
            "version_id": version.id,
            "date": target_date,
            "duration": dur,
            "work_entry_type_id": absent_type.id,
            "company_id": self.company_id.id,
        })
        _logger.info(
            "Factory Absent Automation: created ABSENT work entry for employee=%s(%s) date=%s duration=%s",
            self.name,
            self.id,
            target_date,
            dur,
        )

    def _has_approved_leave_on_day(self, target_date):
        """
        Checks whether the employee has an approved Time Off / Leave (Silver color in UI) on target_date:
        1. Approved hr.leave in states ['validate', 'validate1'].
        2. Existing leave work entry in hr.work.entry (is_leave=True or excused leave code).
        3. Resource calendar global leaves / public holidays.
        """
        self.ensure_one()
        day_start_utc, next_day_start_utc, _employee_tz = self._get_day_utc_bounds(target_date)

        # 1. Check hr.leave records with approved/validated state (excluding settlement deduction records)
        if "hr.leave" in self.env:
            leaves_count = self.env["hr.leave"].sudo().search_count([
                ("employee_id", "=", self.id),
                ("state", "in", ["validate", "validate1"]),
                ("date_from", "<", fields.Datetime.to_string(next_day_start_utc)),
                ("date_to", ">", fields.Datetime.to_string(day_start_utc)),
                "!", ("name", "ilike", "Lateness Settlement"),
            ])
            if leaves_count > 0:
                return True

        # 2. Check hr.work.entry for existing leave work entries
        work_entries = self.env["hr.work.entry"].sudo().search([
            ("employee_id", "=", self.id),
            ("date", "=", target_date),
            ("state", "!=", "cancelled"),
        ])
        for we in work_entries:
            type_obj = we.work_entry_type_id
            if not type_obj:
                continue
            if type_obj.is_leave:
                return True
            code = (type_obj.code or "").strip().upper()
            display_code = (getattr(type_obj, "display_code", False) or "").strip().upper()
            name = (type_obj.name or "").strip().upper()
            if (code in EXCUSED_LEAVE_WORK_ENTRY_CODES or display_code in EXCUSED_LEAVE_WORK_ENTRY_CODES or
                any(c in code or c in display_code or c in name for c in ["RST", "RESTDAY", "REST_DAY"])):
                return True

        # 3. Check resource calendar global leaves / public holidays
        if self._is_public_holiday_on_day(target_date):
            return True

        return False

    def _is_public_holiday_on_day(self, target_date):
        """
        Checks whether target_date is a Public Holiday / Global Leave in resource.calendar.leaves
        for the employee's calendar or company calendar.
        """
        self.ensure_one()
        if not target_date or "resource.calendar.leaves" not in self.env:
            return False
        dt_start = fields.Datetime.to_string(datetime.datetime.combine(target_date, datetime.time.min))
        dt_end = fields.Datetime.to_string(datetime.datetime.combine(target_date, datetime.time.max))

        calendar_ids = set()
        if self.resource_calendar_id:
            calendar_ids.add(self.resource_calendar_id.id)
        if self.company_id and self.company_id.resource_calendar_id:
            calendar_ids.add(self.company_id.resource_calendar_id.id)
        calendar_list = [False] + list(calendar_ids)

        return bool(self.env["resource.calendar.leaves"].sudo().search_count([
            ("calendar_id", "in", calendar_list),
            ("resource_id", "in", [False, self.resource_id.id if self.resource_id else False]),
            ("date_from", "<=", dt_end),
            ("date_to", ">=", dt_start),
        ]))

    def _has_checkin_on_day(self, target_date):
        """Checks if the employee has any attendance check-in recorded on target_date."""
        self.ensure_one()
        day_start, next_day_start, _employee_tz = self._get_day_utc_bounds(target_date)
        return bool(self.env["hr.attendance"].sudo().search_count([
            ("employee_id", "=", self.id),
            ("check_in", ">=", fields.Datetime.to_string(day_start)),
            ("check_in", "<", fields.Datetime.to_string(next_day_start)),
        ]))

    def _get_work_entry_source_on_day(self, target_date):
        self.ensure_one()
        version = self._get_versions_with_contract_overlap_with_period(target_date, target_date)[:1]
        if not version:
            return False
        return (version.work_entry_source or "").strip()

    def _get_expected_hours_on_day(self, target_date):
        """Return expected net work hours (after break deduction) based on contract work entry source (planning vs calendar)."""
        self.ensure_one()
        source = self._get_work_entry_source_on_day(target_date)
        if source == "planning":
            gross_hrs = self._get_planning_hours_on_day(target_date)
        else:
            gross_hrs = self._get_calendar_hours_on_day(target_date)

        if gross_hrs <= 0:
            return 0.0

        break_hrs = self._get_lunch_break_duration()
        if gross_hrs >= 6.0:
            return max(0.0, gross_hrs - break_hrs)
        elif gross_hrs > 4.0:
            return max(0.0, gross_hrs - (break_hrs / 2.0))
        return gross_hrs

    def _get_day_utc_bounds(self, target_date):
        self.ensure_one()
        calendar = self.resource_calendar_id or self.company_id.resource_calendar_id
        tz_name = (calendar and calendar.tz) or self.tz or "UTC"
        employee_tz = pytz.timezone(tz_name)
        day_start_local = employee_tz.localize(datetime.combine(target_date, time.min))
        next_day_start_local = employee_tz.localize(datetime.combine(target_date + timedelta(days=1), time.min))
        day_start_utc = day_start_local.astimezone(pytz.utc).replace(tzinfo=None)
        next_day_start_utc = next_day_start_local.astimezone(pytz.utc).replace(tzinfo=None)
        return day_start_utc, next_day_start_utc, employee_tz

    def _get_planning_hours_on_day(self, target_date):
        self.ensure_one()
        if "planning.slot" not in self.env or not self.resource_id:
            return 0.0

        start_dt, end_dt, _employee_tz = self._get_day_utc_bounds(target_date)
        slots = self.env["planning.slot"].sudo().search([
            ("resource_id", "=", self.resource_id.id),
            ("start_datetime", "<", end_dt),
            ("end_datetime", ">", start_dt),
        ])

        total_hours = 0.0
        for slot in slots:
            overlap_start = max(slot.start_datetime, start_dt)
            overlap_end = min(slot.end_datetime, end_dt)
            if overlap_end > overlap_start:
                total_hours += (overlap_end - overlap_start).total_seconds() / 3600.0
        return total_hours

    def _get_calendar_hours_on_day(self, target_date):
        self.ensure_one()
        version = self._get_versions_with_contract_overlap_with_period(target_date, target_date)[:1]
        if not version:
            return 0.0

        calendar = version.resource_calendar_id or self.resource_calendar_id or self.company_id.resource_calendar_id
        if not calendar:
            return 0.0

        day_start_utc, day_end_utc, employee_tz = self._get_day_utc_bounds(target_date)
        day_start_utc = pytz.utc.localize(day_start_utc)
        day_end_utc = pytz.utc.localize(day_end_utc)

        resource = self.resource_id
        intervals_by_resource = calendar._attendance_intervals_batch(
            day_start_utc,
            day_end_utc,
            resources=resource,
            tz=employee_tz,
        )
        intervals = intervals_by_resource.get(resource.id if resource else False)
        if not intervals:
            return 0.0

        total_hours = 0.0
        for interval_start, interval_end, _attendance in intervals._items:
            if interval_end > interval_start:
                total_hours += (interval_end - interval_start).total_seconds() / 3600.0
        return total_hours
