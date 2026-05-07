# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime, time
from odoo.addons.resource.models.utils import HOURS_PER_DAY
from odoo.tools.date_utils import float_to_time
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
from odoo.tools.float_utils import float_round
from pytz import timezone, UTC
from collections import namedtuple
import logging
import math

DummyAttendance = namedtuple('DummyAttendance', 'hour_from, hour_to, dayofweek, day_period, week_type')
_logger = logging.getLogger(__name__)


class BaseEmployee(models.AbstractModel):
    _inherit = 'hr.employee'

    leave_manager_id = fields.Many2one(domain="[('company_ids', 'in', company_id)]")

    def write(self, vals):
        if 'leave_manager_id' in vals or 'department_approver_id' in vals:
            self = self.with_context(skip_adding_hr_responsible=True)
        res = super(BaseEmployee, self).write(vals)
        return res


class Users(models.Model):
    _inherit = 'res.users'

    def write(self, vals):
        time_off_group = self.env.ref('hr_holidays.group_hr_holidays_responsible')
        if ('groups_id' in vals and 'skip_adding_hr_responsible' in self._context
                and vals.get('groups_id')[0][1] == time_off_group.id):
            del vals['groups_id']
        res = super(Users, self).write(vals)
        return res


class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'

    def get_support_document_bool_js(self):
        self = self.sudo()
        result = self.support_document
        return result


class HrLeave(models.Model):
    _name = 'hr.leave'
    _inherit = ['hr.leave', 'portal.mixin']

    current_approver = fields.Many2one('res.users', string="Current Approver", compute="_compute_current_approver",
                                       store=True)

    @api.depends('holiday_status_id', 'holiday_status_id.leave_validation_type',
                 'employee_id', 'employee_id.leave_manager_id', 'state', 'name')
    def _compute_current_approver(self):
        for leave in self:
            if leave.holiday_status_id.leave_validation_type not in ['hr', 'no_validation']:
                leave_manager_id = leave.employee_id.leave_manager_id
                if leave.state == 'confirm':
                    leave.current_approver = leave_manager_id
                elif leave.state == 'validate1' and leave.holiday_status_id.responsible_ids:
                    leave.current_approver = leave.holiday_status_id.responsible_ids[0]
                else:
                    leave.current_approver = False
            else:
                leave.current_approver = False

    def get_portal_url_manager(self, suffix=None, report_type=None, download=None, query_string=None, anchor=None):
        return self.with_context(is_manager=True).get_portal_url(suffix, report_type, download, query_string, anchor)

    def get_portal_refuse_url(self, suffix=None, report_type=None, download=None, query_string=None, anchor=None):
        self.ensure_one()
        url = f'/my/requests/refuse/{self.id}' + '%s?access_token=%s%s%s%s%s' % (
            suffix if suffix else '',
            self._portal_ensure_token(),
            '&report_type=%s' % report_type if report_type else '',
            '&download=true' if download else '',
            query_string if query_string else '',
            '#%s' % anchor if anchor else ''
        )
        return url

    def get_portal_approve_url(self, suffix=None, report_type=None, download=None, query_string=None, anchor=None):
        self.ensure_one()
        url = f'/my/requests/approve/{self.id}' + '%s?access_token=%s%s%s%s%s' % (
            suffix if suffix else '',
            self._portal_ensure_token(),
            '&report_type=%s' % report_type if report_type else '',
            '&download=true' if download else '',
            query_string if query_string else '',
            '#%s' % anchor if anchor else ''
        )
        return url

    def _compute_access_url(self):
        super(HrLeave, self)._compute_access_url()
        for leave in self:
            if 'is_manager' in self._context and self._context['is_manager']:
                leave.access_url = f'/my/requests/{leave.id}'
            else:
                leave.access_url = f'/my/leaves/{leave.id}'

    @api.constrains('date_from', 'date_to', 'employee_id')
    def _check_date_state(self):
        """Add diagnostic logs when Odoo blocks date modifications on validated leaves."""
        try:
            return super()._check_date_state()
        except ValidationError:
            for leave in self:
                _logger.exception(
                    "Portal leave date-state constraint blocked write. leave_id=%s state=%s employee_id=%s "
                    "date_from=%s date_to=%s request_date_from=%s request_date_to=%s context_leave_skip_state_check=%s",
                    leave.id,
                    leave.state,
                    leave.employee_id.id if leave.employee_id else False,
                    leave.date_from,
                    leave.date_to,
                    leave.request_date_from,
                    leave.request_date_to,
                    self.env.context.get('leave_skip_state_check'),
                )
            raise

    def get_date_from_to(self, request_date_from, request_date_to, request_hour_from, request_hour_to,
                         request_unit_half, request_unit_hours, request_unit_custom, request_date_from_period,
                         employee):
        employee_id = self.env['hr.employee'].sudo().search([('id', '=', employee)])
        date_from = False
        date_to = False
        if request_date_from:
            request_date_from = datetime.strptime(request_date_from, DEFAULT_SERVER_DATE_FORMAT)
        if request_date_to:
            request_date_to = datetime.strptime(request_date_to, DEFAULT_SERVER_DATE_FORMAT)
        if request_date_from and request_date_to and request_date_from > request_date_to:
            request_date_to = request_date_from
        if not request_date_from:
            date_from = False
        elif not request_unit_half and not request_unit_hours and not request_date_to:
            date_to = False
        else:
            if request_unit_half or request_unit_hours:
                request_date_to = request_date_from
            resource_calendar_id = employee_id.resource_calendar_id or self.sudo().env.company.resource_calendar_id
            domain = [('calendar_id', '=', resource_calendar_id.id), ('display_type', '=', False)]
            attendances = self.env['resource.calendar.attendance'].sudo().read_group(domain, ['ids:array_agg(id)',
                                                                                              'hour_from:min(hour_from)',
                                                                                              'hour_to:max(hour_to)',
                                                                                              'week_type', 'dayofweek',
                                                                                              'day_period'],
                                                                                     ['week_type', 'dayofweek',
                                                                                      'day_period'],
                                                                                     lazy=False)

            # Must be sorted by dayofweek ASC and day_period DESC
            attendances = sorted([DummyAttendance(group['hour_from'], group['hour_to'], group['dayofweek'],
                                                  group['day_period'], group['week_type']) for group in attendances],
                                 key=lambda att: (att.dayofweek, att.day_period != 'morning'))

            default_value = DummyAttendance(0, 0, 0, 'morning', False)

            if resource_calendar_id.two_weeks_calendar:
                # find week type of start_date
                start_week_type = int(math.floor((request_date_from.toordinal() - 1) / 7) % 2)
                attendance_actual_week = [att for att in attendances if
                                          att.week_type is False or int(att.week_type) == start_week_type]
                attendance_actual_next_week = [att for att in attendances if
                                               att.week_type is False or int(att.week_type) != start_week_type]
                # irst, add days of actual week coming after date_from
                attendance_filtred = [att for att in attendance_actual_week if
                                      int(att.dayofweek) >= request_date_from.weekday()]
                # Second, add days of the other type of week
                attendance_filtred += list(attendance_actual_next_week)
                # Third, add days of actual week (to consider days that we have remove first because they coming before date_from)
                attendance_filtred += list(attendance_actual_week)

                end_week_type = int(math.floor((request_date_to.toordinal() - 1) / 7) % 2)
                attendance_actual_week = [att for att in attendances if
                                          att.week_type is False or int(att.week_type) == end_week_type]
                attendance_actual_next_week = [att for att in attendances if
                                               att.week_type is False or int(att.week_type) != end_week_type]
                attendance_filtred_reversed = list(reversed(
                    [att for att in attendance_actual_week if int(att.dayofweek) <= request_date_to.weekday()]))
                attendance_filtred_reversed += list(reversed(attendance_actual_next_week))
                attendance_filtred_reversed += list(reversed(attendance_actual_week))

                # find first attendance coming after first_day
                attendance_from = attendance_filtred[0]
                # find last attendance coming before last_day
                attendance_to = attendance_filtred_reversed[0]
            else:
                # find first attendance coming after first_day
                attendance_from = next(
                    (att for att in attendances if int(att.dayofweek) >= request_date_from.weekday()),
                    attendances[0] if attendances else default_value)
                # find last attendance coming before last_day
                attendance_to = next(
                    (att for att in reversed(attendances) if int(att.dayofweek) <= request_date_to.weekday()),
                    attendances[-1] if attendances else default_value)

            compensated_request_date_from = request_date_from
            compensated_request_date_to = request_date_to

            if request_unit_half:
                if request_date_from_period == 'am':
                    hour_from = float_to_time(attendance_from.hour_from)
                    hour_to = float_to_time(attendance_from.hour_to)
                else:
                    hour_from = float_to_time(attendance_to.hour_from)
                    hour_to = float_to_time(attendance_to.hour_to)
            elif request_unit_hours:
                hour_from = float_to_time(float(request_hour_from))
                hour_to = float_to_time(float(request_hour_to))

            else:
                hour_from = float_to_time(attendance_from.hour_from)
                hour_to = float_to_time(attendance_to.hour_to)

            tz = self.env.user.tz or 'UTC'
            date_from = timezone(tz).localize(datetime.combine(compensated_request_date_from, hour_from)).astimezone(
                UTC).replace(tzinfo=None)
            date_to = timezone(tz).localize(datetime.combine(compensated_request_date_to, hour_to)).astimezone(
                UTC).replace(tzinfo=None)

        return date_from, date_to

    def get_number_of_days_ajax(self, request_date_from, request_date_to, request_hour_from, request_hour_to,
                                request_unit_half, request_unit_hours, request_unit_custom, request_date_from_period,
                                employee, status_id):
        _logger.info(
            "Portal duration compute call: leave_ids=%s employee=%s status_id=%s request_date_from=%s "
            "request_date_to=%s request_hour_from=%s request_hour_to=%s request_unit_half=%s request_unit_hours=%s "
            "request_date_from_period=%s",
            self.ids,
            employee,
            status_id,
            request_date_from,
            request_date_to,
            request_hour_from,
            request_hour_to,
            request_unit_half,
            request_unit_hours,
            request_date_from_period,
        )

        date_from, date_to = self.get_date_from_to(request_date_from, request_date_to, request_hour_from,
                                                   request_hour_to, request_unit_half, request_unit_hours,
                                                   request_unit_custom, request_date_from_period, employee)

        if not self.employee_id:
            employee_id = self.env['hr.employee'].sudo().browse(employee)
        else:
            employee_id = self.employee_id
        if date_from and date_to:
            # Odoo versions/customizations may expose employee contracts with different fields
            # (e.g. no `contract_ids` on hr.employee). Resolve calendar defensively.
            resource_calendar_id = employee_id.resource_calendar_id
            if 'contract_ids' in employee_id._fields:
                contracts = employee_id.sudo().contract_ids.filtered(lambda x: x.state in ['open'])
                if contracts and contracts[0].resource_calendar_id:
                    resource_calendar_id = contracts[0].resource_calendar_id
            elif 'current_contract_id' in employee_id._fields:
                current_contract = employee_id.sudo().current_contract_id
                if current_contract and current_contract.resource_calendar_id:
                    resource_calendar_id = current_contract.resource_calendar_id
            if not resource_calendar_id:
                resource_calendar_id = self.env.company.resource_calendar_id

            _logger.info(
                "Portal duration compute calendar resolved: employee_id=%s calendar_id=%s",
                employee_id.id if employee_id else False,
                resource_calendar_id.id if resource_calendar_id else False,
            )

            days, hours = self.sudo().with_context(resource_calendar=resource_calendar_id)._get_duration_portal(date_from, date_to, employee_id, status_id, resource_calendar_id)
            duration = {}
            duration['days'] = float_round(days, precision_digits=2)
            duration['hours'] = float_round(hours, precision_digits=2)
            return duration
        else:
            return 0

    def _get_duration_portal(self, date_from, date_to, employee_id, status_id, resource_calendar=None):

        resource_calendar = resource_calendar

        if not date_from or not date_to or not resource_calendar:
            return (0, 0)
        hours, days = (0, 0)
        if employee_id:
            # We force the company in the domain as we are more than likely in a compute_sudo
            if 'duration_type' in self.sudo().env['hr.leave.type']._fields and self.sudo().env['hr.leave.type'].browse(status_id).duration_type == 'calendar':
                days = (date_to - date_from)

                seconds = days.seconds
                hours = seconds / 3600
                days = hours / resource_calendar.hours_per_day if resource_calendar.hours_per_day != 0 else 0
            else:
                domain = [('time_type', '=', 'leave'),
                          ('company_id', 'in', self.env.companies.ids + self.env.context.get('allowed_company_ids', [])),
                          # When searching for resource leave intervals, we exclude the one that
                          # is related to the leave we're currently trying to compute for.
                          '|', ('holiday_id', '=', False)]
                dict_work_time_per_day = employee_id._list_work_time_per_day(date_from, date_to,
                                                                                 calendar=resource_calendar, domain=domain)
                work_time_per_day_list = dict_work_time_per_day.get(employee_id.id, [])
                days = len(work_time_per_day_list)
                hours = sum(map(lambda t: t[1], work_time_per_day_list))
        else:
            today_hours = resource_calendar.get_work_hours_count(
                datetime.combine(date_from.date(), time.min),
                datetime.combine(date_from.date(), time.max),
                False)
            hours = resource_calendar.get_work_hours_count(date_from, date_to)
            days = hours / (today_hours or HOURS_PER_DAY)
            days = math.ceil(days)
        return (days, hours)

    def _compute_date_from_to_portal(self):
        for holiday in self:
            if holiday.request_date_from and holiday.request_date_to and holiday.request_date_from > holiday.request_date_to:
                holiday.request_date_to = holiday.request_date_from
            if not holiday.request_date_from:
                holiday.date_from = False
            elif not holiday.request_unit_half and not holiday.request_unit_hours and not holiday.request_date_to:
                holiday.date_to = False
            else:
                if holiday.request_unit_half or holiday.request_unit_hours:
                    holiday.request_date_to = holiday.request_date_from

                hour_from, hour_to = holiday._get_hour_from_to(holiday.employee_id, holiday.request_date_from, holiday.request_date_to)

                compensated_request_date_from = holiday.request_date_from
                compensated_request_date_to = holiday.request_date_to

                # if holiday.request_unit_half:
                #     if holiday.request_date_from_period == 'am':
                #         hour_from = attendance_from.hour_from
                #         hour_to = attendance_from.hour_to
                #     else:
                #         hour_from = attendance_to.hour_from
                #         hour_to = attendance_to.hour_to
                # elif holiday.request_unit_hours:
                #     hour_from = holiday.request_hour_from
                #     hour_to = holiday.request_hour_to
                # else:
                #     hour_from = attendance_from.hour_from
                #     hour_to = attendance_to.hour_to

                tz = timezone(holiday.resource_calendar_id.tz or self.env.user.tz or 'UTC')
                now = datetime.now(tz)
                utc_offset_seconds = now.utcoffset().total_seconds()

                utc_offset_hours = utc_offset_seconds / 3600
                holiday.write({
                    'date_from': self._to_utc(compensated_request_date_from, utc_offset_hours, holiday.resource_calendar_id),
                    'date_to': self._to_utc(compensated_request_date_to, utc_offset_hours, holiday.resource_calendar_id),
                })

    def get_selection_label(self, field_name, field_value):
        return dict(self.fields_get(allfields=[field_name])[field_name]['selection'])[field_value]

    def _get_number_of_days(self, date_from, date_to, employee_id):
        """ Returns a float equals to the timedelta between two dates given as string."""
        if employee_id:
            return self._get_number_of_days_batch(date_from, date_to, employee_id)[employee_id]

        today_hours = self.env.company.resource_calendar_id.get_work_hours_count(
            datetime.combine(date_from.date(), time.min),
            datetime.combine(date_from.date(), time.max),
            False)

        hours = self.env.company.resource_calendar_id.get_work_hours_count(date_from, date_to)
        days = hours / (today_hours or HOURS_PER_DAY) if not self.request_unit_half else 0.5
        return {'days': days, 'hours': hours}

    def _get_number_of_days_batch(self, date_from, date_to, employee_ids):
        """ Returns a float equals to the timedelta between two dates given as string."""
        employee = self.env['hr.employee'].browse(employee_ids)
        # We force the company in the domain as we are more than likely in a compute_sudo
        domain = [('time_type', '=', 'leave'),
                  ('company_id', 'in', self.env.company.ids + self.env.context.get('allowed_company_ids', []))]

        result = employee._get_work_days_data_batch(date_from, date_to, domain=domain)
        for employee_id in result:
            if self.request_unit_half and result[employee_id]['hours'] > 0:
                result[employee_id]['days'] = 0.5
        return result
