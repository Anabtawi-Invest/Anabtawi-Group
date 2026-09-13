import base64

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError

from .xlsx_report import build_xlsx


class ReconciledReportWizard(models.TransientModel):
    _name = 'reconciled.report.wizard'
    _description = 'Payroll Reconciled Report'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    date_from = fields.Date(required=True, default=lambda self: fields.Date.start_of(fields.Date.context_today(self), 'month'))
    date_to = fields.Date(required=True, default=lambda self: fields.Date.end_of(fields.Date.context_today(self), 'month'))
    payrun_id = fields.Many2one('hr.payslip.run', string='Pay Run')
    employee_ids = fields.Many2many('hr.employee', string='Employees')
    department_id = fields.Many2one('hr.department', string='Department')
    reconciliation_filter = fields.Selection([
        ('all', 'All'), ('yes', 'Computed reconciliation only'), ('no', 'Not yet computed')], default='all', required=True)
    file_data = fields.Binary(readonly=True, attachment=False)
    filename = fields.Char(readonly=True)

    @api.onchange('payrun_id')
    def _onchange_payrun(self):
        if self.payrun_id:
            self.date_from = self.payrun_id.date_start
            self.date_to = self.payrun_id.date_end

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise ValidationError(_('Period From must not be after Period To.'))

    def _get_payslips(self):
        self.ensure_one()
        if not self.env.user.has_group('hr_payroll.group_hr_payroll_user'):
            raise AccessError(_('Only Payroll users may export this report.'))
        if self.company_id not in self.env.companies:
            raise AccessError(_('Select an allowed company.'))
        self._check_dates()
        # Full payslip periods only: do not present a full-month salary as a partial-month result.
        domain = [('company_id', '=', self.company_id.id), ('date_from', '>=', self.date_from),
                  ('date_to', '<=', self.date_to), ('state', '!=', 'cancel')]
        if self.payrun_id:
            domain.append(('payslip_run_id', '=', self.payrun_id.id))
        if self.employee_ids:
            domain.append(('employee_id', 'in', self.employee_ids.ids))
        if self.department_id:
            domain.append(('employee_id.department_id', '=', self.department_id.id))
        if self.reconciliation_filter != 'all':
            domain.append(('is_reconciled', '=', self.reconciliation_filter == 'yes'))
        slips = self.env['hr.payslip'].search(domain, order='date_from, employee_id, id')
        if not slips:
            raise UserError(_('No non-cancelled payslips with complete periods inside the selected dates match these filters.'))
        return slips

    def action_compute_export(self):
        """Explicit user action: run the same Compute Sheet used on the payslip."""
        slips = self._get_payslips()
        editable = slips.filtered(lambda slip: slip.state in ('draft', 'verify'))
        # Chronological single-slip calls avoid the upstream batch date-window ambiguity.
        # Exceptions intentionally roll back this entire RPC, rather than produce a partial report.
        for slip in editable.sorted(key=lambda s: (s.date_from, s.date_to, s.id)):
            slip.compute_sheet()
        return self._export(slips)

    def action_export(self):
        return self._export(self._get_payslips())

    def _prepare_rows(self, slips):
        states = dict(slips._fields['state']._description_selection(self.env))
        rows = []
        for slip in slips:
            emp = slip.employee_id
            notes = []
            computed = bool(slip.is_reconciled)
            if not computed:
                notes.append('Preview / stored values; use Compute Reconciliation & Export to refresh editable payslips.')
            elif slip.state in ('draft', 'verify'):
                notes.append('Computed; payslip not confirmed. Leave settlement is not certified by this report.')
            ot = slip.attendance_gross_overtime
            late = slip.attendance_gross_undertime
            available = slip.total_extra_hours_available
            step1 = slip.lateness_covered_by_extra_hours
            step2 = slip.lateness_covered_by_annual_leave
            step3 = slip.undertime_cash_deduction_hours
            check = round(late - step1 - step2 - step3, 6)
            if abs(check) > 0.02:
                notes.append('Lateness differs from the three settlement steps; review the source payslip.')
            cash_lines = slip.line_ids.filtered(lambda line: line.code == 'DED_UNDERTIME')
            cash_amount = sum(cash_lines.mapped('total')) if cash_lines else (0.0 if step3 < 0.01 else None)
            if cash_amount is None:
                notes.append('DED_UNDERTIME salary rule is missing; deduction money is unavailable.')
            elif cash_amount > 0:
                notes.append('DED_UNDERTIME has a positive source amount; review salary rule sign.')
            if not slip.line_ids:
                notes.append('Salary lines are not computed; Net Salary is unavailable.')
            if computed and cash_amount == 0 and step3 >= 0.01:
                notes.append('Cash deduction hours exist but the salary rule amount is zero.')
            employee_code = next((getattr(emp, name, False) for name in
                                  ('employee_number', 'registration_number', 'barcode')
                                  if getattr(emp, name, False)), str(emp.id))
            rows.append({
                'employee_code': employee_code, 'employee': emp.name or '',
                'department': emp.department_id.name or '', 'job': emp.job_id.name or '',
                'payslip': slip.name or str(slip.id), 'payrun': slip.payslip_run_id.name or '',
                'date_from': slip.date_from, 'date_to': slip.date_to,
                'state': states.get(slip.state, slip.state),
                'reconciliation': 'Computed' if computed else 'Not computed / preview',
                'overtime': ot, 'lateness': -abs(late), 'opening': available - ot,
                'available': available, 'variance': ot - late,
                'extra_cut': -abs(step1), 'annual_cut': -abs(step2), 'cash_hours': -abs(step3),
                'remaining': slip.remaining_extra_hours_balance,
                'cash_amount': -abs(cash_amount) if cash_amount is not None else None,
                'net': slip.net_wage if slip.line_ids else None,
                'currency': slip.company_id.currency_id.name, 'check': check, 'notes': ' '.join(notes),
            })
        return rows

    def _export(self, slips):
        self.ensure_one()
        rows = self._prepare_rows(slips)
        content = build_xlsx(rows, {
            'company': self.company_id.name,
            'period': f'{self.date_from} — {self.date_to}',
            'user': self.env.user.name,
            'generated': fields.Datetime.context_timestamp(self, fields.Datetime.now()).strftime('%Y-%m-%d %H:%M'),
        })
        self.write({'file_data': base64.b64encode(content),
                    'filename': f'Reconciled_Report_{self.date_from}_{self.date_to}.xlsx'})
        return {'type': 'ir.actions.act_url', 'target': 'download',
                'url': f'/web/content?model={self._name}&id={self.id}&field=file_data&filename_field=filename&download=true'}

    @api.model
    def _attach_reporting_menu(self):
        """Resolve the standard Reporting menu across Payroll distributions."""
        parent = self.env.ref('hr_payroll.menu_hr_payroll_report', raise_if_not_found=False)
        if not parent:
            data = self.env['ir.model.data'].search([
                ('module', '=', 'hr_payroll'), ('model', '=', 'ir.ui.menu'), ('name', 'ilike', 'report')])
            candidates = self.env['ir.ui.menu'].browse(data.mapped('res_id')).exists().filtered(lambda menu: not menu.action)
            if len(candidates) == 1:
                parent = candidates
        if not parent:
            raise UserError(_('Payroll Reporting menu could not be uniquely identified. Check the hr_payroll Reporting menu external ID.'))
        self.env.ref('reconciled_report.menu_reconciled_report').write({'parent_id': parent.id})
