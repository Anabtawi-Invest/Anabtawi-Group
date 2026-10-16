# -*- coding: utf-8 -*-
"""Mid-month advance: what each employee has earned up to a cut-off date, from the same day ledger and
lateness settlement the payslip uses. Confirming creates a One Time Salary Adjustment per employee that the
month-end payslip deducts (Company loan input). Nothing is written to payslips or leave balances."""
import base64
import calendar
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date

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
        return L, vals, earned, deduction, paid_days, daily

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
            L, vals, earned, deduction, paid_days, daily = self._earned_to_date(emp, d_from, d_to, pre, slip)
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
                'daily_wage': round(daily, 3),
                'paid_days': paid_days,
                'deduction': round(deduction, 3),
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

    # ------------------------------------------------------------------
    # Excel export (same look as the PayRun Audit)
    # ------------------------------------------------------------------
    def action_export_xlsx(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("Press Calculate first."))
        data = self._build_xlsx()
        att = self.env['ir.attachment'].create({
            'name': "Advance Audit %s.xlsx" % self.date_cutoff.strftime('%Y-%m-%d'),
            'datas': base64.b64encode(data), 'res_model': self._name, 'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'})
        return {'type': 'ir.actions.act_url', 'url': '/web/content/%s?download=true' % att.id, 'target': 'self'}

    def _build_xlsx(self):
        import xlsxwriter  # pylint: disable=import-outside-toplevel
        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {'in_memory': True})
        title = wb.add_format({'bold': True, 'font_size': 15, 'font_color': '#1F497D'})
        meta_l = wb.add_format({'bold': True, 'bg_color': '#F2F4F8', 'border': 1, 'font_size': 10})
        meta_v = wb.add_format({'border': 1, 'font_size': 10, 'align': 'left'})
        card_h = wb.add_format({'bold': True, 'bg_color': '#D9E1F2', 'border': 1, 'align': 'center', 'font_size': 10})
        card_v = wb.add_format({'bold': True, 'border': 1, 'align': 'center', 'font_size': 11,
                                'num_format': '#,##0.00'})
        head = wb.add_format({'bold': True, 'font_color': '#FFFFFF', 'bg_color': '#1F497D', 'border': 1,
                              'align': 'center', 'valign': 'vcenter', 'text_wrap': True, 'font_size': 10})
        head_alw = wb.add_format({'bold': True, 'font_color': '#375623', 'bg_color': '#E2EFDA', 'border': 1,
                                  'align': 'center', 'valign': 'vcenter', 'font_size': 11})
        head_ded = wb.add_format({'bold': True, 'font_color': '#FFFFFF', 'bg_color': '#C00000', 'border': 1,
                                  'align': 'center', 'valign': 'vcenter', 'font_size': 11})
        head_comp = wb.add_format({'bold': True, 'font_color': '#FFFFFF', 'bg_color': '#203764', 'border': 1,
                                   'align': 'center', 'valign': 'vcenter', 'font_size': 11})
        left = wb.add_format({'border': 1, 'align': 'left', 'font_size': 10})
        center = wb.add_format({'border': 1, 'align': 'center', 'font_size': 10})
        num = wb.add_format({'border': 1, 'align': 'right', 'num_format': '#,##0.00', 'font_size': 10})
        num3 = wb.add_format({'border': 1, 'align': 'right', 'num_format': '#,##0.000', 'font_size': 10})
        tot_l = wb.add_format({'bold': True, 'border': 1, 'bg_color': '#E9ECEF', 'align': 'left', 'font_size': 10})
        tot_n = wb.add_format({'bold': True, 'border': 1, 'bg_color': '#E9ECEF', 'align': 'right',
                               'num_format': '#,##0.00', 'font_size': 10})
        ok = wb.add_format({'border': 1, 'align': 'center', 'bg_color': '#E2EFDA', 'font_color': '#375623',
                            'bold': True})
        warn = wb.add_format({'border': 1, 'align': 'center', 'bg_color': '#FFF2CC', 'font_color': '#7F6000',
                              'bold': True})
        err = wb.add_format({'border': 1, 'align': 'center', 'bg_color': '#FCE4D6', 'font_color': '#C00000',
                             'bold': True})

        lines = self.line_ids
        chosen = lines.filtered('selected')
        n = len(chosen)

        sh = wb.add_worksheet("Advance Audit")
        sh.set_landscape()
        sh.write(0, 0, _("Odoo Payroll Report - Mid-month Advance Audit (%s)") % self.date_cutoff, title)
        meta = [(_("Period From"), format_date(self.env, self.month_start)),
                (_("Cut-off Date"), format_date(self.env, self.date_cutoff)),
                (_("Advance %"), "%.2f" % self.advance_percent),
                (_("Deduct As"), self.input_type_id.name or ""),
                (_("Generated By"), self.env.user.name or "System"),
                (_("Generated On"), fields.Datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                (_("Source System"), "Odoo 19 Payroll")]
        for i, (lab, val) in enumerate(meta):
            sh.write(2 + i // 2, (i % 2) * 3, lab, meta_l)
            sh.write(2 + i // 2, (i % 2) * 3 + 1, val, meta_v)

        cards = [(_("Employees Paid"), float(n)),
                 (_("Total Earned (JOD)"), sum(chosen.mapped('earned'))),
                 (_("Total Deduction (JOD)"), sum(chosen.mapped('deduction'))),
                 (_("Total Advance (JOD)"), sum(chosen.mapped('advance'))),
                 (_("Avg Advance / Emp (JOD)"), (sum(chosen.mapped('advance')) / n) if n else 0.0)]
        for c, (lab, val) in enumerate(cards):
            sh.write(7, c, lab, card_h)
            sh.write_number(8, c, val, card_v)

        info = [(_("Employee ID"), 14), (_("Employee Name"), 28), (_("Department"), 22),
                (_("Job Title / Position"), 22), (_("Monthly Wage"), 14), (_("Daily Wage"), 12)]
        days = [(_("Worked Days"), 12), (_("Rest Days"), 11), (_("Absent Days"), 12), (_("Paid Days"), 11)]
        earn = [(_("Gross Earned"), 14)]
        ded = [(_("Lateness + Absent (h)"), 14), (_("Covered by Extra / Annual (h)"), 16),
               (_("Cash Deducted (h)"), 14), (_("Attendance Deduction"), 16)]
        adv = [(_("Earned to Date"), 14), (_("Advance"), 14), (_("Included"), 10), (_("Note"), 34)]
        groups = [(_("EMPLOYEE"), info, head), (_("ATTENDANCE"), days, head), (_("EARNINGS"), earn, head_alw),
                  (_("DEDUCTIONS"), ded, head_ded), (_("ADVANCE"), adv, head_comp)]

        r_group, r_head, r0 = 11, 12, 13
        col = 0
        for gname, cols, gfmt in groups:
            if len(cols) > 1:
                sh.merge_range(r_group, col, r_group, col + len(cols) - 1, gname, gfmt)
            else:
                sh.write(r_group, col, gname, gfmt)
            for label, width in cols:
                sh.write(r_head, col, label, head)
                sh.set_column(col, col, width)
                col += 1
        total_cols = col
        sh.set_row(r_head, 42)
        sh.freeze_panes(r0, 2)

        audit = []
        row = r0
        for line in lines:
            emp = line.employee_id
            number = getattr(emp, 'employee_number', False) or getattr(emp, 'registration_number', False)
            emp_id = number or getattr(emp, 'barcode', False) or str(emp.id)
            dept = emp.department_id.name or "N/A"
            name = emp.legal_name or emp.name
            gross_earned = (line.paid_days or 0.0) * (line.daily_wage or 0.0)
            vals = [emp_id, name, dept, emp.job_id.name or "N/A", line.wage, line.daily_wage,
                    line.worked_days, line.rest_days, line.absent_days, line.paid_days, gross_earned,
                    line.lateness_hours, line.covered_hours, line.cash_hours, line.deduction,
                    line.earned, line.advance if line.selected else 0.0,
                    _("Yes") if line.selected else _("No"), line.note or ""]
            fmts = [center, left, left, left, num, num3, num, num, num, num, num, num, num, num, num3,
                    num, num, center, left]
            for c, (v, f) in enumerate(zip(vals, fmts)):
                if isinstance(v, (int, float)):
                    sh.write_number(row, c, v, f)
                else:
                    sh.write(row, c, v, f)
            issues = []
            if not number:
                issues.append(_("Missing Employee Number"))
            if line.wage <= 0:
                issues.append(_("Negative or zero wage"))
            if line.advance < 0:
                issues.append(_("Negative advance"))
            if line.note:
                issues.append(line.note)
            if line.selected and abs(line.advance - round(line.earned * self.advance_percent / 100.0, 3)) > 0.0005:
                issues.append(_("Advance edited manually"))
            if line.selected and line.earned <= 0:
                issues.append(_("Nothing earned to date"))
            if line.absent_days >= 5:
                issues.append(_("%d absent days") % line.absent_days)
            status = "ERROR" if any("Negative" in i for i in issues) else ("WARNING" if issues else "OK")
            audit.append((emp_id, name, dept, status,
                          ", ".join(issues) if issues else _("Computation verified cleanly")))
            row += 1

        sh.write(row, 0, _("Total"), tot_l)
        for c in range(1, 6):
            sh.write(row, c, "", tot_l)
        sum_to = total_cols - 2                          # numeric columns up to Advance (Included / Note are text)
        for c in range(6, total_cols):
            if c < sum_to:
                letter = xlsxwriter.utility.xl_col_to_name(c)
                sh.write_formula(row, c, "=SUM(%s%d:%s%d)" % (letter, r0 + 1, letter, row), tot_n)
            else:
                sh.write(row, c, "", tot_l)

        sh2 = wb.add_worksheet("Audit")
        for c, w in enumerate((14, 28, 22, 16, 55)):
            sh2.set_column(c, c, w)
        sh2.write(0, 0, _("Advance Audit Trail & Exception Log"), title)
        sh2.write(1, 0, _("Cut-off: %s") % self.date_cutoff, meta_v)
        for c, h in enumerate((_("Employee ID"), _("Employee Name"), _("Department"), _("Audit Status"),
                               _("Issue / Remarks"))):
            sh2.write(3, c, h, head)
        r = 4
        for emp_id, name, dept, status, remarks in audit:
            sh2.write(r, 0, emp_id, center)
            sh2.write(r, 1, name, left)
            sh2.write(r, 2, dept, left)
            sh2.write(r, 3, status, ok if status == "OK" else (warn if status == "WARNING" else err))
            sh2.write(r, 4, remarks, left)
            r += 1
        sh2.write(r, 0, _("Summary Total"), tot_l)
        sh2.write(r, 1, _("Total Audited Records: %d") % len(audit), tot_l)
        for c in (2, 3, 4):
            sh2.write(r, c, "", tot_l)
        wb.close()
        return buf.getvalue()

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
    daily_wage = fields.Float(string="Daily Wage", readonly=True, digits=(16, 3))
    paid_days = fields.Float(string="Paid Days", readonly=True)
    deduction = fields.Float(string="Attendance Deduction", readonly=True, digits=(16, 3))
    earned = fields.Float(string="Earned to Date", readonly=True)
    advance = fields.Float(string="Advance")
    note = fields.Char(readonly=True)
