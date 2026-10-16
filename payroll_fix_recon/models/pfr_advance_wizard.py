# -*- coding: utf-8 -*-
"""Mid-month advance: what each employee has earned up to a cut-off date, from the same day ledger and
lateness settlement the payslip uses. Confirming creates a One Time Salary Adjustment per employee that the
month-end payslip deducts (Company loan input). Nothing is written to payslips or leave balances."""
import calendar

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from . import pfr_utils as U


class PfrAdvanceWizard(models.TransientModel):
    _name = 'pfr.advance.wizard'
    _description = 'Payroll Fix Recon - Mid-month Advance'

    date_cutoff = fields.Date(string="Cut-off Date", required=True,
                              default=lambda self: fields.Date.context_today(self).replace(day=15))
    month_start = fields.Date(string="Month Start", compute='_compute_month_start')
    advance_percent = fields.Float(string="Advance %", default=100.0, required=True,
                                   help="Share of the earned-to-date amount that is paid as advance.")
    input_type_id = fields.Many2one(
        'hr.payslip.input.type', string="Deduct As", required=True,
        default=lambda self: self._default_input_type(),
        help="Payslip input the month-end slip deducts the advance with (e.g. Company loan).")
    employee_ids = fields.Many2many('hr.employee', string="Employees",
                                    help="Leave empty for every active employee with a wage.")
    line_ids = fields.One2many('pfr.advance.wizard.line', 'wizard_id', string="Preview")
    state = fields.Selection([('draft', 'Draft'), ('calculated', 'Calculated'), ('done', 'Done')], default='draft')
    total_advance = fields.Float(string="Total Advance", compute='_compute_total')

    @api.model
    def _default_input_type(self):
        InputType = self.env['hr.payslip.input.type']
        return InputType.search(['|', '|', ('code', '=', 'com_lon'), ('name', 'ilike', 'company loan'),
                                 ('name', 'ilike', 'advance')], limit=1)

    @api.depends('date_cutoff')
    def _compute_month_start(self):
        for wiz in self:
            wiz.month_start = wiz.date_cutoff.replace(day=1) if wiz.date_cutoff else False

    @api.depends('line_ids.advance', 'line_ids.selected')
    def _compute_total(self):
        for wiz in self:
            wiz.total_advance = sum(wiz.line_ids.filtered('selected').mapped('advance'))

    # ------------------------------------------------------------------
    def _marker(self):
        return _("Mid-month advance %s", self.date_cutoff.strftime('%Y-%m'))

    def _earned_to_date(self, emp, d_from, d_to, pre, slip):
        """(ledger, recon values, earned, deduction, paid_days) of one employee for d_from..d_to."""
        L = self.env['pfr.day.ledger'].build(emp, d_from, d_to)
        vals = self.env['pfr.settlement'].compute(slip, L, pre)
        wage = emp.wage or 0.0
        daily = wage / float(calendar.monthrange(d_to.year, d_to.month)[1])
        paid_days = 0.0
        for bucket in L.days.values():
            if bucket in ('OUT', 'UNPAID'):
                continue                                 # absent days stay paid: their cost is the cash deduction
            wet = L.kind_types.get('PH' if bucket == 'PHD' else bucket)
            paid_days += wet._pfr_pay_factor() if wet and wet.pfr_pay_percent is not None else 1.0
        deduction = (vals['undertime_cash_deduction_hours'] or 0.0) * daily / U.DAILY_HOURS
        earned = max(0.0, paid_days * daily - deduction)
        return L, vals, earned, deduction, paid_days

    def action_calculate(self):
        self.ensure_one()
        if not self.date_cutoff:
            raise UserError(_("Choose a cut-off date."))
        d_from, d_to = self.date_cutoff.replace(day=1), self.date_cutoff
        domain = [('active', '=', True)]
        employees = self.employee_ids or self.env['hr.employee'].search(domain)
        employees = employees.filtered(lambda e: (e.wage or 0.0) > 0)
        if not employees:
            raise UserError(_("No employee with a wage found."))
        # same absent / rest-day entries the payslip would see, up to the cut-off date
        employees._pfr_create_absent_entries(d_from, d_to)
        self.env.flush_all()

        Slip = self.env['hr.payslip']
        slips = Slip
        for e in employees:                              # in-memory payslips, never saved
            slips |= Slip.new({'employee_id': e.id, 'date_from': d_from, 'date_to': d_to,
                               'company_id': e.company_id.id or self.env.company.id})
        pre = self.env['pfr.settlement'].preload(slips)
        marker = self._marker()
        Attachment = self.env['hr.salary.attachment'].sudo()
        done = {}
        if 'description' in Attachment._fields and 'employee_ids' in Attachment._fields:
            for att in Attachment.search([('description', 'ilike', marker)]):
                for emp in att.employee_ids:
                    done[emp.id] = att.monthly_amount if 'monthly_amount' in att._fields else 0.0

        lines = [(5, 0, 0)]
        for emp, slip in zip(employees, slips):
            L, vals, earned, deduction, paid_days = self._earned_to_date(emp, d_from, d_to, pre, slip)
            advance = round(earned * self.advance_percent / 100.0, 3)
            exists = emp.id in done
            lines.append((0, 0, {
                'employee_id': emp.id,
                'worked_days': float(L.count('WORK') + L.count('PHD')),
                'rest_days': float(L.count('REST')),
                'absent_days': float(L.count('ABSENT')),
                'lateness_hours': vals['attendance_gross_undertime'],
                'covered_hours': vals['lateness_covered_by_extra_hours'] + vals['lateness_covered_by_annual_leave'],
                'cash_hours': vals['undertime_cash_deduction_hours'],
                'wage': emp.wage,
                'earned': round(earned, 3),
                'advance': advance,
                'selected': advance > 0 and not exists,
                'note': _("Advance already created (%.3f)", done[emp.id]) if exists else '',
            }))
        self.write({'line_ids': lines, 'state': 'calculated'})
        return self._reopen()

    # ------------------------------------------------------------------
    def _attachment_type_vals(self, Attachment):
        """Link the adjustment to the chosen payslip input type, whatever the field is called."""
        vals = {}
        for fname in ('other_input_type_id', 'input_type_id', 'payslip_input_type_id',
                      'deduction_type_id', 'attachment_type_id', 'type_id'):
            field = Attachment._fields.get(fname)
            if not field or field.type != 'many2one':
                continue
            if field.comodel_name == 'hr.payslip.input.type':
                vals[fname] = self.input_type_id.id
                break
            Co = self.env[field.comodel_name].sudo()
            found = Co.browse()
            for link in ('other_input_type_id', 'input_type_id', 'payslip_input_type_id'):
                if link in Co._fields:
                    found = Co.search([(link, '=', self.input_type_id.id)], limit=1)
                    if found:
                        break
            if not found and 'code' in Co._fields and self.input_type_id.code:
                found = Co.search([('code', '=', self.input_type_id.code)], limit=1)
            if not found and 'name' in Co._fields:
                found = Co.search([('name', 'ilike', self.input_type_id.name)], limit=1)
            if found:
                vals[fname] = found.id
                break
        return vals

    def action_create_adjustments(self):
        self.ensure_one()
        lines = self.line_ids.filtered(lambda l: l.selected and l.advance > 0)
        if not lines:
            raise UserError(_("Nothing selected."))
        Attachment = self.env['hr.salary.attachment'].sudo()
        fields_ = Attachment._fields
        base = self._attachment_type_vals(Attachment)
        for fname in ('duration_type', 'duration'):         # One Time
            field = fields_.get(fname)
            if field and field.type == 'selection':
                for key, label in field._description_selection(self.env):
                    if str(key).lower() in ('one', 'one_time', 'onetime', 'single') or 'one' in str(label).lower():
                        base[fname] = key
                        break
        marker = self._marker()
        for line in lines:
            vals = dict(base)
            vals.update({
                'employee_ids': [(6, 0, [line.employee_id.id])],
                'description': marker,
                'monthly_amount': line.advance,
                'date_start': self.month_start,
            })
            if 'total_amount' in fields_:
                vals['total_amount'] = line.advance
            if 'has_total_amount' in fields_:
                vals['has_total_amount'] = True
            if 'company_id' in fields_:
                vals['company_id'] = line.employee_id.company_id.id or self.env.company.id
            Attachment.create(vals)
        self.state = 'done'
        return self._reopen()

    def _reopen(self):
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
                'view_mode': 'form', 'target': 'new'}


class PfrAdvanceWizardLine(models.TransientModel):
    _name = 'pfr.advance.wizard.line'
    _description = 'Payroll Fix Recon - Mid-month Advance Line'

    wizard_id = fields.Many2one('pfr.advance.wizard', required=True, ondelete='cascade')
    selected = fields.Boolean(string="Pay", default=True)
    employee_id = fields.Many2one('hr.employee', string="Employee", readonly=True)
    wage = fields.Float(string="Wage", readonly=True)
    worked_days = fields.Float(string="Worked", readonly=True)
    rest_days = fields.Float(string="Rest", readonly=True)
    absent_days = fields.Float(string="Absent", readonly=True)
    lateness_hours = fields.Float(string="Lateness h", readonly=True, help="Punch lateness plus absent hours.")
    covered_hours = fields.Float(string="Covered h", readonly=True, help="Covered by Extra Hours / Annual Leave.")
    cash_hours = fields.Float(string="Cash h", readonly=True, help="Hours deducted from the salary.")
    earned = fields.Float(string="Earned to Date", readonly=True)
    advance = fields.Float(string="Advance")
    note = fields.Char(readonly=True)
