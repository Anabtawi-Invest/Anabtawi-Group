# -*- coding: utf-8 -*-
import base64
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    @api.model
    def _employee_field_by_label(self, label):
        """Name of the hr.employee field whose label is `label` (custom fields differ per database)."""
        for fname, field in self.env['hr.employee']._fields.items():
            if (field.string or '').strip().lower() == label.lower() and field.type in ('char', 'text', 'integer'):
                return fname
        return False

    @api.model
    def _get_employee_bank_account(self, emp):
        """Safely finds the employee's bank account across all standard Odoo configurations."""
        emp_sudo = emp.sudo()
        # 1. Direct field on hr.employee
        for b_field in ('bank_account_id', 'bank_account_ids', 'partner_bank_id'):
            if b_field in emp_sudo._fields:
                val = getattr(emp_sudo, b_field, False)
                if val:
                    res = val[0] if hasattr(val, '__getitem__') else val
                    return res.sudo() if res else False

        # 2. Related partner / home address / private address / work contact
        for p_field in ('address_home_id', 'work_contact_id', 'user_partner_id', 'partner_id'):
            if p_field in emp_sudo._fields:
                partner = getattr(emp_sudo, p_field, False)
                if partner and getattr(partner, 'bank_ids', False):
                    return partner.sudo().bank_ids[0].sudo()

        # 3. Direct search on res.partner.bank
        if 'res.partner.bank' in self.env:
            BankModel = self.env['res.partner.bank'].sudo()
            partner_ids = [getattr(emp_sudo, f).id for f in ('address_home_id', 'work_contact_id', 'partner_id')
                           if f in emp_sudo._fields and getattr(emp_sudo, f, False)]
            if partner_ids:
                found = BankModel.search([('partner_id', 'in', partner_ids)], limit=1)
                if found:
                    return found.sudo()
            if 'employee_id' in BankModel._fields:
                found = BankModel.search([('employee_id', '=', emp_sudo.id)], limit=1)
                if found:
                    return found.sudo()
            elif 'employee_ids' in BankModel._fields:
                found = BankModel.search([('employee_ids', 'in', [emp_sudo.id])], limit=1)
                if found:
                    return found.sudo()
        return False

    def action_export_bank_xlsx(self):
        self.ensure_one()
        slips = self.slip_ids.filtered(lambda s: s.state != 'cancel')
        if not slips:
            raise UserError(_("No payslips found in this payrun."))

        # Prefer validated/done payslips, but if in verify, allow export
        done_slips = slips.filtered(lambda s: s.state in ('done', 'paid'))
        target_slips = done_slips or slips

        # Collect payslips with a positive Net Wage
        exportable = []
        for slip in target_slips:
            net = 0.0
            net_line = slip.line_ids.filtered(lambda l: l.code == 'NET')
            if net_line:
                net = net_line[0].total or 0.0
            else:
                net = getattr(slip, 'net_wage', 0.0) or 0.0
            if net > 0:
                exportable.append((slip, net))

        if not exportable:
            raise UserError(_("No payslips with a positive Net Wage found in this payrun."))

        data = self._build_bank_xlsx(exportable)
        name_clean = (self.name or "Payroll").replace('/', '_').replace('\\', '_')
        att = self.env['ir.attachment'].create({
            'name': "Banks Payroll List %s.xlsx" % name_clean,
            'datas': base64.b64encode(data),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % att.id,
            'target': 'self',
        }

    def _build_bank_xlsx(self, exportable):
        import xlsxwriter  # pylint: disable=import-outside-toplevel
        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {'in_memory': True})
        sh = wb.add_worksheet("Page 1")

        # Column widths matching the Arab Bank Jordan payroll upload layout
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

        transfer_date_str = (self.date_end or fields.Date.today()).strftime('%d/%m/%Y')
        desc_str = self.name or f"PAYROLL {(self.date_end or fields.Date.today()).strftime('%m %Y')}"
        company_currency = self.env.company.currency_id.name or 'JOD'

        # Text format for preserving codes and amounts accurately
        text_fmt = wb.add_format({'num_format': '@'})

        # Exact 11 columns matching 'Banks Payroll List' format WITHOUT header row
        for r, (slip, net_amount) in enumerate(exportable):
            emp = slip.sudo().employee_id
            bank = self._get_employee_bank_account(emp)

            # Col 0: Internal Transfer (LBT / BT)
            transfer_type = getattr(bank, 'internal_transfer', False) or ''
            if not transfer_type:
                bic_code = (getattr(bank, 'bank_bic', '') or '') if bank else ''
                transfer_type = 'BT' if 'ARAB' in bic_code.upper() else 'LBT'

            # Col 1: Company Account Number
            comp_acc = (emp[f_account_no] if f_account_no and emp[f_account_no] else '') or company_bank_acc

            # Col 2: Beneficiary Account / IBAN
            acc_number = (getattr(bank, 'acc_number', '') or '').replace(' ', '') if bank else ''

            # Col 3: Beneficiary Name
            holder = (getattr(bank, 'acc_holder_name', '') or getattr(emp, 'legal_name', '') or emp.name or '').strip()

            # Col 4: Bank Identifier Code (BIC)
            bic = (getattr(bank, 'bank_bic', '') or '') if bank else ''
            if not bic and bank and getattr(bank, 'bank_id', False):
                bic = getattr(bank.bank_id, 'bic', '') or ''

            # Col 5: From code (e.g. '13')
            code_13 = '13'

            # Col 6: Bank Form Number / Date (DD/MM/YYYY)
            f_form_no = self._employee_field_by_label('Bank Form Number')
            date_val = (emp[f_form_no] if f_form_no and emp[f_form_no] else '') or transfer_date_str

            # Col 7: Currency
            curr = (bank.currency_id.name if bank and getattr(bank, 'currency_id', False) else company_currency) or 'JOD'

            # Col 8: Net Wage (formatted with 3 decimal places e.g. 784.750)
            wage_val = round(net_amount or 0.0, 3)
            amount_str = f"{wage_val:.3f}"

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


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def action_export_bank_xlsx(self):
        payrun = self.mapped('payslip_run_id')[:1]
        if payrun:
            return payrun.action_export_bank_xlsx()
        if not self:
            raise UserError(_("Please select payslips."))
        exportable = []
        for slip in self:
            if slip.state == 'cancel':
                continue
            net = 0.0
            net_line = slip.line_ids.filtered(lambda l: l.code == 'NET')
            if net_line:
                net = net_line[0].total or 0.0
            else:
                net = getattr(slip, 'net_wage', 0.0) or 0.0
            if net > 0:
                exportable.append((slip, net))
        if not exportable:
            raise UserError(_("No payslips with positive Net Wage selected."))
        fake_run = self.env['hr.payslip.run'].new({
            'name': 'Payslips Export',
            'date_end': fields.Date.today()
        })
        data = fake_run._build_bank_xlsx(exportable)
        att = self.env['ir.attachment'].create({
            'name': "Banks Payroll List %s.xlsx" % fields.Date.today().strftime('%m_%Y'),
            'datas': base64.b64encode(data),
            'res_model': 'hr.payslip',
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % att.id,
            'target': 'self',
        }

