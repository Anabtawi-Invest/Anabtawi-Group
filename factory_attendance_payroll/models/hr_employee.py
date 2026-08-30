# -*- coding: utf-8 -*-

from collections import defaultdict
from datetime import datetime, time, timedelta
import logging
import pytz

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

EXCUSED_LEAVE_WORK_ENTRY_CODES = [
    "GTO", "CTO", "HW", "STO", "PTO", "SIK", "ANU", "PHD", "BFV", "HIL",
    "FWS", "DIE", "MRD", "NPO", "PID", "HAJ", "MAM", "LDO", "TRV", "MKA", "BRK", "UNP", "ARS", "RST", "RESTDAY", "RestDay", "REST_DAY",
    "LEAVE100", "LEAVE105", "WORK110", "LEAVE110", "LEAVE120", "SICKLEAVE0",
    "An_le", "un_paid", "REST", "RST", "RESTDAY", "RestDay", "REST_DAY",
    "LEAVE", "SICK", "VAC", "ANNUAL", "UNPAID", "HOLIDAY", "REST_DAY", "RESTDAY", "RestDay",
]

ABSENT_WORK_ENTRY_CODES = ["ABS", "ABSENT", "A"]


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
        - Uses configured break_duration_hours if set (>= 0.0)
        - Otherwise defaults based on employee_work_station (Headoffice: 0.5h, Retail/Factory: 1.0h)
        """
        self.ensure_one()
        if self.break_duration_hours is not None and self.break_duration_hours >= 0.0:
            return self.break_duration_hours
        elif self.employee_work_station == 'headoffice':
            return 0.5
        else:
            return 1.0

    def is_manager_exempt(self):
        """Returns True if the employee is marked as Manager and exempt from overtime/lateness."""
        self.ensure_one()
        for fname in ['x_studio_manager', 'is_manager', 'x_manager']:
            if fname in self._fields and getattr(self, fname):
                return True
        return False

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
        Uses high-performance batch pre-fetching to eliminate N+1 database queries.
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

        emp_ids = self.ids
        dt_start = datetime.combine(date_from, time.min)
        dt_end = datetime.combine(date_to, time.max)

        # Batch Pre-fetch 1: Public holidays in range
        public_holiday_dates = self.env['hr.attendance']._get_public_holiday_dates_batch(date_from, date_to)

        # Batch Pre-fetch 2: Attendances (emp_id, check_in_date)
        attendances = self.env['hr.attendance'].sudo().search([
            ('employee_id', 'in', emp_ids),
            ('check_in', '>=', dt_start),
            ('check_in', '<=', dt_end),
        ])
        checked_in_keys = set((att.employee_id.id, att.check_in.date()) for att in attendances if att.check_in)

        # Batch Pre-fetch 3: Approved Leaves (emp_id, leave_date)
        approved_leave_keys = set()
        if "hr.leave" in self.env:
            leaves = self.env["hr.leave"].sudo().search([
                ("employee_id", "in", emp_ids),
                ("state", "in", ["validate", "validate1"]),
                ("date_from", "<=", fields.Datetime.to_string(dt_end)),
                ("date_to", ">=", fields.Datetime.to_string(dt_start)),
                "!", ("name", "ilike", "Lateness Settlement"),
            ])
            for lve in leaves:
                d_curr = lve.date_from.date()
                d_last = lve.date_to.date()
                while d_curr <= d_last:
                    if date_from <= d_curr <= date_to:
                        approved_leave_keys.add((lve.employee_id.id, d_curr))
                    d_curr += timedelta(days=1)

        # Batch Pre-fetch 4: Leave Work Entries
        dt_start_we = datetime.combine(date_from, time.min)
        dt_end_we = datetime.combine(date_to, time.max)
        work_entries = self.env["hr.work.entry"].sudo().search([
            ("employee_id", "in", emp_ids),
            ("date_start", ">=", dt_start_we),
            ("date_start", "<=", dt_end_we),
            ("state", "!=", "cancelled"),
        ])
        for we in work_entries:
            type_obj = we.work_entry_type_id
            if not type_obj:
                continue
            code = (type_obj.code or "").strip().upper()
            display_code = (getattr(type_obj, "display_code", False) or "").strip().upper()
            name = (type_obj.name or "").strip().upper()
            if type_obj.is_leave or code in EXCUSED_LEAVE_WORK_ENTRY_CODES or display_code in EXCUSED_LEAVE_WORK_ENTRY_CODES or \
               any(c in code or c in display_code or c in name for c in ["RST", "RESTDAY", "REST_DAY"]):
                we_date = we.date_start.date() if we.date_start else False
                if we_date:
                    approved_leave_keys.add((we.employee_id.id, we_date))

        absent_type = self._get_absent_work_entry_type()
        yesterday = fields.Date.context_today(self) - timedelta(days=1)

        for m_from, m_to in months:
            eval_to = min(m_to, yesterday)
            if m_from > eval_to:
                continue

            for employee in self:
                if employee.is_manager_exempt():
                    continue

                candidate_unpunched_days = []
                current = m_from
                while current <= eval_to:
                    emp_key = (employee.id, current)

                    # Public Holiday -> No absence
                    if current in public_holiday_dates:
                        current += timedelta(days=1)
                        continue

                    # Has check-in -> No absence
                    if emp_key in checked_in_keys:
                        current += timedelta(days=1)
                        continue

                    # Has approved leave / time off -> No absence
                    if emp_key in approved_leave_keys:
                        current += timedelta(days=1)
                        continue

                    # Expected hours (standard 8h)
                    expected_hours = employee._get_expected_hours_on_day(current)
                    if expected_hours <= 0:
                        current += timedelta(days=1)
                        continue

                    candidate_unpunched_days.append((current, expected_hours))
                    current += timedelta(days=1)

                # 4-Day Monthly Grace Threshold Rule:
                # First 4 unpunched days in month forgiven; 5th+ day receives ABSENT entry
                allowed_grace_days = 4
                forgiven_days = [d[0] for d in candidate_unpunched_days[:allowed_grace_days]]
                if forgiven_days:
                    min_forgiven_dt = datetime.combine(min(forgiven_days), time.min)
                    max_forgiven_dt = datetime.combine(max(forgiven_days), time.max)
                    forgiven_we = self.env["hr.work.entry"].sudo().search([
                        ("employee_id", "=", employee.id),
                        ("date_start", ">=", min_forgiven_dt),
                        ("date_start", "<=", max_forgiven_dt),
                        ("work_entry_type_id", "=", absent_type.id),
                        ("state", "!=", "validated"),
                    ]).filtered(lambda w: w.date_start and w.date_start.date() in forgiven_days)
                    if forgiven_we:
                        forgiven_we.unlink()

                excess_absent_days = candidate_unpunched_days[allowed_grace_days:]
                for target_date, exp_hours in excess_absent_days:
                    employee._apply_absence_for_day(target_date, exp_hours, absent_type)

    def _apply_absence_for_day(self, target_date, duration, absent_type):
        self.ensure_one()
        dur = min(round(duration, 2), 24.0)
        if dur <= 0.01:
            return

        dt_day_start = datetime.combine(target_date, time.min)
        dt_day_end = datetime.combine(target_date, time.max)
        dt_start_val = datetime.combine(target_date, time(8, 0, 0))
        dt_stop_val = dt_start_val + timedelta(hours=dur)

        work_entry_model = self.env["hr.work.entry"].sudo()
        existing_work_entries = work_entry_model.search([
            ("employee_id", "=", self.id),
            ("date_start", ">=", dt_day_start),
            ("date_start", "<=", dt_day_end),
            ("state", "!=", "cancelled"),
            ("work_entry_type_id.is_leave", "=", False),
        ])

        if existing_work_entries:
            editable_work_entries = existing_work_entries.filtered(lambda we: we.state != "validated")
            if editable_work_entries:
                update_vals = {"work_entry_type_id": absent_type.id, "duration": dur}
                if "date_start" in work_entry_model._fields:
                    update_vals["date_start"] = dt_start_val
                if "date_stop" in work_entry_model._fields:
                    update_vals["date_stop"] = dt_stop_val
                editable_work_entries.write(update_vals)
            return

        if work_entry_model.search_count([
            ("employee_id", "=", self.id),
            ("date_start", ">=", dt_day_start),
            ("date_start", "<=", dt_day_end),
            ("state", "!=", "cancelled"),
            ("work_entry_type_id", "=", absent_type.id),
        ]):
            return

        version = self._get_versions_with_contract_overlap_with_period(target_date, target_date)[:1]
        if not version:
            return

        we_vals = {
            "employee_id": self.id,
            "version_id": version.id,
            "date_start": dt_start_val,
            "date_stop": dt_stop_val,
            "duration": dur,
            "work_entry_type_id": absent_type.id,
            "company_id": self.company_id.id,
        }
        if "name" in work_entry_model._fields:
            we_vals["name"] = f"Absent: {self.name} - {target_date}"

        work_entry_model.create(we_vals)

    def _get_day_utc_bounds(self, target_date):
        """Returns UTC bounds (start, next_day_start) for target_date according to employee tz."""
        self.ensure_one()
        tz_name = self.tz or self.company_id.tz or "UTC"
        try:
            employee_tz = pytz.timezone(tz_name)
        except Exception:
            employee_tz = pytz.UTC
        day_start_local = employee_tz.localize(datetime.combine(target_date, time.min))
        next_day_start_local = day_start_local + timedelta(days=1)
        day_start_utc = day_start_local.astimezone(pytz.UTC).replace(tzinfo=None)
        next_day_start_utc = next_day_start_local.astimezone(pytz.UTC).replace(tzinfo=None)
        return day_start_utc, next_day_start_utc, employee_tz

    def _get_versions_with_contract_overlap_with_period(self, date_from, date_to):
        """Returns contract versions covering the specified period for all employees in self."""
        if hasattr(super(), '_get_versions_with_contract_overlap_with_period'):
            try:
                return super()._get_versions_with_contract_overlap_with_period(date_from, date_to)
            except Exception:
                pass
        if not self:
            return self.env['hr.contract'] if 'hr.contract' in self.env else self.env['hr.employee']
        if "hr.contract" in self.env:
            domain = [
                ("employee_id", "in", self.ids),
                ("state", "in", ["open", "close"]),
                ("date_start", "<=", date_to),
                "|",
                ("date_end", "=", False),
                ("date_end", ">=", date_from),
            ]
            return self.env["hr.contract"].sudo().search(domain, order="date_start desc")
        return self.env["hr.employee"]

    def _get_work_entry_source_on_day(self, target_date):
        self.ensure_one()
        version = self._get_versions_with_contract_overlap_with_period(target_date, target_date)[:1]
        if not version:
            return "attendance"
        return (getattr(version, 'work_entry_source', False) or "attendance").strip()

    def _get_expected_hours_on_day(self, target_date):
        """Return expected net work hours based on contract work entry source (planning vs calendar vs attendance)."""
        self.ensure_one()
        source = self._get_work_entry_source_on_day(target_date)
        if source == "planning":
            return self._get_planning_hours_on_day(target_date)
        elif source == "calendar" and self.resource_calendar_id:
            return 8.0
        return 8.0

    def _get_planning_hours_on_day(self, target_date):
        """Get total published planning shift hours on target_date if planning module is installed."""
        self.ensure_one()
        if "planning.slot" not in self.env:
            return 0.0
        day_start_utc, next_day_start_utc, _employee_tz = self._get_day_utc_bounds(target_date)
        slots = self.env["planning.slot"].sudo().search([
            ("employee_id", "=", self.id),
            ("state", "=", "published"),
            ("start_datetime", "<", fields.Datetime.to_string(next_day_start_utc)),
            ("end_datetime", ">", fields.Datetime.to_string(day_start_utc)),
        ])
        return sum(slot.allocated_hours for slot in slots)
