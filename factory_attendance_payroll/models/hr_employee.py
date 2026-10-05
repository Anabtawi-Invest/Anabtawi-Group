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
    "LEAVE100", "LEAVE105", "WORK110", "LEAVE110", "LEAVE120", "LEAVE500", "SICKLEAVE0",
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
        d_start = fields.Date.to_date(date_start)
        d_stop = fields.Date.to_date(date_stop)
        
        WEModel = self.env["hr.work.entry"].sudo()
        emp_ids = self.ids if self else self.search([("active", "=", True)]).ids

        def _get_we_date_domain(d_from_val, d_to_val):
            dom = []
            if "date" in WEModel._fields:
                dom += [("date", ">=", d_from_val), ("date", "<=", d_to_val)]
            elif "date_start" in WEModel._fields:
                dt_from = datetime.combine(d_from_val, time.min)
                dt_to = datetime.combine(d_to_val, time.max)
                dom += [("date_start", ">=", dt_from), ("date_start", "<=", dt_to)]
            elif "date_from" in WEModel._fields:
                dt_from = datetime.combine(d_from_val, time.min)
                dt_to = datetime.combine(d_to_val, time.max)
                dom += [("date_from", ">=", dt_from), ("date_from", "<=", dt_to)]
            return dom

        # Clean up any legacy corrupt work entries with invalid duration (<= 0 or > 24h) before regeneration
        if emp_ids and d_start and d_stop:
            corrupt_domain = [
                ("employee_id", "in", emp_ids),
                ("state", "!=", "validated"),
                "|", ("duration", "<=", 0.0), ("duration", ">", 24.0),
            ] + _get_we_date_domain(d_start, d_stop)
            corrupt_entries = WEModel.search(corrupt_domain)
            if corrupt_entries:
                corrupt_entries.unlink()

        try:
            result = super().generate_work_entries(date_start, date_stop, force=force)
        except Exception as e:
            _logger.warning(f"Standard generate_work_entries warning: {e}")
            result = True

        if force:
            employees = self if self else self.search([("active", "=", True)])
            employees._create_absent_work_entries_for_period(date_start, date_stop)

        # Final cleanup pass for any 0h or >24h entries generated by standard calendar hooks
        if emp_ids and d_start and d_stop:
            bad_domain = [
                ("employee_id", "in", emp_ids),
                ("state", "!=", "validated"),
                "|", ("duration", "<=", 0.0), ("duration", ">", 24.0),
            ] + _get_we_date_domain(d_start, d_stop)
            bad_entries = WEModel.search(bad_domain)
            if bad_entries:
                bad_entries.unlink()

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
                "round_days": "NO",
                "round_days_type": "DOWN",
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
                we_type = lve.holiday_status_id.work_entry_type_id if lve.holiday_status_id and lve.holiday_status_id.work_entry_type_id else False
                while d_curr <= d_last:
                    if date_from <= d_curr <= date_to:
                        approved_leave_keys.add((lve.employee_id.id, d_curr))
                        if we_type:
                            lve.employee_id._ensure_leave_work_entry_for_day(d_curr, we_type)
                    d_curr += timedelta(days=1)

        # Batch Pre-fetch 4: Leave Work Entries
        WEModel = self.env["hr.work.entry"]
        we_domain = [
            ("employee_id", "in", emp_ids),
            ("state", "!=", "cancelled"),
        ]
        if "date" in WEModel._fields:
            we_domain += [("date", ">=", date_from), ("date", "<=", date_to)]
        elif "date_start" in WEModel._fields:
            we_domain += [
                ("date_start", ">=", datetime.combine(date_from, time.min)),
                ("date_start", "<=", datetime.combine(date_to, time.max)),
            ]
        work_entries = WEModel.sudo().search(we_domain)
        for we in work_entries:
            type_obj = we.work_entry_type_id
            if not type_obj:
                continue
            code = (type_obj.code or "").strip().upper()
            display_code = (getattr(type_obj, "display_code", False) or "").strip().upper()
            name = (type_obj.name or "").strip().upper()
            is_absent = (type_obj.id == absent_type.id) if 'absent_type' in locals() and absent_type else False
            if not is_absent:
                is_absent = code in ["ABSENT", "ABS"] or display_code in ["ABSENT", "ABS"] or name == "ABSENT"
            if not is_absent:
                we_date = getattr(we, "date", False) or (we.date_start.date() if hasattr(we, "date_start") and we.date_start else False)
                if isinstance(we_date, datetime):
                    we_date = we_date.date()
                if we_date:
                    approved_leave_keys.add((we.employee_id.id, we_date))

        # Batch Pre-fetch 5: Employee Contracts
        cached_contracts = defaultdict(list)
        if "hr.contract" in self.env:
            contracts = self.env["hr.contract"].sudo().search([
                ("employee_id", "in", emp_ids),
                ("state", "in", ["open", "close"]),
                ("date_start", "<=", date_to),
                "|",
                ("date_end", "=", False),
                ("date_end", ">=", date_from),
            ], order="date_start desc")
            for c in contracts:
                cached_contracts[c.employee_id.id].append(c)

        self = self.with_context(cached_contracts=cached_contracts)
        absent_type = self._get_absent_work_entry_type()
        yesterday = fields.Date.context_today(self) - timedelta(days=1)

        for m_from, m_to in months:
            eval_to = m_to
            if m_from > eval_to:
                continue

            for employee in self:
                candidate_unpunched_days = []
                emp_contracts = cached_contracts.get(employee.id, [])
                c_vers = employee._get_versions_with_contract_overlap_with_period(m_from, m_to) if hasattr(employee, '_get_versions_with_contract_overlap_with_period') else []
                active_contracts = c_vers or emp_contracts

                current = m_from
                while current <= eval_to:
                    emp_key = (employee.id, current)

                    # Out of Contract -> No absence (do not count days before contract start or after contract end as absent)
                    is_covered = any(
                        (getattr(c, 'date_start', None) and c.date_start <= current) and
                        (not getattr(c, 'date_end', None) or c.date_end >= current)
                        for c in active_contracts
                    ) if active_contracts else True

                    if not is_covered:
                        employee._remove_absence_for_day(current, absent_type)
                        current += timedelta(days=1)
                        continue

                    # Public Holiday -> No absence
                    if current in public_holiday_dates:
                        employee._remove_absence_for_day(current, absent_type)
                        current += timedelta(days=1)
                        continue

                    # Has check-in -> No absence
                    if emp_key in checked_in_keys:
                        employee._remove_absence_for_day(current, absent_type)
                        current += timedelta(days=1)
                        continue

                    # Has approved leave / time off (Unpaid, Sick, Annual, etc.) -> No absence
                    if emp_key in approved_leave_keys:
                        employee._remove_absence_for_day(current, absent_type)
                        current += timedelta(days=1)
                        continue

                    # Expected hours (standard 8h)
                    expected_hours = employee._get_expected_hours_on_day(current)
                    if expected_hours <= 0:
                        current += timedelta(days=1)
                        continue

                    candidate_unpunched_days.append((current, expected_hours))
                    current += timedelta(days=1)

                is_flexible = getattr(employee.resource_calendar_id, 'flexible_hours', False) or getattr(employee, 'flexible_hours', False)
                work_station = getattr(employee, 'employee_work_station', False) or 'factory'

                rest_dates_to_skip = set()
                if is_flexible or work_station != 'headoffice':
                    target_weekday = 0 if work_station == 'factory' else 4
                    emp_checkins = sum(1 for (e_id, d) in checked_in_keys if e_id == employee.id and m_from <= d <= m_to)
                    month_target_weekdays = sum(1 for d_idx in range((m_to - m_from).days + 1) if (m_from + timedelta(days=d_idx)).weekday() == target_weekday)
                    earned_rest_days = min(month_target_weekdays, emp_checkins // 6) if emp_checkins > 0 else month_target_weekdays

                    primary_rest = [d for (d, h) in candidate_unpunched_days if d.weekday() == target_weekday]
                    selected_rest = list(primary_rest[:earned_rest_days])

                    if len(selected_rest) < earned_rest_days:
                        needed = earned_rest_days - len(selected_rest)
                        other_unpunched = [d for (d, h) in candidate_unpunched_days if d not in set(selected_rest)]
                        selected_rest.extend(other_unpunched[:needed])

                    rest_dates_to_skip = set(selected_rest)

                # Generate ABSENT work entries for candidate unpunched working days, leaving rest days empty
                for target_date, exp_hours in candidate_unpunched_days:
                    if target_date in rest_dates_to_skip:
                        employee._remove_absence_for_day(target_date, absent_type)
                    else:
                        employee._apply_absence_for_day(target_date, exp_hours, absent_type)

    def _remove_absence_for_day(self, target_date, absent_type):
        self.ensure_one()
        work_entry_model = self.env["hr.work.entry"].sudo()
        day_domain = [
            ("employee_id", "=", self.id),
            ("state", "!=", "validated"),
        ]
        if "date" in work_entry_model._fields:
            day_domain += [("date", "=", target_date)]
        elif "date_start" in work_entry_model._fields:
            day_domain += [
                ("date_start", ">=", datetime.combine(target_date, time.min)),
                ("date_start", "<=", datetime.combine(target_date, time.max)),
            ]
        existing_absent = work_entry_model.search(day_domain).filtered(
            lambda we: we.work_entry_type_id and ((we.work_entry_type_id.code or '').strip().upper() in ["ABSENT", "ABS", "ARS", "REST", "RESTDAY"] or (absent_type and we.work_entry_type_id.id == absent_type.id))
        )
        if existing_absent:
            existing_absent.unlink()

    def _ensure_leave_work_entry_for_day(self, target_date, work_entry_type):
        self.ensure_one()
        if not work_entry_type:
            return
        WEModel = self.env["hr.work.entry"].sudo()
        day_domain = [
            ("employee_id", "=", self.id),
            ("state", "!=", "cancelled"),
        ]
        if "date" in WEModel._fields:
            day_domain += [("date", "=", target_date)]
        elif "date_start" in WEModel._fields:
            day_domain += [
                ("date_start", ">=", datetime.combine(target_date, time.min)),
                ("date_start", "<=", datetime.combine(target_date, time.max)),
            ]
        existing = WEModel.search(day_domain)
        matching_leave_we = existing.filtered(lambda w: w.work_entry_type_id and w.work_entry_type_id.id == work_entry_type.id)
        if matching_leave_we:
            return

        absent_we = existing.filtered(
            lambda w: w.work_entry_type_id and (w.work_entry_type_id.code or '').strip().upper() in ["ABSENT", "ABS"]
        )
        if absent_we:
            absent_we.unlink()

        t_start = datetime.combine(target_date, time(8, 0, 0))
        dur_hrs = 9.0 if (work_entry_type.code or '').strip().upper() in ['UNPAID', 'LEAVE500', 'UNP'] or 'unpaid' in (work_entry_type.name or '').lower() else 8.0
        t_stop = t_start + timedelta(hours=dur_hrs)
        vals = {
            "name": f"{self.name}: {work_entry_type.name}",
            "employee_id": self.id,
            "work_entry_type_id": work_entry_type.id,
            "duration": dur_hrs,
            "state": "draft",
        }
        if "date" in WEModel._fields:
            vals["date"] = target_date
        if "date_start" in WEModel._fields:
            vals["date_start"] = t_start
        if "date_stop" in WEModel._fields:
            vals["date_stop"] = t_stop
        if "company_id" in WEModel._fields:
            vals["company_id"] = self.company_id.id if self.company_id else self.env.company.id

        WEModel.create(vals)

    def _apply_absence_for_day(self, target_date, duration, absent_type):
        self.ensure_one()
        dur = max(0.01, min(round(duration, 2), 24.0))
        if dur <= 0.01:
            return

        work_entry_model = self.env["hr.work.entry"].sudo()
        day_domain = [
            ("employee_id", "=", self.id),
            ("state", "!=", "cancelled"),
        ]
        if "date" in work_entry_model._fields:
            day_domain += [("date", "=", target_date)]
        elif "date_start" in work_entry_model._fields:
            day_domain += [
                ("date_start", ">=", datetime.combine(target_date, time.min)),
                ("date_start", "<=", datetime.combine(target_date, time.max)),
            ]
        existing_work_entries = work_entry_model.search(day_domain)

        t_start = datetime.combine(target_date, time(8, 0, 0))
        t_stop = t_start + timedelta(hours=dur)

        if existing_work_entries:
            non_absent = existing_work_entries.filtered(
                lambda we: we.work_entry_type_id and (we.work_entry_type_id.code or '').strip().upper() not in ["ABSENT", "ABS"] and (not absent_type or we.work_entry_type_id.id != absent_type.id)
            )
            if non_absent:
                return
            editable_work_entries = existing_work_entries.filtered(lambda we: we.state != "validated")
            if editable_work_entries:
                update_vals = {"work_entry_type_id": absent_type.id, "duration": dur}
                if "date_start" in work_entry_model._fields:
                    update_vals["date_start"] = t_start
                if "date_stop" in work_entry_model._fields:
                    update_vals["date_stop"] = t_stop
                editable_work_entries.write(update_vals)
            return

        cnt_domain = [
            ("employee_id", "=", self.id),
            ("state", "!=", "cancelled"),
            ("work_entry_type_id", "=", absent_type.id),
        ]
        if "date" in work_entry_model._fields:
            cnt_domain += [("date", "=", target_date)]
        elif "date_start" in work_entry_model._fields:
            cnt_domain += [
                ("date_start", ">=", datetime.combine(target_date, time.min)),
                ("date_start", "<=", datetime.combine(target_date, time.max)),
            ]
        if work_entry_model.search_count(cnt_domain):
            return

        version = self._get_versions_with_contract_overlap_with_period(target_date, target_date)[:1]
        if not version:
            return

        we_vals = {
            "employee_id": self.id,
            "version_id": version.id,
            "duration": dur,
            "work_entry_type_id": absent_type.id,
            "company_id": self.company_id.id,
        }
        if "date" in work_entry_model._fields:
            we_vals["date"] = target_date
        if "date_start" in work_entry_model._fields:
            we_vals["date_start"] = datetime.combine(target_date, time(8, 0, 0))
        if "date_stop" in work_entry_model._fields:
            we_vals["date_stop"] = datetime.combine(target_date, time(8, 0, 0)) + timedelta(hours=dur)
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
        cached = self.env.context.get('cached_contracts')
        if cached is not None and "hr.contract" in self.env:
            res = self.env['hr.contract']
            for emp_id in self.ids:
                for c in cached.get(emp_id, []):
                    c_start = c.date_start
                    c_end = c.date_end
                    if c_start and c_start <= date_to and (not c_end or c_end >= date_from):
                        res |= c
            return res.sorted('date_start', reverse=True)
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
        """Return expected net work hours based on contract work entry source (planning vs calendar vs attendance). Returns 0.0 if out of contract."""
        self.ensure_one()
        version = self._get_versions_with_contract_overlap_with_period(target_date, target_date)[:1]
        if not version:
            return 0.0
        source = (getattr(version, 'work_entry_source', False) or "attendance").strip()
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
