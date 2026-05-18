from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta, time
import pytz


class AttendanceOvertimeRequest(models.Model):
    _name = 'attendance.overtime.request'
    _description = 'Overtime Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        readonly=True,
        default=lambda self: _('New'),
        copy=False,
        tracking=True,
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        tracking=True,
        default=lambda self: self.env.user.employee_id,
    )
    department_id = fields.Many2one(
        'hr.department',
        related='employee_id.department_id',
        string='Department',
        store=True,
    )
    date = fields.Date(
        string='Overtime Date',
        required=True,
        tracking=True,
    )
    overtime_hours = fields.Float(
        string='Requested Overtime Hours',
        required=True,
        tracking=True,
    )
    reason = fields.Text(
        string='Reason',
        required=True,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('refused', 'Refused'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, required=True)

    approved_by = fields.Many2one(
        'res.users',
        string='Approved By',
        readonly=True,
        tracking=True,
    )
    approval_date = fields.Datetime(
        string='Approval Date',
        readonly=True,
    )
    refusal_reason = fields.Text(
        string='Refusal Reason',
        readonly=True,
        tracking=True,
    )

    # Computed: what time the overtime window ends (shift_end + overtime_hours)
    overtime_end_datetime = fields.Datetime(
        string='Overtime Ends At',
        compute='_compute_overtime_end_datetime',
        store=True,
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'attendance.overtime.request') or _('New')
        return super().create(vals_list)

    @api.depends('employee_id', 'date', 'overtime_hours', 'state')
    def _compute_overtime_end_datetime(self):
        for rec in self:
            if rec.state != 'approved' or not rec.employee_id or not rec.date:
                rec.overtime_end_datetime = False
                continue
            shift_end = rec._get_shift_end_datetime()
            if shift_end:
                rec.overtime_end_datetime = shift_end + timedelta(hours=rec.overtime_hours)
            else:
                rec.overtime_end_datetime = False

    def _get_shift_end_datetime(self):
        """Return the scheduled shift end datetime for the employee on self.date."""
        self.ensure_one()
        employee = self.employee_id
        work_date = self.date

        tz = pytz.timezone(employee.tz or 'UTC')

        # Try planning shift first
        try:
            planning_slot = self.env['planning.slot'].sudo().search([
                ('employee_id', '=', employee.id),
                ('start_datetime', '>=', datetime.combine(work_date, time.min)),
                ('start_datetime', '<', datetime.combine(work_date + timedelta(days=1), time.min)),
                ('state', 'in', ['published', 'confirmed']),
            ], limit=1)
        except Exception:
            planning_slot = None

        if planning_slot:
            return planning_slot.end_datetime

        # Fall back to work schedule
        schedule = employee.resource_calendar_id
        if not schedule:
            return None

        day_of_week = work_date.weekday()  # 0=Monday
        attendances = schedule.attendance_ids.filtered(
            lambda a: int(a.dayofweek) == day_of_week
        )
        if not attendances:
            return None

        # Get the last attendance line of the day (latest hour_to)
        last_att = max(attendances, key=lambda a: a.hour_to)
        hour = int(last_att.hour_to)
        minute = int((last_att.hour_to - hour) * 60)

        # Build naive local datetime then convert to UTC
        local_end = tz.localize(datetime(work_date.year, work_date.month, work_date.day, hour, minute))
        return local_end.astimezone(pytz.utc).replace(tzinfo=None)

    @api.constrains('overtime_hours')
    def _check_overtime_hours(self):
        for rec in self:
            if rec.overtime_hours <= 0:
                raise ValidationError(_('Overtime hours must be greater than zero.'))
            if rec.overtime_hours > 12:
                raise ValidationError(_('Overtime hours cannot exceed 12 hours per request.'))

    @api.constrains('date', 'employee_id', 'state')
    def _check_no_duplicate_approved(self):
        for rec in self:
            if rec.state == 'approved':
                duplicate = self.search([
                    ('employee_id', '=', rec.employee_id.id),
                    ('date', '=', rec.date),
                    ('state', '=', 'approved'),
                    ('id', '!=', rec.id),
                ])
                if duplicate:
                    raise ValidationError(_(
                        'Employee %(name)s already has an approved overtime request for %(date)s.',
                        name=rec.employee_id.name,
                        date=rec.date,
                    ))

    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft requests can be submitted.'))
            rec.state = 'submitted'

    def action_approve(self):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_('Only submitted requests can be approved.'))
            rec.write({
                'state': 'approved',
                'approved_by': self.env.user.id,
                'approval_date': fields.Datetime.now(),
            })

    def action_refuse(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Refuse Overtime Request'),
            'res_model': 'overtime.refuse.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_overtime_request_id': self.id},
        }

    def action_cancel(self):
        for rec in self:
            if rec.state in ('approved',):
                raise UserError(_('Approved overtime cannot be cancelled directly. Please refuse it first.'))
            rec.state = 'cancelled'

    def action_reset_draft(self):
        for rec in self:
            if rec.state not in ('refused', 'cancelled'):
                raise UserError(_('Only refused or cancelled requests can be reset to draft.'))
            rec.state = 'draft'

    def get_approved_overtime_for_employee_date(self, employee_id, work_date):
        """Return approved overtime record for an employee on a given date, or False."""
        return self.search([
            ('employee_id', '=', employee_id),
            ('date', '=', work_date),
            ('state', '=', 'approved'),
        ], limit=1)
