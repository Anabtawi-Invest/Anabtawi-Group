import base64
import io
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import openpyxl
except ImportError:
    openpyxl = None


class HrPayslipRunImportWizard(models.TransientModel):
    _name = 'hr.payslip.run.import.wizard'
    _description = 'Payrun Bulk Partial Salary & Adjustment Wizard'

    payrun_id = fields.Many2one('hr.payslip.run', string="Payrun", required=False, ondelete='cascade')
    excel_file = fields.Binary(string="Excel File", help="Upload the completed partial payment Excel file.")
    file_name = fields.Char(string="File Name")
    import_mode = fields.Selection([
        ('replace', 'Replace existing partial payment / input lines'),
        ('append', 'Add / Update amounts on existing input lines'),
    ], default='replace', required=True, string="Import Mode")
    recompute_payslips = fields.Boolean(
        string="Recompute Payslips",
        default=True,
        help="Automatically trigger salary calculation for updated payslips after import."
    )

    def _get_target_payslips(self):
        """Helper to return relevant payslips from Payrun or Active Selection."""
        if self.payrun_id and self.payrun_id.slip_ids:
            return self.payrun_id.slip_ids
        active_ids = self._context.get('active_ids', [])
        if active_ids:
            return self.env['hr.payslip'].browse(active_ids)
        return self.env['hr.payslip']

    def _get_partial_payment_input_type(self):
        """Helper to retrieve or fallback to Partial Payment input type."""
        InputType = self.env['hr.payslip.input.type']
        input_type = InputType.search([('code', 'in', ['PARTIAL_PAYMENT', 'SALARY_ADVANCE', 'LOAN', 'ADVANCE'])], limit=1)
        if not input_type:
            try:
                input_type = self.env.ref('anabtawi_payrun_bulk_adjustment.input_type_partial_payment')
            except Exception:
                input_type = False
        if not input_type:
            input_type = InputType.create({
                'name': 'Partial Salary Payment / Loan',
                'code': 'PARTIAL_PAYMENT',
            })
        return input_type

    def _get_slip_actual_salary(self, slip):
        """Extracts the Actual Salary from the Salary Computation tab lines (line_ids) safely."""
        if not slip:
            return 0.0

        # 1. Primary Source: Check Salary Computation lines (line_ids)
        if "line_ids" in slip._fields and slip.line_ids:
            actual_line = slip.line_ids.filtered(
                lambda l: (l.name and l.name.strip().lower() == 'actual salary') or 
                          (l.code and l.code.upper() in ['ACTUAL', 'ACTUAL_SALARY', 'ACTUAL_SAL'])
            )
            if actual_line:
                return actual_line[0].total

            net_line = slip.line_ids.filtered(lambda l: l.code and l.code.upper() in ['NET', 'GROSS', 'BASIC'])
            if net_line:
                return net_line[0].total

        # 2. Safe Fallbacks if line_ids are not computed yet
        if "wage" in slip._fields and getattr(slip, 'wage', False):
            return slip.wage

        if "version_id" in slip._fields and getattr(slip, 'version_id', False):
            version = slip.version_id
            if getattr(version, 'contract_wage', False):
                return version.contract_wage

        if "contract_id" in slip._fields and getattr(slip, 'contract_id', False):
            contract = slip.contract_id
            if getattr(contract, 'wage', False):
                return contract.wage

        if getattr(slip, 'employee_id', False):
            emp = slip.employee_id
            if "wage" in emp._fields and getattr(emp, 'wage', False):
                return emp.wage
            if "contract_id" in emp._fields and getattr(emp, 'contract_id', False):
                contract = emp.contract_id
                if getattr(contract, 'wage', False):
                    return contract.wage

        return 0.0

    def action_export_template(self):
        """Generates and downloads the Excel template containing Employee Code, Name, Actual Salary, and Partial Payment Column."""
        self.ensure_one()
        if not openpyxl:
            raise UserError(_("The 'openpyxl' Python package is required to generate Excel files. Please install it."))

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Partial Salary Payments"

        partial_input_type = self._get_partial_payment_input_type()

        # Build headers
        headers = [
            "Employee Code", 
            "Employee Name", 
            "Actual Salary", 
            "Partial Payment Amount", 
            "Notes"
        ]

        # Styling
        header_fill = openpyxl.styles.PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
        header_font = openpyxl.styles.Font(color="FFFFFF", bold=True)
        ws.append(headers)

        for col_num in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_num)
            cell.fill = header_fill
            cell.font = header_font

        # Populate rows with target payslips
        slips = self._get_target_payslips().sorted(key=lambda s: s.employee_id.name or '')
        if not slips:
            raise UserError(_("No payslips found to export template for."))

        for slip in slips:
            emp = slip.employee_id
            emp_code = getattr(emp, 'employee_number', False) or getattr(emp, 'registration_number', False) or getattr(emp, 'barcode', False) or ''
            actual_salary = self._get_slip_actual_salary(slip)

            existing_input = slip.input_line_ids.filtered(lambda i: i.input_type_id == partial_input_type)
            existing_partial_amt = existing_input[0].amount if existing_input else 0.0

            ws.append([
                emp_code,
                emp.name,
                round(actual_salary, 3),
                existing_partial_amt,
                ""
            ])

        # Formatting columns
        ws.column_dimensions['A'].width = 18
        ws.column_dimensions['B'].width = 30
        ws.column_dimensions['C'].width = 18
        ws.column_dimensions['D'].width = 24
        ws.column_dimensions['E'].width = 25

        for row in range(2, ws.max_row + 1):
            ws.cell(row=row, column=3).number_format = '#,##0.000'
            ws.cell(row=row, column=4).number_format = '#,##0.000'

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        file_data = base64.b64encode(output.read())

        payrun_name = self.payrun_id.name if self.payrun_id else 'Batch'
        filename = f"Partial_Salary_Payment_{payrun_name}.xlsx".replace(" ", "_")
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': file_data,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def action_import_adjustments(self):
        """Reads uploaded Excel file and sets partial payment salary inputs for employees."""
        self.ensure_one()
        if not openpyxl:
            raise UserError(_("The 'openpyxl' Python package is required to read Excel files."))
        if not self.excel_file:
            raise UserError(_("Please select an Excel file to upload."))

        file_content = base64.b64decode(self.excel_file)
        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_content), data_only=True)
        except Exception as e:
            raise UserError(_("Failed to read Excel file: %s") % str(e))

        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows or len(rows) < 2:
            raise UserError(_("The uploaded Excel file contains no data rows."))

        header_row = [str(cell).strip() if cell else '' for cell in rows[0]]

        code_col_idx = None
        partial_col_idx = None

        for idx, col_name in enumerate(header_row):
            c_lower = col_name.lower()
            if c_lower in ['employee code', 'employee_number', 'emp code', 'code', 'badge id']:
                code_col_idx = idx
            elif 'partial payment' in c_lower or 'loan' in c_lower or 'advance' in c_lower or c_lower == 'partial_payment':
                partial_col_idx = idx

        if code_col_idx is None:
            code_col_idx = 0
        if partial_col_idx is None:
            partial_col_idx = 3 if len(header_row) > 3 else 2

        partial_input_type = self._get_partial_payment_input_type()

        target_slips = self._get_target_payslips()

        slips_by_code = {}
        for slip in target_slips:
            emp = slip.employee_id
            code = getattr(emp, 'employee_number', False) or getattr(emp, 'registration_number', False) or getattr(emp, 'barcode', False)
            if code:
                slips_by_code[str(code).strip()] = slip
            slips_by_code[str(emp.id)] = slip

        updated_slips = self.env['hr.payslip']
        missing_codes = []
        updated_count = 0
        total_partial_amount = 0.0

        for row_idx, row in enumerate(rows[1:], start=2):
            if not row or not any(row):
                continue

            raw_code = row[code_col_idx]
            if raw_code is None:
                continue

            emp_code = str(raw_code).strip()
            if emp_code.endswith('.0'):
                emp_code = emp_code[:-2]

            slip = slips_by_code.get(emp_code)
            if not slip:
                missing_codes.append(f"Row {row_idx}: Code '{emp_code}'")
                continue

            raw_amount = row[partial_col_idx] if partial_col_idx < len(row) else 0.0
            try:
                partial_amount = float(raw_amount or 0.0)
            except (ValueError, TypeError):
                partial_amount = 0.0

            if self.import_mode == 'replace':
                slip.input_line_ids.filtered(lambda i: i.input_type_id == partial_input_type).unlink()

            if partial_amount > 0.0 or self.import_mode == 'replace':
                existing_line = slip.input_line_ids.filtered(lambda i: i.input_type_id == partial_input_type)
                if existing_line:
                    existing_line[0].write({'amount': partial_amount})
                else:
                    self.env['hr.payslip.input'].create({
                        'payslip_id': slip.id,
                        'input_type_id': partial_input_type.id,
                        'amount': partial_amount,
                    })

                updated_slips |= slip
                updated_count += 1
                total_partial_amount += partial_amount

        if self.recompute_payslips and updated_slips:
            updated_slips.compute_sheet()

        # Chatter Log
        log_msg = _(
            "<b>Partial Salary Payments Imported</b><br/>"
            "• File: <code>%s</code><br/>"
            "• Updated Payslips: <b>%d</b><br/>"
            "• Total Partial Loans Registered: <b>%.3f JOD</b><br/>"
            "• Auto-recomputed: %s"
        ) % (
            self.file_name or 'Uploaded Excel',
            updated_count,
            total_partial_amount,
            "Yes" if self.recompute_payslips else "No"
        )

        if missing_codes:
            log_msg += "<br/><br/><b style='color:red;'>Unmatched Rows (%d):</b><br/>%s" % (
                len(missing_codes), "<br/>".join(missing_codes[:10])
            )

        if self.payrun_id:
            self.payrun_id.message_post(body=log_msg)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Partial Payments Imported"),
                'message': _("Successfully set partial payment salary inputs for %d employees (Total: %.3f JOD).") % 
                           (updated_count, total_partial_amount),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }
