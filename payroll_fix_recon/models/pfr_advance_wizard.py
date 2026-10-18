# -*- coding: utf-8 -*-
"""Mid-month advance: what each employee has earned up to a cut-off date, from the same day ledger the payslip
uses (rest-day rules included). Only attendance and absent days count: absent days are deducted in full, punch
lateness and Extra Hours / Annual Leave cover are ignored and settled on the month-end payslip.
Confirming creates a One Time Salary Adjustment per employee that the month-end payslip deducts
(Company loan input). Nothing is written to payslips or leave balances."""
import base64
import calendar
from datetime import datetime, time
import io
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date

from . import pfr_utils as U

try:
    import openpyxl
except ImportError:
    openpyxl = None


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
    excel_file = fields.Binary(string="Excel File", help="Upload the updated Excel sheet with adjusted advance amounts.")
    file_name = fields.Char(string="File Name")

    batch_name = fields.Char(string="Batch Label / Note",
                             help="Optional note or batch name (e.g. Batch 2, Plant Workers).")
    history_batch = fields.Selection(selection='_get_history_batches', string="Past Advance Run",
                                     help="Choose a previously completed advance run to view or re-download.")

    @api.model
    def _default_input_type(self):
        InputType = self.env['hr.payslip.input.type']
        return InputType.search(['|', '|', ('code', '=', 'com_lon'), ('name', 'ilike', 'company loan'),
                                 ('name', 'ilike', 'advance')], limit=1)

    @api.model
    def _get_history_batches(self):
        """Finds all past mid-month advance batches from hr.salary.attachment."""
        if 'hr.salary.attachment' not in self.env:
            return []
        Attachment = self.env['hr.salary.attachment'].sudo()
        if 'description' not in Attachment._fields:
            return []
        try:
            records = Attachment.search(
                [('description', 'ilike', 'Mid-month advance')],
                order='create_date desc, id desc'
            )
        except Exception:
            return []
        if not records:
            return []
        groups = {}
        order = []
        for att in records:
            desc = att.description or _("Mid-month advance")
            if desc not in groups:
                groups[desc] = {'count': 0, 'total': 0.0}
                order.append(desc)
            groups[desc]['count'] += 1
            amt = (
                att.monthly_amount if 'monthly_amount' in att._fields
                else (att.total_amount if 'total_amount' in att._fields else 0.0)
            ) or 0.0
            groups[desc]['total'] += amt

        res = []
        for desc in order:
            info = groups[desc]
            label = f"{desc} ({info['count']} employees — Total: {info['total']:,.3f} JOD)"
            res.append((desc, label))
        return res

    def action_reset_draft(self):
        self.ensure_one()
        self.line_ids.unlink()
        self.write({
            'state': 'draft',
            'history_batch': False,
            'excel_file': False,
            'file_name': False,
        })
        return self._reopen()

    def action_view_salary_attachments(self):
        """Opens native hr.salary.attachment view filtered to mid-month advances or selected batch."""
        domain = [('description', 'ilike', 'Mid-month advance')]
        if self.history_batch:
            domain = [('description', '=', self.history_batch)]
        return {
            'name': _("Salary Advance Adjustments"),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.salary.attachment',
            'view_mode': 'tree,form',
            'views': [(False, 'tree'), (False, 'form')],
            'domain': domain,
            'context': dict(self.env.context),
        }

    def action_load_history(self):
        self.ensure_one()
        if not self.history_batch:
            raise UserError(_("Please select a past advance run from the dropdown first."))

        Attachment = self.env['hr.salary.attachment'].sudo()
        domain = [('description', '=', self.history_batch)]
        records = Attachment.search(domain)
        if not records:
            raise UserError(_("No salary attachments found for: %s", self.history_batch))

        # Determine cutoff date from records or description
        sample = records[0]
        d_from = False
        d_to = False
        if sample.date_start:
            d_from = sample.date_start
            d_to = d_from.replace(day=min(15, calendar.monthrange(d_from.year, d_from.month)[1]))
        else:
            m = re.search(r'(\d{4})-(\d{2})', self.history_batch)
            if m:
                year, month = int(m.group(1)), int(m.group(2))
                d_from = fields.Date.today().replace(year=year, month=month, day=1)
                d_to = d_from.replace(day=min(15, calendar.monthrange(year, month)[1]))
            else:
                d_from = self.month_start or fields.Date.context_today(self).replace(day=1)
                d_to = self.date_cutoff or d_from.replace(day=15)

        self.date_cutoff = d_to

        emp_adv = {}
        for att in records:
            amt = (
                att.monthly_amount if 'monthly_amount' in att._fields and att.monthly_amount
                else (att.total_amount if 'total_amount' in att._fields and att.total_amount else 0.0)
            ) or 0.0
            emp_ids = []
            if 'employee_id' in att._fields and att.employee_id:
                emp_ids.append(att.employee_id.id)
            if 'employee_ids' in att._fields and att.employee_ids:
                emp_ids.extend(att.employee_ids.ids)
            for eid in set(emp_ids):
                emp_adv[eid] = emp_adv.get(eid, 0.0) + amt

        if not emp_adv:
            raise UserError(_("No employees found in the selected advance run."))

        employees = self.env['hr.employee'].browse(list(emp_adv.keys()))
        employees._pfr_create_absent_entries(d_from, d_to)
        self.env.flush_all()

        # Preload leave balances in bulk
        company = self.env.company
        types = self.env['pfr.settlement'].leave_types(company)
        annual_types = types.get('annual', self.env['hr.leave.type'])
        extra_types = types.get('extra', self.env['hr.leave.type'])
        pto_types = types.get('pto', self.env['hr.leave.type'])

        all_type_ids = list((annual_types | extra_types | pto_types).ids)
        bal_hours = self.env['pfr.settlement'].balance_hours(employees.ids, all_type_ids)

        self.line_ids.unlink()
        lines = []
        for emp in employees:
            advance = emp_adv.get(emp.id, 0.0)
            L, earned, deduction, paid_days, daily = self._earned_to_date(emp, d_from, d_to)

            # Audit: Leaves taken in period
            sick_days = float(L.count('SICK'))
            annual_days = 0.0
            other_paid_days = 0.0
            for d, bucket in L.days.items():
                if bucket == 'TRAVEL':
                    other_paid_days += 1.0
                elif isinstance(bucket, tuple) and bucket[0] == 'TYPE':
                    wet = L.kind_types.get(bucket)
                    w_name = (wet.name or '').lower() if wet else ''
                    w_code = (wet.code or '').lower() if wet else ''
                    if any(n in w_name or n in w_code for n in ('annual', 'سنوي')):
                        annual_days += 1.0
                    elif wet and getattr(wet, 'pfr_pay_percent', 100.0) == 0:
                        pass
                    else:
                        other_paid_days += 1.0

            if annual_days == 0 and annual_types and 'hr.leave' in self.env:
                ann_leaves = self.env['hr.leave'].sudo().search([
                    ('employee_id', '=', emp.id),
                    ('state', 'in', ['validate', 'validate1']),
                    ('holiday_status_id', 'in', annual_types.ids),
                    ('date_from', '<=', datetime.combine(d_to, time.max)),
                    ('date_to', '>=', datetime.combine(d_from, time.min)),
                    '!', ('name', 'ilike', 'Lateness Settlement')
                ])
                for al in ann_leaves:
                    l_from = max(al.request_date_from or U.local_date(al.date_from, emp._pfr_tz()), d_from)
                    l_to = min(al.request_date_to or U.local_date(al.date_to, emp._pfr_tz()), d_to)
                    annual_days = max(annual_days, float((l_to - l_from).days + 1))

            # Audit Balances
            ann_hrs = sum(bal_hours.get((emp.id, t.id), 0.0) for t in annual_types)
            ann_bal = round(ann_hrs / U.DAILY_HOURS, 2)
            for ltype in annual_types:
                try:
                    data, _alloc = emp._get_consumed_leaves(ltype, target_date=d_to)
                    content = data.get(emp, {}).get(ltype, {})
                    v = content.get('virtual_remaining_leaves') or content.get('remaining_leaves')
                    if v is not None:
                        ann_bal = float(v)
                        break
                except Exception:
                    pass

            extra_bal = 0.0
            for fname in ('extra_hours_balance', 'total_extra_hours', 'total_overtime', 'overtime_balance'):
                if fname in emp._fields and getattr(emp, fname, False):
                    extra_bal = float(getattr(emp, fname) or 0.0)
                    break
            if not extra_bal and extra_types:
                extra_bal = sum(bal_hours.get((emp.id, t.id), 0.0) for t in extra_types)
            if not extra_bal and 'hr.attendance.overtime.line' in self.env:
                lines_ot = self.env['hr.attendance.overtime.line'].sudo().search([
                    ('employee_id', '=', emp.id), ('compensable_as_leave', '=', True), ('status', '=', 'approved'),
                    ('date', '<=', d_to)
                ])
                extra_bal = sum(lines_ot.mapped('duration'))

            if 'remaining_leaves' in emp._fields and emp.remaining_leaves:
                paid_bal = float(emp.remaining_leaves)
            else:
                total_paid_hrs = sum(bal_hours.get((emp.id, t_id), 0.0) for t_id in all_type_ids)
                paid_bal = max(ann_bal, round(total_paid_hrs / U.DAILY_HOURS, 2))

            lines.append((0, 0, {
                'employee_id': emp.id,
                'worked_days': float(L.count('WORK') + L.count('PHD')),
                'rest_days': float(L.count('REST')),
                'absent_days': float(L.count('ABSENT')),
                'sick_leave_days': round(sick_days, 2),
                'annual_leave_days': round(annual_days, 2),
                'other_paid_leave_days': round(other_paid_days, 2),
                'annual_leave_balance': round(ann_bal, 2),
                'extra_hours_balance': round(extra_bal, 2),
                'paid_leave_balance': round(paid_bal, 2),
                'wage': emp.wage,
                'daily_wage': round(daily, 3),
                'paid_days': paid_days,
                'deduction': round(deduction, 3),
                'earned': round(earned, 3),
                'advance': advance,
                'selected': True,
                'note': _("Loaded from: %s", self.history_batch),
            }))

        self.write({'line_ids': lines, 'state': 'done'})
        return self._reopen()

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
        base = _("Mid-month advance %s", self.date_cutoff.strftime('%Y-%m'))
        if self.batch_name and self.batch_name.strip():
            return f"{base} - {self.batch_name.strip()}"
        return base

    def _earned_to_date(self, emp, d_from, d_to):
        """(ledger, earned, deduction, paid_days, daily wage) of one employee for d_from..d_to."""
        L = self.env['pfr.day.ledger'].build(emp, d_from, d_to)
        wage = emp.wage or 0.0
        daily = wage / float(calendar.monthrange(d_to.year, d_to.month)[1])
        paid_days = 0.0
        for bucket in L.days.values():
            if bucket in ('OUT', 'UNPAID', 'ABSENT'):
                continue                                 # absent days are not paid in the advance
            wet = L.kind_types.get('PH' if bucket == 'PHD' else bucket)
            paid_days += wet._pfr_pay_factor() if wet and wet.pfr_pay_percent is not None else 1.0
        deduction = L.count('ABSENT') * daily
        earned = max(0.0, paid_days * daily)
        return L, earned, deduction, paid_days, daily

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

        marker = self._marker()
        Attachment = self.env['hr.salary.attachment'].sudo()
        done = {}
        if 'description' in Attachment._fields:
            for att in Attachment.search([('description', 'ilike', marker)]):
                amt = att.monthly_amount if 'monthly_amount' in att._fields else 0.0
                if 'employee_id' in att._fields and att.employee_id:
                    done[att.employee_id.id] = amt
                elif 'employee_ids' in att._fields:
                    for emp in att.employee_ids:
                        done[emp.id] = amt

        # Preload leave balances in bulk
        company = self.env.company
        types = self.env['pfr.settlement'].leave_types(company)
        annual_types = types.get('annual', self.env['hr.leave.type'])
        extra_types = types.get('extra', self.env['hr.leave.type'])
        pto_types = types.get('pto', self.env['hr.leave.type'])

        emp_ids = employees.ids
        all_type_ids = list((annual_types | extra_types | pto_types).ids)
        bal_hours = self.env['pfr.settlement'].balance_hours(emp_ids, all_type_ids)

        lines = [(5, 0, 0)]
        for emp in employees:
            L, earned, deduction, paid_days, daily = self._earned_to_date(emp, d_from, d_to)
            advance = round(earned * self.advance_percent / 100.0, 3)
            exists = emp.id in done

            # Audit: Leaves taken in period (up to cut-off)
            sick_days = float(L.count('SICK'))
            annual_days = 0.0
            other_paid_days = 0.0
            for d, bucket in L.days.items():
                if bucket == 'TRAVEL':
                    other_paid_days += 1.0
                elif isinstance(bucket, tuple) and bucket[0] == 'TYPE':
                    wet = L.kind_types.get(bucket)
                    w_name = (wet.name or '').lower() if wet else ''
                    w_code = (wet.code or '').lower() if wet else ''
                    if any(n in w_name or n in w_code for n in ('annual', 'سنوي')):
                        annual_days += 1.0
                    elif wet and getattr(wet, 'pfr_pay_percent', 100.0) == 0:
                        pass
                    else:
                        other_paid_days += 1.0

            # Cross-check with hr.leave for annual leaves taken in period
            if annual_days == 0 and annual_types and 'hr.leave' in self.env:
                ann_leaves = self.env['hr.leave'].sudo().search([
                    ('employee_id', '=', emp.id),
                    ('state', 'in', ['validate', 'validate1']),
                    ('holiday_status_id', 'in', annual_types.ids),
                    ('date_from', '<=', datetime.combine(d_to, time.max)),
                    ('date_to', '>=', datetime.combine(d_from, time.min)),
                    '!', ('name', 'ilike', 'Lateness Settlement')
                ])
                for al in ann_leaves:
                    l_from = max(al.request_date_from or U.local_date(al.date_from, emp._pfr_tz()), d_from)
                    l_to = min(al.request_date_to or U.local_date(al.date_to, emp._pfr_tz()), d_to)
                    annual_days = max(annual_days, float((l_to - l_from).days + 1))

            # Audit: Current Balances
            # 1. Annual Leave balance (days)
            ann_hrs = sum(bal_hours.get((emp.id, t.id), 0.0) for t in annual_types)
            ann_bal = round(ann_hrs / U.DAILY_HOURS, 2)
            for ltype in annual_types:
                try:
                    data, _alloc = emp._get_consumed_leaves(ltype, target_date=d_to)
                    content = data.get(emp, {}).get(ltype, {})
                    v = content.get('virtual_remaining_leaves') or content.get('remaining_leaves')
                    if v is not None:
                        ann_bal = float(v)
                        break
                except Exception:
                    pass

            # 2. Extra Hours balance (hours)
            extra_bal = 0.0
            for fname in ('extra_hours_balance', 'total_extra_hours', 'total_overtime', 'overtime_balance'):
                if fname in emp._fields and getattr(emp, fname, False):
                    extra_bal = float(getattr(emp, fname) or 0.0)
                    break
            if not extra_bal and extra_types:
                extra_bal = sum(bal_hours.get((emp.id, t.id), 0.0) for t in extra_types)
            if not extra_bal and 'hr.attendance.overtime.line' in self.env:
                lines_ot = self.env['hr.attendance.overtime.line'].sudo().search([
                    ('employee_id', '=', emp.id), ('compensable_as_leave', '=', True), ('status', '=', 'approved'),
                    ('date', '<=', d_to)
                ])
                extra_bal = sum(lines_ot.mapped('duration'))

            # 3. Paid Leave balance (days)
            if 'remaining_leaves' in emp._fields and emp.remaining_leaves:
                paid_bal = float(emp.remaining_leaves)
            else:
                total_paid_hrs = sum(bal_hours.get((emp.id, t_id), 0.0) for t_id in all_type_ids)
                paid_bal = max(ann_bal, round(total_paid_hrs / U.DAILY_HOURS, 2))

            lines.append((0, 0, {
                'employee_id': emp.id,
                'worked_days': float(L.count('WORK') + L.count('PHD')),
                'rest_days': float(L.count('REST')),
                'absent_days': float(L.count('ABSENT')),
                'sick_leave_days': round(sick_days, 2),
                'annual_leave_days': round(annual_days, 2),
                'other_paid_leave_days': round(other_paid_days, 2),
                'annual_leave_balance': round(ann_bal, 2),
                'extra_hours_balance': round(extra_bal, 2),
                'paid_leave_balance': round(paid_bal, 2),
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
        # If no explicit batch_name provided, but an adjustment with this marker already exists,
        # suffix with run index so historical runs don't get combined
        if not self.batch_name and 'description' in fields_:
            existing_count = Attachment.search_count([('description', '=', marker)])
            if existing_count > 0:
                all_matching = Attachment.search([('description', 'ilike', marker)])
                unique_descs = set(all_matching.mapped('description'))
                marker = f"{marker} (Run {len(unique_descs) + 1})"

        for line in lines:
            vals = dict(base)
            vals.update({
                'description': marker,
                'monthly_amount': line.advance,
                'date_start': self.month_start,
            })
            if 'employee_id' in fields_:
                vals['employee_id'] = line.employee_id.id
            if 'employee_ids' in fields_:
                vals['employee_ids'] = [(6, 0, [line.employee_id.id])]
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
        head_bal = wb.add_format({'bold': True, 'font_color': '#203764', 'bg_color': '#D9E1F2', 'border': 1,
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
        att = [(_("Attendance Days"), 15), (_("Rest Days"), 11), (_("Absent Days"), 12)]
        lves = [(_("Sick Leave (Days)"), 15), (_("Annual Leave (Days)"), 16), (_("Other Paid Leaves"), 16)]
        bals = [(_("Annual Leave Bal (Days)"), 20), (_("Extra Hours Bal (Hrs)"), 20), (_("Paid Leave Bal (Days)"), 20)]
        earn = [(_("Paid Days"), 11), (_("Gross (Paid + Absent)"), 18), (_("Absent Deduction"), 16)]
        adv = [(_("Earned to Date"), 14), (_("Advance"), 14), (_("Included"), 10), (_("Note"), 34)]
        groups = [(_("EMPLOYEE"), info, head),
                  (_("ATTENDANCE & ABSENCE"), att, head),
                  (_("LEAVES IN PERIOD"), lves, head_alw),
                  (_("BALANCES"), bals, head_bal),
                  (_("EARNINGS & DEDUCTIONS"), earn, head_ded),
                  (_("ADVANCE"), adv, head_comp)]

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
            gross_earned = ((line.paid_days or 0.0) + (line.absent_days or 0.0)) * (line.daily_wage or 0.0)
            vals = [emp_id, name, dept, emp.job_id.name or "N/A", line.wage, line.daily_wage,
                    line.worked_days, line.rest_days, line.absent_days,
                    line.sick_leave_days, line.annual_leave_days, line.other_paid_leave_days,
                    line.annual_leave_balance, line.extra_hours_balance, line.paid_leave_balance,
                    line.paid_days, gross_earned, line.deduction,
                    line.earned, line.advance if line.selected else 0.0,
                    _("Yes") if line.selected else _("No"), line.note or ""]
            fmts = [center, left, left, left, num, num3,
                    num, num, num,
                    num, num, num,
                    num, num, num,
                    num, num, num3,
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
        for c in range(1, 4):
            sh.write(row, c, "", tot_l)
        letter_wage = xlsxwriter.utility.xl_col_to_name(4)
        sh.write_formula(row, 4, "=SUM(%s%d:%s%d)" % (letter_wage, r0 + 1, letter_wage, row), tot_n)
        sh.write(row, 5, "", tot_l)
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

    # ------------------------------------------------------------------
    # Excel Import (Offline Review & Advance Adjustment)
    # ------------------------------------------------------------------
    def action_import_xlsx(self):
        """Reads uploaded Excel file, matches employees, and updates the advance amount for each."""
        self.ensure_one()
        if not openpyxl:
            raise UserError(_("The 'openpyxl' Python library is required to read Excel files."))
        if not self.excel_file:
            raise UserError(_("Please upload an Excel file to import."))

        if not self.line_ids:
            self.action_calculate()

        if not self.line_ids:
            raise UserError(_("No employee lines available to update."))

        file_content = base64.b64decode(self.excel_file)
        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_content), data_only=True)
        except Exception as e:
            raise UserError(_("Failed to read Excel file: %s") % str(e))

        ws = wb["Advance Audit"] if "Advance Audit" in wb.sheetnames else wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows or len(rows) < 2:
            raise UserError(_("The uploaded Excel sheet contains no data rows."))

        header_row_idx = None
        col_id_idx = None
        col_adv_idx = None
        col_inc_idx = None

        for r_idx, r_vals in enumerate(rows[:25]):
            if not r_vals:
                continue
            r_str = [str(c).strip().lower() if c is not None else '' for c in r_vals]
            has_id = any(any(k in cell for k in ('employee id', 'employee number', 'emp id', 'code', 'badge', 'رقم الموظف', 'الرقم')) for cell in r_str)
            has_adv = any(any(k in cell for k in ('advance', 'سلفة', 'قيمة السلفة', 'advance amount')) for cell in r_str)
            if has_id and has_adv:
                header_row_idx = r_idx
                for c_idx, cell in enumerate(r_str):
                    if any(k in cell for k in ('employee id', 'employee number', 'emp id', 'code', 'badge', 'رقم الموظف', 'الرقم')):
                        if col_id_idx is None:
                            col_id_idx = c_idx
                    elif any(k in cell for k in ('advance', 'سلفة', 'قيمة السلفة', 'advance amount')):
                        if 'earned' not in cell and 'total' not in cell:
                            col_adv_idx = c_idx
                    elif any(k in cell for k in ('included', 'مشمول', 'pay', 'صرف')):
                        col_inc_idx = c_idx
                break

        if col_id_idx is None or col_adv_idx is None:
            col_id_idx = 0
            for r_idx in [12, 11, 10, 1, 0]:
                if r_idx < len(rows):
                    r_str = [str(c).strip().lower() if c is not None else '' for c in rows[r_idx]]
                    for c_idx, cell in enumerate(r_str):
                        if any(k in cell for k in ('advance', 'سلفة')) and 'earned' not in cell:
                            col_adv_idx = c_idx
                            header_row_idx = r_idx
                            break
                    if col_adv_idx is not None:
                        break

        if col_id_idx is None or col_adv_idx is None:
            raise UserError(_("Could not locate 'Employee ID' and 'Advance' columns in the uploaded Excel file."))

        lines_by_emp_code = {}
        for line in self.line_ids:
            emp = line.employee_id
            for attr in ('employee_number', 'sb_employee_number', 'registration_number', 'barcode', 'identification_id'):
                v = getattr(emp, attr, False)
                if v:
                    s = str(v).strip()
                    lines_by_emp_code[s] = line
                    lines_by_emp_code[s.lstrip('0')] = line
            lines_by_emp_code[str(emp.id)] = line
            if emp.name:
                lines_by_emp_code[emp.name.strip().lower()] = line
            if getattr(emp, 'legal_name', False):
                lines_by_emp_code[emp.legal_name.strip().lower()] = line

        updated_count = 0
        unmatched_rows = []
        data_rows = rows[(header_row_idx + 1):] if header_row_idx is not None else rows[1:]

        for r_num, row in enumerate(data_rows, start=(header_row_idx + 2 if header_row_idx is not None else 2)):
            if not row or not any(row):
                continue
            if col_id_idx >= len(row):
                continue

            raw_id = row[col_id_idx]
            if raw_id is None:
                continue

            id_str = str(raw_id).strip()
            if not id_str or id_str.lower() in ('total', 'المجموع', 'sum'):
                continue
            if id_str.endswith('.0'):
                id_str = id_str[:-2]

            line = lines_by_emp_code.get(id_str) or lines_by_emp_code.get(id_str.lstrip('0'))
            if not line:
                unmatched_rows.append(f"Row {r_num}: ID '{id_str}'")
                continue

            raw_adv = row[col_adv_idx] if col_adv_idx < len(row) else 0.0
            try:
                if isinstance(raw_adv, (int, float)):
                    adv_val = float(raw_adv)
                elif isinstance(raw_adv, str):
                    clean_str = raw_adv.replace(',', '').replace('JOD', '').replace('JD', '').replace('$', '').strip()
                    adv_val = float(clean_str) if clean_str else 0.0
                else:
                    adv_val = 0.0
            except (ValueError, TypeError):
                adv_val = 0.0

            adv_val = max(0.0, round(adv_val, 3))
            old_adv = line.advance
            line.advance = adv_val

            if col_inc_idx is not None and col_inc_idx < len(row):
                inc_val = row[col_inc_idx]
                if inc_val is not None:
                    s_inc = str(inc_val).strip().lower()
                    if s_inc in ('no', 'false', '0', 'لا', 'n'):
                        line.selected = False
                    elif s_inc in ('yes', 'true', '1', 'نعم', 'y'):
                        line.selected = (adv_val > 0)
                    else:
                        line.selected = (adv_val > 0)
                else:
                    line.selected = (adv_val > 0)
            else:
                line.selected = (adv_val > 0)

            if abs(old_adv - adv_val) > 0.001:
                line.note = _("Adjusted via Excel: was %.3f -> now %.3f", old_adv, adv_val)

            updated_count += 1

        self._compute_total()

        msg = _("Successfully updated %d employee advance records from Excel (Total Advance: %.3f JOD).") % (
            updated_count, self.total_advance
        )
        if unmatched_rows:
            msg += "\n\n" + _("Unmatched rows (%d): %s") % (len(unmatched_rows), ", ".join(unmatched_rows[:5]))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Excel Import Completed"),
                'message': msg,
                'type': 'success' if updated_count > 0 else 'warning',
                'sticky': False,
                'next': self._reopen(),
            },
        }

    # ------------------------------------------------------------------
    # Bank transfer file (same columns as the "Pay Slip (hr.payslip)" export)
    # ------------------------------------------------------------------
    @api.model
    def _employee_field_by_label(self, label):
        """Name of the hr.employee field whose label is `label` (custom fields differ per database)."""
        for fname, field in self.env['hr.employee']._fields.items():
            if (field.string or '').strip().lower() == label.lower() and field.type in ('char', 'text', 'integer'):
                return fname
        return False

    def action_export_bank_xlsx(self):
        self.ensure_one()
        lines = self.line_ids.filtered(lambda l: l.selected and l.advance > 0)
        if not lines:
            raise UserError(_("Nothing selected."))
        data = self._build_bank_xlsx(lines)
        att = self.env['ir.attachment'].create({
            'name': "Banks Advance List %s.xlsx" % self.date_cutoff.strftime('%m_%Y'),
            'datas': base64.b64encode(data), 'res_model': self._name, 'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'})
        return {'type': 'ir.actions.act_url', 'url': '/web/content/%s?download=true' % att.id, 'target': 'self'}

    def _build_bank_xlsx(self, lines):
        import xlsxwriter  # pylint: disable=import-outside-toplevel
        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {'in_memory': True})
        sh = wb.add_worksheet("Page 1")

        # Column widths matching the example bank list format
        col_widths = [8, 20, 34, 38, 16, 8, 12, 8, 12, 28, 16]
        for c, w in enumerate(col_widths):
            sh.set_column(c, c, w)

        # Company Arab Bank Account Number (defaults to 0126046919500 as in the example sheet)
        company_bank_acc = '0126046919500'
        f_account_no = self._employee_field_by_label('Bank Account Number')
        if self.env.company.partner_id.bank_ids:
            for b in self.env.company.partner_id.bank_ids:
                if b.acc_number:
                    company_bank_acc = str(b.acc_number).replace(' ', '')
                    break

        transfer_date_str = (self.date_cutoff or fields.Date.today()).strftime('%d/%m/%Y')
        desc_str = f"SALARY ADVANCE {self.date_cutoff.strftime('%m %Y')}" if self.date_cutoff else "SALARY ADVANCE"
        company_currency = self.env.company.currency_id.name or 'JOD'

        # Text format for preserving codes and amounts accurately
        text_fmt = wb.add_format({'num_format': '@'})

        # Exact 11 columns matching 'Banks Payroll List' format WITHOUT header row
        for r, line in enumerate(lines):
            emp = line.employee_id
            bank = emp.bank_account_id or (emp.bank_account_ids[:1] if 'bank_account_ids' in emp._fields else False)

            # Col 0: Internal Transfer (LBT / BT)
            transfer_type = getattr(bank, 'internal_transfer', False) or ''
            if not transfer_type:
                bic_code = (bank.bank_bic if bank and 'bank_bic' in bank._fields else '') or ''
                transfer_type = 'BT' if 'ARAB' in bic_code.upper() else 'LBT'

            # Col 1: Company Account Number
            comp_acc = (emp[f_account_no] if f_account_no and emp[f_account_no] else '') or company_bank_acc

            # Col 2: Beneficiary Account / IBAN
            acc_number = (bank.acc_number or '').replace(' ', '') if bank else ''

            # Col 3: Beneficiary Name
            holder = (getattr(bank, 'acc_holder_name', '') or emp.legal_name or emp.name or '').strip()

            # Col 4: Bank Identifier Code (BIC)
            bic = (bank.bank_bic if bank and 'bank_bic' in bank._fields else '') or ''
            if not bic and bank and getattr(bank, 'bank_id', False):
                bic = getattr(bank.bank_id, 'bic', '') or ''

            # Col 5: From code (e.g. '13')
            code_13 = '13'

            # Col 6: Bank Form Number / Date (DD/MM/YYYY)
            f_form_no = self._employee_field_by_label('Bank Form Number')
            date_val = (emp[f_form_no] if f_form_no and emp[f_form_no] else '') or transfer_date_str

            # Col 7: Currency
            curr = (bank.currency_id.name if bank and bank.currency_id else company_currency) or 'JOD'

            # Col 8: Net Wage (Advance Amount formatted with 3 decimal places e.g. 784.750)
            adv_amount = round(line.advance or 0.0, 3)
            amount_str = f"{adv_amount:.3f}"

            # Col 9: Payrun Description
            payrun_name = desc_str

            # Col 10: Employee Number
            emp_number = (
                getattr(emp, 'employee_number', False)
                or getattr(emp, 'sb_employee_number', False)
                or getattr(emp, 'registration_number', False)
                or getattr(emp, 'barcode', False)
                or str(emp.id)
            )

            sh.write_string(r, 0, str(transfer_type), text_fmt)
            sh.write_string(r, 1, str(comp_acc), text_fmt)
            sh.write_string(r, 2, str(acc_number), text_fmt)
            sh.write_string(r, 3, str(holder), text_fmt)
            sh.write_string(r, 4, str(bic), text_fmt)
            sh.write_string(r, 5, str(code_13), text_fmt)
            sh.write_string(r, 6, str(date_val), text_fmt)
            sh.write_string(r, 7, str(curr), text_fmt)
            sh.write_string(r, 8, str(amount_str), text_fmt)
            sh.write_string(r, 9, str(payrun_name), text_fmt)
            sh.write_string(r, 10, str(emp_number), text_fmt)

        wb.close()
        return buf.getvalue()

    def _reopen(self):
        view = self.env.ref('payroll_fix_recon.view_pfr_advance_wizard_form', raise_if_not_found=False)
        return {
            'name': _("Mid-month Advance"),
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(view.id if view else False, 'form')],
            'target': 'new',
            'context': self.env.context,
        }


class PfrAdvanceWizardLine(models.TransientModel):
    _name = 'pfr.advance.wizard.line'
    _description = 'Payroll Fix Recon - Mid-month Advance Line'

    wizard_id = fields.Many2one('pfr.advance.wizard', required=True, ondelete='cascade')
    selected = fields.Boolean(string="Pay", default=True)
    employee_id = fields.Many2one('hr.employee', string="Employee", readonly=True)
    wage = fields.Float(string="Wage", readonly=True)
    worked_days = fields.Float(string="Attendance Days", readonly=True)
    rest_days = fields.Float(string="Rest Days", readonly=True)
    absent_days = fields.Float(string="Absent Days", readonly=True)
    daily_wage = fields.Float(string="Daily Wage", readonly=True, digits=(16, 3))
    paid_days = fields.Float(string="Paid Days", readonly=True)
    deduction = fields.Float(string="Absent Deduction", readonly=True, digits=(16, 3))
    earned = fields.Float(string="Earned to Date", readonly=True)
    advance = fields.Float(string="Advance")
    note = fields.Char(readonly=True)

    # Leaves taken in the period (up to cut-off)
    sick_leave_days = fields.Float(string="Sick Leave (Days)", readonly=True, digits=(16, 2))
    annual_leave_days = fields.Float(string="Annual Leave (Days)", readonly=True, digits=(16, 2))
    other_paid_leave_days = fields.Float(string="Other Paid Leaves (Days)", readonly=True, digits=(16, 2))

    # Balances
    annual_leave_balance = fields.Float(string="Annual Leave Balance (Days)", readonly=True, digits=(16, 2))
    extra_hours_balance = fields.Float(string="Extra Hours Balance (Hrs)", readonly=True, digits=(16, 2))
    paid_leave_balance = fields.Float(string="Paid Leave Balance (Days)", readonly=True, digits=(16, 2))

