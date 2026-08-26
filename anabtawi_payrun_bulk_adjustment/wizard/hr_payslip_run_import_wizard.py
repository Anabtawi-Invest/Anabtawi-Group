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

    def _get_emp_code(self, emp):
        """Returns the primary employee code (employee_number)."""
        if not emp:
            return ""
        code = (
            getattr(emp, 'employee_number', False)
            or getattr(emp, 'sb_employee_number', False)
            or getattr(emp, 'registration_number', False)
            or getattr(emp, 'barcode', False)
            or ''
        )
        return str(code).strip()

    def _get_target_payslips(self):
        """Helper to return relevant payslips from Payrun or Active Selection."""
        if self.payrun_id and self.payrun_id.slip_ids:
            return self.payrun_id.slip_ids
        active_ids = self._context.get('active_ids', [])
        if active_ids and self._context.get('active_model') == 'hr.payslip':
            return self.env['hr.payslip'].browse(active_ids)
        if active_ids and self._context.get('active_model') == 'hr.employee':
            employees = self.env['hr.employee'].browse(active_ids)
            return self.env['hr.payslip'].search([
                ('employee_id', 'in', employees.ids),
                ('state', 'in', ['draft', 'verify']),
            ])
        return self.env['hr.payslip']

    def _get_partial_payment_input_type(self):
        """Helper to retrieve or create the Partial Payment input type."""
        InputType = self.env['hr.payslip.input.type']
        input_type = InputType.search(
            [('code', 'in', ['PARTIAL_PAYMENT', 'SALARY_ADVANCE', 'LOAN', 'ADVANCE'])], limit=1
        )
        if not input_type:
            try:
                input_type = self.env.ref('anabtawi_payrun_bulk_adjustment.input_type_partial_payment')
            except Exception:
                input_type = False
        if not input_type:
            input_type = InputType.create({
                'name': 'Salary partial payment',
                'code': 'PARTIAL_PAYMENT',
            })
        return input_type

    def _get_slip_actual_salary(self, slip):
        """Extracts the Actual Salary from the Salary Computation tab lines safely."""
        if not slip:
            return 0.0

        if "line_ids" in slip._fields and slip.line_ids:
            actual_line = slip.line_ids.filtered(
                lambda l: (l.name and l.name.strip().lower() == 'actual salary')
                or (l.code and l.code.upper() in ['ACTUAL', 'ACTUAL_SALARY', 'ACTUAL_SAL'])
            )
            if actual_line:
                return actual_line[0].total
            net_line = slip.line_ids.filtered(
                lambda l: l.code and l.code.upper() in ['NET', 'GROSS', 'BASIC']
            )
            if net_line:
                return net_line[0].total

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
        """Generates and downloads the Excel template."""
        self.ensure_one()
        if not openpyxl:
            raise UserError(_("The 'openpyxl' Python package is required to generate Excel files."))

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Partial Salary Payments"

        partial_input_type = self._get_partial_payment_input_type()

        headers = ["Employee Code", "Employee Name", "Actual Salary", "Partial Payment Amount", "Notes"]
        header_fill = openpyxl.styles.PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
        header_font = openpyxl.styles.Font(color="FFFFFF", bold=True)
        ws.append(headers)
        for col_num in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_num)
            cell.fill = header_fill
            cell.font = header_font

        slips = self._get_target_payslips().sorted(key=lambda s: s.employee_id.name or '')
        if not slips:
            active_emp_ids = self._context.get('active_ids', [])
            if active_emp_ids and self._context.get('active_model') == 'hr.employee':
                employees = self.env['hr.employee'].browse(active_emp_ids)
            else:
                employees = self.env['hr.employee'].search([('active', '=', True)])

            for emp in employees.sorted(key=lambda e: e.name or ''):
                emp_code = self._get_emp_code(emp)
                wage = 0.0
                if "wage" in emp._fields and emp.wage:
                    wage = emp.wage
                elif "contract_id" in emp._fields and emp.contract_id and getattr(emp.contract_id, 'wage', False):
                    wage = emp.contract_id.wage
                ws.append([emp_code, emp.name, round(wage, 3), 0.0, ""])
        else:
            for slip in slips:
                emp = slip.employee_id
                emp_code = self._get_emp_code(emp)
                actual_salary = self._get_slip_actual_salary(slip)
                existing_input = slip.input_line_ids.filtered(lambda i: i.input_type_id == partial_input_type)
                existing_partial_amt = existing_input[0].amount if existing_input else 0.0
                ws.append([emp_code, emp.name, round(actual_salary, 3), existing_partial_amt, ""])

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

    def _resolve_relation_type_id(self, target_model_obj, field_name, partial_input_type):
        """Dynamically finds the correct record ID for a Many2one field on an adjustment/attachment model."""
        field_obj = target_model_obj._fields.get(field_name)
        if not field_obj or field_obj.type != 'many2one':
            return False

        comodel_name = field_obj.comodel_name
        if not comodel_name or comodel_name not in self.env:
            return False

        if comodel_name == 'hr.payslip.input.type':
            return partial_input_type.id

        CoModel = self.env[comodel_name]
        c_fields = CoModel._fields

        domain = []
        if 'code' in c_fields:
            domain = [('code', 'in', ['PARTIAL_PAYMENT', 'LOAN', 'ADVANCE', 'OTHER', 'DEDUCTION'])]
        elif 'name' in c_fields:
            domain = [('name', 'ilike', 'partial')]

        found = CoModel.search(domain, limit=1) if domain else False
        if not found:
            found = CoModel.search([], limit=1)
        if not found and 'name' in c_fields:
            try:
                vals = {'name': 'Salary partial payment'}
                if 'code' in c_fields:
                    vals['code'] = 'PARTIAL_PAYMENT'
                found = CoModel.create(vals)
            except Exception:
                found = False

        return found.id if found else False

    def _create_employee_salary_adjustment(self, emp, partial_input_type, partial_amount):
        """Creates or updates a Salary Adjustment record under the Employee Profile safely."""
        note_text = _("Mid-month partial salary payment loan")
        today = fields.Date.today()

        # 1. Standard Odoo Salary Attachment model (hr.salary.attachment)
        if 'hr.salary.attachment' in self.env:
            try:
                with self.env.cr.savepoint():
                    Attachment = self.env['hr.salary.attachment']
                    fields_dict = Attachment._fields

                    domain = []
                    if 'employee_ids' in fields_dict:
                        domain.append(('employee_ids', 'in', [emp.id]))
                    elif 'employee_id' in fields_dict:
                        domain.append(('employee_id', '=', emp.id))

                    if 'date_start' in fields_dict:
                        domain.append(('date_start', '=', today))
                    elif 'date' in fields_dict:
                        domain.append(('date', '=', today))

                    existing = Attachment.search(domain, limit=1) if domain else False

                    vals = {}
                    if 'employee_ids' in fields_dict:
                        vals['employee_ids'] = [(4, emp.id)]
                    if 'employee_id' in fields_dict:
                        vals['employee_id'] = emp.id

                    if 'description' in fields_dict:
                        vals['description'] = note_text
                    elif 'name' in fields_dict:
                        vals['name'] = note_text

                    if 'amount' in fields_dict:
                        vals['amount'] = partial_amount
                    if 'monthly_amount' in fields_dict:
                        vals['monthly_amount'] = partial_amount
                    if 'total_amount' in fields_dict:
                        vals['total_amount'] = partial_amount

                    if 'date_start' in fields_dict:
                        vals['date_start'] = today
                    elif 'date' in fields_dict:
                        vals['date'] = today

                    if 'company_id' in fields_dict and emp.company_id:
                        vals['company_id'] = emp.company_id.id

                    for type_fname in ['deduction_type_id', 'attachment_type_id', 'payslip_input_type_id', 'input_type_id', 'type_id']:
                        if type_fname in fields_dict:
                            type_val = self._resolve_relation_type_id(Attachment, type_fname, partial_input_type)
                            if type_val:
                                vals[type_fname] = type_val
                                break

                    if existing:
                        existing.write(vals)
                    else:
                        Attachment.create(vals)

            except Exception as e:
                _logger.warning(
                    "hr.salary.attachment creation/update skipped for emp %s (%s): %s",
                    emp.id, emp.name, str(e)
                )

        # 2. Check custom Salary Adjustment models if present
        for model_name in ['hr.salary.adjustment', 'sb.hr.salary.adjustment', 'hr.employee.salary.adjustment']:
            if model_name in self.env:
                try:
                    with self.env.cr.savepoint():
                        AdjModel = self.env[model_name]
                        adj_fields = AdjModel._fields
                        vals = {}
                        if 'employee_id' in adj_fields:
                            vals['employee_id'] = emp.id
                        elif 'employee_ids' in adj_fields:
                            vals['employee_ids'] = [(4, emp.id)]

                        if 'amount' in adj_fields:
                            vals['amount'] = partial_amount
                        elif 'payslip_amount' in adj_fields:
                            vals['payslip_amount'] = partial_amount

                        if 'note' in adj_fields:
                            vals['note'] = note_text
                        elif 'description' in adj_fields:
                            vals['description'] = note_text
                        elif 'name' in adj_fields:
                            vals['name'] = note_text

                        if 'date_start' in adj_fields:
                            vals['date_start'] = today
                        elif 'date' in adj_fields:
                            vals['date'] = today

                        if 'company_id' in adj_fields and emp.company_id:
                            vals['company_id'] = emp.company_id.id

                        for type_fname in ['type_id', 'input_type_id', 'adjustment_type_id']:
                            if type_fname in adj_fields:
                                type_val = self._resolve_relation_type_id(AdjModel, type_fname, partial_input_type)
                                if type_val:
                                    vals[type_fname] = type_val
                                    break

                        AdjModel.create(vals)

                except Exception as e:
                    _logger.warning(
                        "Could not create %s for emp %s (%s): %s",
                        model_name, emp.id, emp.name, str(e)
                    )

    def action_import_adjustments(self):
        """Reads the uploaded Excel file and creates Salary Adjustments on employee profiles."""
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
            if c_lower in ['employee code', 'employee_number', 'emp code', 'code', 'badge id', 'badge_id', 'employee id', 'employee_id']:
                code_col_idx = idx
            elif 'partial' in c_lower or 'loan' in c_lower or 'advance' in c_lower or 'adjustment' in c_lower:
                partial_col_idx = idx

        if code_col_idx is None:
            code_col_idx = 0
        if partial_col_idx is None:
            partial_col_idx = 3 if len(header_row) > 3 else 2

        partial_input_type = self._get_partial_payment_input_type()

        # Build comprehensive index of all employees
        all_employees = self.env['hr.employee'].search([])
        emp_by_code = {}
        for emp in all_employees:
            code = self._get_emp_code(emp)
            if code:
                emp_by_code[code] = emp
            if getattr(emp, 'barcode', False):
                emp_by_code[str(emp.barcode).strip()] = emp
            if getattr(emp, 'registration_number', False):
                emp_by_code[str(emp.registration_number).strip()] = emp
            emp_by_code[str(emp.id)] = emp

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

            emp = emp_by_code.get(emp_code)
            if not emp:
                missing_codes.append(f"Row {row_idx}: Code '{emp_code}'")
                continue

            raw_amount = row[partial_col_idx] if partial_col_idx < len(row) else 0.0
            try:
                if isinstance(raw_amount, str):
                    clean_str = raw_amount.replace(',', '').replace('JOD', '').replace('$', '').strip()
                    partial_amount = float(clean_str) if clean_str else 0.0
                else:
                    partial_amount = float(raw_amount or 0.0)
            except (ValueError, TypeError):
                partial_amount = 0.0

            if partial_amount > 0.0:
                self._create_employee_salary_adjustment(emp, partial_input_type, partial_amount)
                updated_count += 1
                total_partial_amount += partial_amount

        # Log to payrun chatter if linked
        payrun = self.payrun_id
        if payrun:
            log_msg = _(
                "<b>Partial Salary Payments Imported</b><br/>"
                "• File: <code>%s</code><br/>"
                "• Employees Updated: <b>%d</b><br/>"
                "• Total Partial Loans: <b>%.3f JOD</b>"
            ) % (self.file_name or 'Uploaded Excel', updated_count, total_partial_amount)
            if missing_codes:
                log_msg += "<br/><br/><b style='color:red;'>Unmatched Rows (%d):</b><br/>%s" % (
                    len(missing_codes), "<br/>".join(missing_codes[:10])
                )
            payrun.message_post(body=log_msg)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Salary Adjustments Created"),
                'message': _(
                    "Created Salary Partial Payment adjustments for %d employees (Total: %.3f JOD)."
                ) % (updated_count, total_partial_amount),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }
