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

    @api.model
    def _is_employee_suspended(self, emp):
        """Returns True if the employee is marked as suspended."""
        emp_sudo = emp.sudo()
        status = getattr(emp_sudo, 'profile_employment_status', False)
        if status and str(status).strip().lower() in ('suspended', 'suspend', 'on_leave_unpaid'):
            return True
        for f in ('suspended', 'is_suspended', 'on_suspension'):
            if f in emp_sudo._fields and getattr(emp_sudo, f, False):
                return True
        return False

    @api.model
    def _get_slip_net_amount(self, slip):
        """Returns the Net amount of a payslip with 3 decimal precision."""
        net_line = slip.line_ids.filtered(lambda l: l.code == 'NET')
        if net_line:
            return round(net_line[0].total or 0.0, 3)
        return round(getattr(slip, 'net_wage', 0.0) or 0.0, 3)

    def _split_paid_slips(self, slips):
        """Splits paid payslips into bank_exportable and cash_exportable.
        - bank_exportable: paid payslips with Net > 0, valid bank account, NOT suspended.
        - cash_exportable: paid payslips with Net > 0, NO bank account OR suspended.
        """
        bank_exportable = []
        cash_exportable = []

        for slip in slips:
            if slip.state != 'paid':
                continue
            net = self._get_slip_net_amount(slip)
            if net <= 0:
                continue

            emp = slip.sudo().employee_id
            is_suspended = self._is_employee_suspended(emp)
            bank = self._get_employee_bank_account(emp)
            acc_number = (getattr(bank, 'acc_number', '') or '').replace(' ', '') if bank else ''

            if not is_suspended and acc_number:
                bank_exportable.append((slip, net))
            else:
                reason = _("Suspended Employee") if is_suspended else _("No Bank Account")
                cash_exportable.append((slip, net, reason))

        return bank_exportable, cash_exportable

    def action_export_bank_paid_xlsx(self):
        """Export Bank File for all paid payslips in this payrun."""
        self.ensure_one()
        paid_slips = self.slip_ids.filtered(lambda s: s.state == 'paid')
        if not paid_slips:
            raise UserError(_("No paid payslips found in this payrun."))
        return paid_slips._do_export_paid_slips(mode='bank', payrun=self)

    def action_export_cash_paid_xlsx(self):
        """Export Cash Sheet for all paid payslips in this payrun."""
        self.ensure_one()
        paid_slips = self.slip_ids.filtered(lambda s: s.state == 'paid')
        if not paid_slips:
            raise UserError(_("No paid payslips found in this payrun."))
        return paid_slips._do_export_paid_slips(mode='cash', payrun=self)

    def action_export_bank_xlsx(self):
        """Legacy export method for all payslips with net > 0 in this payrun."""
        self.ensure_one()
        slips = self.slip_ids.filtered(lambda s: s.state != 'cancel')
        if not slips:
            raise UserError(_("No payslips found in this payrun."))

        done_slips = slips.filtered(lambda s: s.state in ('done', 'paid'))
        target_slips = done_slips or slips

        exportable = []
        for slip in target_slips:
            net = self._get_slip_net_amount(slip)
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

        # Company Arab Bank Account Number
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

        text_fmt = wb.add_format({'num_format': '@'})

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

    def _build_cash_xlsx(self, cash_exportable):
        """Builds a formatted Excel sheet for cash distribution with employee signatures."""
        import xlsxwriter  # pylint: disable=import-outside-toplevel
        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {'in_memory': True})
        sh = wb.add_worksheet("Cash Payout")
        sh.set_portrait()
        sh.set_paper(9)  # A4
        sh.fit_to_pages(1, 0)

        title_fmt = wb.add_format({
            'bold': True, 'font_size': 14, 'align': 'center', 'valign': 'vcenter',
            'font_color': '#1B4F72'
        })
        subtitle_fmt = wb.add_format({
            'font_size': 10, 'italic': True, 'align': 'center', 'valign': 'vcenter',
            'font_color': '#5D6D7E'
        })
        th_fmt = wb.add_format({
            'bold': True, 'font_size': 10, 'align': 'center', 'valign': 'vcenter',
            'bg_color': '#2C3E50', 'font_color': '#FFFFFF',
            'border': 1, 'text_wrap': True
        })
        td_center = wb.add_format({'font_size': 9.5, 'align': 'center', 'valign': 'vcenter', 'border': 1})
        td_left = wb.add_format({'font_size': 9.5, 'align': 'left', 'valign': 'vcenter', 'border': 1})
        td_right = wb.add_format({'font_size': 9.5, 'align': 'right', 'valign': 'vcenter', 'border': 1})
        td_money = wb.add_format({
            'font_size': 9.5, 'bold': True, 'align': 'right', 'valign': 'vcenter',
            'border': 1, 'num_format': '#,##0.000'
        })
        td_reason_susp = wb.add_format({
            'font_size': 9, 'bold': True, 'align': 'center', 'valign': 'vcenter',
            'border': 1, 'font_color': '#C0392B', 'bg_color': '#FDEDEC'
        })
        td_reason_nobank = wb.add_format({
            'font_size': 9, 'align': 'center', 'valign': 'vcenter',
            'border': 1, 'font_color': '#7D6608', 'bg_color': '#FEF9E7'
        })
        total_label_fmt = wb.add_format({
            'bold': True, 'font_size': 10, 'align': 'right', 'valign': 'vcenter',
            'border': 1, 'bg_color': '#EAEDED'
        })
        total_money_fmt = wb.add_format({
            'bold': True, 'font_size': 10, 'align': 'right', 'valign': 'vcenter',
            'border': 1, 'top': 1, 'bottom': 6, 'bg_color': '#EAEDED',
            'font_color': '#922B21', 'num_format': '#,##0.000'
        })

        # Columns:
        # 0: #, 1: Emp No, 2: Name, 3: Arabic Name, 4: Department, 5: Job Title / Branch,
        # 6: Net Amount (JOD), 7: Reason, 8: Recipient Signature, 9: Date Received
        col_widths = [5, 12, 28, 24, 20, 20, 16, 18, 22, 14]
        for c, w in enumerate(col_widths):
            sh.set_column(c, c, w)

        payrun_name = self.name or "Payroll"
        company_name = self.env.company.name or "Anabtawi Group"

        sh.merge_range(0, 0, 0, 9, f"{company_name} — Cash Payroll Payout Register (كشف تسليم الرواتب نقدياً)", title_fmt)
        date_str = (self.date_end or fields.Date.today()).strftime('%d/%m/%Y')
        sh.merge_range(1, 0, 1, 9, f"Pay Run: {payrun_name}  |  Payment Date: {date_str}  |  Currency: JOD", subtitle_fmt)
        sh.set_row(0, 26)
        sh.set_row(1, 18)
        sh.set_row(2, 6)

        headers = [
            "#",
            "Emp No.",
            "Employee Name",
            "الاسم بالعربية",
            "Department",
            "Job Title / Branch",
            "Net Payable (JOD)",
            "Payment Reason",
            "Recipient Signature",
            "Date Received",
        ]
        sh.set_row(3, 24)
        for c, h in enumerate(headers):
            sh.write(3, c, h, th_fmt)

        row = 4
        total_cash = 0.0
        for idx, (slip, net, reason) in enumerate(cash_exportable, start=1):
            emp = slip.sudo().employee_id
            emp_num = (
                getattr(emp, 'employee_number', False)
                or getattr(emp, 'sb_employee_number', False)
                or getattr(emp, 'registration_number', False)
                or getattr(emp, 'barcode', False)
                or str(emp.id)
            )
            name_en = emp.name or ''
            name_ar = getattr(emp, 'name_arabic', '') or getattr(emp, 'legal_name', '') or ''
            dept = emp.department_id.name if emp.department_id else ''
            job = emp.job_title or (emp.job_id.name if emp.job_id else '')

            reason_fmt = td_reason_susp if "suspend" in str(reason).lower() else td_reason_nobank

            sh.set_row(row, 20)
            sh.write_number(row, 0, idx, td_center)
            sh.write_string(row, 1, str(emp_num), td_center)
            sh.write_string(row, 2, name_en, td_left)
            sh.write_string(row, 3, name_ar, td_right)
            sh.write_string(row, 4, dept, td_left)
            sh.write_string(row, 5, job, td_left)
            sh.write_number(row, 6, net, td_money)
            sh.write_string(row, 7, reason, reason_fmt)
            sh.write_string(row, 8, "", td_center)
            sh.write_string(row, 9, "", td_center)

            total_cash += net
            row += 1

        sh.set_row(row, 22)
        sh.merge_range(row, 0, row, 5, "TOTAL CASH PAYOUT (المجموع الكلي نقداً):", total_label_fmt)
        sh.write_number(row, 6, total_cash, total_money_fmt)
        sh.write_string(row, 7, "", total_label_fmt)
        sh.write_string(row, 8, "", total_label_fmt)
        sh.write_string(row, 9, "", total_label_fmt)

        wb.close()
        return buf.getvalue()


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def action_export_bank_paid_xlsx(self):
        """Export Bank File for selected paid payslips with a bank account (not suspended)."""
        if not self:
            raise UserError(_("Please select at least one payslip."))
        return self._do_export_paid_slips(mode='bank')

    def action_export_cash_paid_xlsx(self):
        """Export Cash Sheet for selected paid payslips without a bank account or on suspension."""
        if not self:
            raise UserError(_("Please select at least one payslip."))
        return self._do_export_paid_slips(mode='cash')

    def action_export_bank_xlsx(self):
        """Legacy export handler."""
        payrun = self.mapped('payslip_run_id')[:1]
        if payrun:
            return payrun.action_export_bank_xlsx()
        if not self:
            raise UserError(_("Please select payslips."))
        return self._do_export_paid_slips(mode='bank')

    def _do_export_paid_slips(self, mode='bank', payrun=None):
        pr = payrun or self.mapped('payslip_run_id')[:1]
        Helper = pr if pr else self.env['hr.payslip.run'].new({
            'name': 'Payslips Export',
            'date_end': fields.Date.today()
        })
        paid_slips = self.filtered(lambda s: s.state == 'paid')
        if not paid_slips:
            raise UserError(_("None of the selected payslips are in 'Paid' status."))

        bank_slips, cash_slips = Helper._split_paid_slips(paid_slips)

        if mode == 'bank':
            if not bank_slips:
                raise UserError(_(
                    "No paid payslips with a valid bank account found among the selected records.\n"
                    "(Found %d slip(s) requiring cash payment due to missing bank account or suspension)."
                ) % len(cash_slips))
            data = Helper._build_bank_xlsx(bank_slips)
            name_clean = (pr.name if pr else "Selected_Payslips").replace('/', '_').replace('\\', '_')
            filename = "Banks Payroll List %s (Paid).xlsx" % name_clean
            res_model = 'hr.payslip'
            res_id = self[0].id
        else:
            if not cash_slips:
                raise UserError(_(
                    "No paid payslips requiring cash payment found among the selected records.\n"
                    "(All %d paid employee(s) have valid bank accounts and are not suspended)."
                ) % len(bank_slips))
            data = Helper._build_cash_xlsx(cash_slips)
            name_clean = (pr.name if pr else "Selected_Payslips").replace('/', '_').replace('\\', '_')
            filename = "Cash Payroll Payout %s (Paid).xlsx" % name_clean
            res_model = 'hr.payslip'
            res_id = self[0].id

        att = self.env['ir.attachment'].create({
            'name': filename,
            'datas': base64.b64encode(data),
            'res_model': res_model,
            'res_id': res_id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % att.id,
            'target': 'self',
        }
