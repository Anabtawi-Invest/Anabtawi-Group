# -*- coding: utf-8 -*-

from collections import defaultdict
from datetime import datetime, time, timedelta
import logging
import pytz

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


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
        help="Lunch/Break duration in hours subtracted from attendance shifts (e.g. 1.0 = 60 min, 0.5 = 30 min)."
    )

    allow_annual_leave_lateness_deduction = fields.Boolean(
        string="Accept Annual Deduction",
        default=True,
        tracking=True,
        help="If checked, lateness hours can be deducted from the employee's Annual Leave balance (Step 2)."
    )

    annual_deduction_approval_document = fields.Binary(
        string="Approval Document",
        attachment=True,
        help="Approval document confirming employee accepts Annual Leave lateness deduction."
    )

    annual_deduction_approval_filename = fields.Char(
        string="Approval Document Filename"
    )

    @api.onchange('employee_work_station')
    def _onchange_employee_work_station(self):
        for emp in self:
            if emp.employee_work_station == 'headoffice':
                emp.break_duration_hours = 0.5
            elif emp.employee_work_station in ['retail', 'factory']:
                emp.break_duration_hours = 1.0

    def _get_lunch_break_duration(self):
        """Returns configured break duration in hours."""
        self.ensure_one()
        if self.break_duration_hours is not None and self.break_duration_hours >= 0.0:
            return self.break_duration_hours
        elif self.employee_work_station == 'headoffice':
            return 0.5
        else:
            return 1.0

    def is_manager_exempt(self):
        """Returns True if the employee is marked as Manager and exempt from hourly lateness/overtime deductions."""
        self.ensure_one()
        for fname in ['x_studio_manager', 'is_manager', 'x_manager']:
            if fname in self._fields and getattr(self, fname):
                return True
        return False

    def _get_versions_with_contract_overlap_with_period(self, date_from, date_to):
        """
        Returns contract versions covering the specified period.
        Safely handles multi-employee recordsets without singleton crashes.
        """
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

    def _get_day_utc_bounds(self, target_date):
        """Returns UTC bounds (start, next_day_start) for target_date according to employee timezone."""
        self.ensure_one()
        tz_name = self.tz or self.company_id.tz or "Asia/Amman"
        try:
            employee_tz = pytz.timezone(tz_name)
        except Exception:
            employee_tz = pytz.timezone("Asia/Amman")
        day_start_local = employee_tz.localize(datetime.combine(target_date, time.min))
        next_day_start_local = day_start_local + timedelta(days=1)
        day_start_utc = day_start_local.astimezone(pytz.UTC).replace(tzinfo=None)
        next_day_start_utc = next_day_start_local.astimezone(pytz.UTC).replace(tzinfo=None)
        return day_start_utc, next_day_start_utc, employee_tz

    def _get_expected_hours_on_day(self, target_date):
        """Returns expected net work hours (standard 8.0h). Returns 0.0 if out of contract."""
        self.ensure_one()
        version = self._get_versions_with_contract_overlap_with_period(target_date, target_date)[:1]
        if not version:
            return 0.0
        return 8.0

    def _get_absent_work_entry_type(self):
        """Finds or creates the ABSENT work entry type."""
        absent_type = self.env["hr.work.entry.type"].sudo().search([("code", "=", "ABSENT")], limit=1)
        if not absent_type:
            absent_type = self.env["hr.work.entry.type"].sudo().search([("display_code", "=", "ABS")], limit=1)
        if not absent_type:
            absent_type = self.env.ref("reconciliation_payroll.work_entry_type_absent", raise_if_not_found=False)
        if not absent_type:
            absent_type = self.env.ref("factory_attendance_payroll.work_entry_type_absent", raise_if_not_found=False)
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
        Evaluates unpunched days across [date_from, date_to] month by month:
        - Out of contract days: Ignored.
        - Public holidays: Ignored.
        - Check-ins: Ignored.
        - Approved leaves (Annual, Sick, Unpaid, Travel, etc.): Ignored.
        - Rest days (Factory: Monday; Retail: Friday; Headoffice: Calendar off-days):
          Earned quota: 1 rest day per 6 worked days. Kept empty.
        - Remaining candidate days: ABSENT work entry generated.
        """
        if not self:
            return
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to)
        if not date_from or not date_to or date_from > date_to:
            return

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

        # 1. Public holidays batch
        public_holiday_dates = self.env['hr.attendance']._get_public_holiday_dates_batch(date_from, date_to)

        # 2. Attendances
        attendances = self.env['hr.attendance'].sudo().search([
            ('employee_id', 'in', emp_ids),
            ('check_in', '>=', dt_start),
            ('check_in', '<=', dt_end),
        ])
        checked_in_keys = set((att.employee_id.id, att.check_in.date()) for att in attendances if att.check_in)

        # 3. Approved Leaves
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

        # 4. Existing Work Entries (exclude ABSENT to avoid circular blocking)
        absent_type = self._get_absent_work_entry_type()
        WEModel = self.env["hr.work.entry"]
        we_domain = [
            ("employee_id", "in", emp_ids),
            ("state", "!=", "cancelled"),
        ]
        if "date" in WEModel._fields:
            we_domain += [("date", ">=", date_from), ("date", "<=", date_to)]
        elif "date_start" in WEModel._fields:
            we_domain += [
                ("date_start", ">=", dt_start),
                ("date_start", "<=", dt_end),
            ]
        work_entries = WEModel.sudo().search(we_domain)
        for we in work_entries:
            t = we.work_entry_type_id
            if not t:
                continue
            code = (t.code or "").strip().upper()
            disp_code = (getattr(t, "display_code", False) or "").strip().upper()
            if code not in ["ABSENT", "ABS"] and disp_code not in ["ABSENT", "ABS"] and t.id != absent_type.id:
                we_d = getattr(we, "date", False) or (we.date_start.date() if getattr(we, "date_start", None) else False)
                if isinstance(we_d, datetime):
                    we_d = we_d.date()
                if we_d:
                    approved_leave_keys.add((we.employee_id.id, we_d))

        # 5. Contracts
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

        for m_from, m_to in months:
            for employee in self:
                candidate_unpunched_days = []
                emp_contracts = cached_contracts.get(employee.id, [])
                c_vers = employee._get_versions_with_contract_overlap_with_period(m_from, m_to) if hasattr(employee, '_get_versions_with_contract_overlap_with_period') else []
                active_contracts = c_vers or emp_contracts

                curr_d = m_from
                while curr_d <= m_to:
                    emp_key = (employee.id, curr_d)

                    # Contract coverage
                    is_covered = any(
                        (getattr(c, 'date_start', None) and c.date_start <= curr_d) and
                        (not getattr(c, 'date_end', None) or c.date_end >= curr_d)
                        for c in active_contracts
                    ) if active_contracts else True

                    if not is_covered or curr_d in public_holiday_dates or emp_key in checked_in_keys or emp_key in approved_leave_keys:
                        employee._remove_absence_for_day(curr_d, absent_type)
                        curr_d += timedelta(days=1)
                        continue

                    exp_hours = employee._get_expected_hours_on_day(curr_d)
                    if exp_hours > 0:
                        candidate_unpunched_days.append((curr_d, exp_hours))

                    curr_d += timedelta(days=1)

                # Determine rest day allowance
                work_station = employee.employee_work_station or 'factory'
                rest_dates_to_skip = set()

                if work_station == 'headoffice':
                    # Fixed schedule: off-days based on calendar
                    cal = employee.resource_calendar_id
                    if cal:
                        working_weekdays = set(int(a.dayofweek) for a in cal.attendance_ids if a.dayofweek is not None)
                        for d, _h in candidate_unpunched_days:
                            if d.weekday() not in working_weekdays:
                                rest_dates_to_skip.add(d)
                else:
                    # Factory: Monday (0); Retail: Friday (4)
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

                # Apply absent work entries
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
        existing = work_entry_model.search(day_domain).filtered(
            lambda we: we.work_entry_type_id and (
                (we.work_entry_type_id.code or '').strip().upper() in ["ABSENT", "ABS"] or
                (absent_type and we.work_entry_type_id.id == absent_type.id)
            )
        )
        if existing:
            existing.unlink()

    def _apply_absence_for_day(self, target_date, duration, absent_type):
        self.ensure_one()
        dur = max(0.01, min(round(duration, 2), 24.0))
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
        existing = work_entry_model.search(day_domain)

        t_start = datetime.combine(target_date, time(8, 0, 0))
        t_stop = t_start + timedelta(hours=dur)

        if existing:
            non_absent = existing.filtered(
                lambda we: we.work_entry_type_id and (we.work_entry_type_id.code or '').strip().upper() not in ["ABSENT", "ABS"] and (not absent_type or we.work_entry_type_id.id != absent_type.id)
            )
            if non_absent:
                return
            editable = existing.filtered(lambda we: we.state != "validated")
            if editable:
                vals = {"work_entry_type_id": absent_type.id, "duration": dur}
                if "date_start" in work_entry_model._fields:
                    vals["date_start"] = t_start
                if "date_stop" in work_entry_model._fields:
                    vals["date_stop"] = t_stop
                editable.write(vals)
            return

        version = self._get_versions_with_contract_overlap_with_period(target_date, target_date)[:1]
        if not version:
            return

        we_vals = {
            "name": f"Absent: {self.name} - {target_date}",
            "employee_id": self.id,
            "version_id": version.id,
            "duration": dur,
            "work_entry_type_id": absent_type.id,
            "company_id": self.company_id.id if self.company_id else self.env.company.id,
        }
        if "date" in work_entry_model._fields:
            we_vals["date"] = target_date
        if "date_start" in work_entry_model._fields:
            we_vals["date_start"] = t_start
        if "date_stop" in work_entry_model._fields:
            we_vals["date_stop"] = t_stop

        work_entry_model.create(we_vals)

    def generate_work_entries(self, date_start, date_stop, force=False):
        """Standard generator extension with bounds cleanup and absent regeneration on force."""
        res = super().generate_work_entries(date_start, date_stop, force=force)
        if force:
            self._create_absent_work_entries_for_period(date_start, date_stop)
        return res

    @api.model
    def _cron_create_absent_work_entries(self):
        """Monthly cron for absent entries generation."""
        today = fields.Date.context_today(self)
        yesterday = today - timedelta(days=1)
        first_day_of_month = yesterday.replace(day=1)
        self.search([("active", "=", True)])._create_absent_work_entries_for_period(first_day_of_month, yesterday)
