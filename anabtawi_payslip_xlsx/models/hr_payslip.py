import io

from odoo import _, models
from odoo.exceptions import ValidationError
from odoo.tools.misc import format_date


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    def action_export_payslip(self):
        if self.filtered("error_count"):
            raise ValidationError(self._get_error_message())
        return {
            "name": "Payslip XLSX",
            "type": "ir.actions.act_url",
            "url": "/anabtawi_payroll/payslips/xlsx?list_ids=%(list_ids)s"
            % {"list_ids": ",".join(str(x) for x in self.ids)},
            "target": "self",
        }

    def _generate_payslips_xlsx(self):
        import xlsxwriter  # pylint: disable=import-outside-toplevel

        workbook_buffer = io.BytesIO()
        workbook = xlsxwriter.Workbook(workbook_buffer, {"in_memory": True})

        title_fmt = workbook.add_format({"bold": True, "font_size": 14})
        section_fmt = workbook.add_format({"bold": True, "bg_color": "#D9E1F2", "border": 1})
        label_fmt = workbook.add_format({"bold": True, "border": 1, "bg_color": "#F2F2F2"})
        text_fmt = workbook.add_format({"border": 1})
        number_fmt = workbook.add_format({"border": 1, "num_format": "#,##0.00"})
        total_fmt = workbook.add_format({"bold": True, "border": 1, "bg_color": "#E9ECEF"})
        total_num_fmt = workbook.add_format(
            {"bold": True, "border": 1, "bg_color": "#E9ECEF", "num_format": "#,##0.00"}
        )
        warning_fmt = workbook.add_format({"bold": True, "font_color": "#9C0006"})

        used_sheet_names = set()
        for index, payslip in enumerate(self, start=1):
            sheet_name = (payslip.name or _("Payslip"))[:31]
            if sheet_name in used_sheet_names:
                suffix = f" {index}"
                sheet_name = f"{sheet_name[:31 - len(suffix)]}{suffix}"
            used_sheet_names.add(sheet_name)

            sheet = workbook.add_worksheet(sheet_name)
            sheet.set_column(0, 0, 30)
            sheet.set_column(1, 1, 44)
            sheet.set_column(2, 5, 16)

            row = 0
            sheet.write(row, 0, payslip.name or _("Payslip"), title_fmt)
            row += 1
            is_invalid = payslip._is_invalid()
            if is_invalid:
                sheet.write(row, 0, is_invalid, warning_fmt)
                row += 1
            row += 1

            sheet.merge_range(row, 0, row, 1, _("Employee Information"), section_fmt)
            sheet.merge_range(row, 2, row, 4, _("Other Information"), section_fmt)
            row += 1

            employee_rows = [
                (_("Name"), payslip.employee_id.legal_name or ""),
                (_("ID"), payslip.version_id.identification_id or ""),
                (_("Email"), payslip.employee_id.work_email or ""),
                (_("Job Position"), payslip.version_id.job_id.display_name or ""),
                (_("Department"), payslip.version_id.department_id.display_name or ""),
                (_("Marital Status"), payslip.version_id.marital or ""),
                (_("Children"), payslip.version_id.children or 0),
                (
                    _("Address"),
                    ", ".join(
                        filter(
                            None,
                            [
                                payslip.version_id.private_street,
                                payslip.version_id.private_street2,
                                payslip.version_id.private_city,
                                payslip.version_id.private_zip,
                                payslip.version_id.private_country_id.display_name,
                            ],
                        )
                    ),
                ),
            ]

            period_from = max(payslip.date_from, payslip.version_id.contract_date_start)
            period_to = min(
                payslip.date_to,
                payslip.version_id.contract_date_end or payslip.date_to,
            )
            schedule = payslip.version_id.resource_calendar_id
            if schedule.flexible_hours:
                working_schedule = _("%s Hours / Week") % schedule.full_time_required_hours
            else:
                working_schedule = _("%s Hours / Week") % payslip.version_id.hours_per_week

            other_rows = [
                (
                    _("Contract Wage"),
                    ""
                    if payslip.struct_id.hide_basic_on_pdf
                    else payslip.version_id._get_contract_wage(),
                ),
                (
                    _("Pay Period"),
                    "%s - %s"
                    % (
                        format_date(self.env, period_from),
                        format_date(self.env, period_to),
                    ),
                ),
                (_("Computed On"), format_date(self.env, payslip.compute_date)),
                (_("Contract Start Date"), format_date(self.env, payslip.version_id.contract_date_start)),
                (_("Contract Type"), payslip.version_id.contract_type_id.display_name or ""),
                (_("Working Schedule"), working_schedule),
            ]

            max_rows = max(len(employee_rows), len(other_rows))
            for i in range(max_rows):
                if i < len(employee_rows):
                    sheet.write(row + i, 0, employee_rows[i][0], label_fmt)
                    sheet.write(row + i, 1, employee_rows[i][1], text_fmt)
                if i < len(other_rows):
                    sheet.write(row + i, 2, other_rows[i][0], label_fmt)
                    if i == 0 and not payslip.struct_id.hide_basic_on_pdf:
                        sheet.write_number(row + i, 3, other_rows[i][1], number_fmt)
                    else:
                        sheet.write(row + i, 3, other_rows[i][1], text_fmt)
            row += max_rows + 2

            if payslip.use_worked_day_lines:
                sheet.merge_range(row, 0, row, 3, _("Earnings"), section_fmt)
                row += 1
                worked_headers = [_("Name"), _("Hours"), _("Days"), _("Amount")]
                for col, header in enumerate(worked_headers):
                    sheet.write(row, col, header, label_fmt)
                row += 1

                worked_lines = payslip.worked_days_line_ids.filtered(lambda wd: wd.code != "OUT")
                for line in worked_lines:
                    sheet.write(row, 0, line.name, text_fmt)
                    sheet.write_number(row, 1, line.number_of_hours or 0.0, number_fmt)
                    sheet.write_number(row, 2, line.number_of_days or 0.0, number_fmt)
                    sheet.write_number(row, 3, line.amount or 0.0, number_fmt)
                    row += 1

                sheet.write(row, 0, _("Total"), total_fmt)
                sheet.write_number(row, 1, sum(worked_lines.mapped("number_of_hours")), total_num_fmt)
                sheet.write_number(row, 2, sum(worked_lines.mapped("number_of_days")), total_num_fmt)
                sheet.write_number(row, 3, sum(worked_lines.mapped("amount")), total_num_fmt)
                row += 2

            sheet.merge_range(row, 0, row, 4, _("Salary Computation"), section_fmt)
            row += 1
            line_headers = [_("Name"), _("Amount"), _("Quantity"), _("Rate"), _("Total")]
            for col, header in enumerate(line_headers):
                sheet.write(row, col, header, label_fmt)
            row += 1

            for line in payslip.line_ids.filtered(lambda l: l.appears_on_payslip):
                style = total_fmt if line.salary_rule_id.title else text_fmt
                number_style = total_num_fmt if line.salary_rule_id.title else number_fmt
                sheet.write(row, 0, line.name, style)
                if line.quantity > 1 or line.rate < 100:
                    sheet.write_number(row, 1, line.amount or 0.0, number_style)
                else:
                    sheet.write(row, 1, "", style)
                sheet.write_number(row, 2, line.quantity or 0.0, number_style)
                sheet.write_number(row, 3, line.rate or 0.0, number_style)
                sheet.write_number(row, 4, line.total or 0.0, number_style)
                row += 1

            row += 1
            sheet.write(row, 0, _("Net Amount"), label_fmt)
            sheet.write_number(row, 1, payslip.net_wage or 0.0, total_num_fmt)
            row += 1

            if payslip.net_wage >= 0:
                allocations = payslip.compute_salary_allocations()
                if allocations:
                    for account_id, amount in allocations.items():
                        bank = payslip.employee_id.bank_account_ids.filtered(
                            lambda b: str(b.id) == account_id
                        )[:1]
                        account_number = bank.acc_number if bank else _("N/A")
                        sheet.write(row, 0, _("To pay on %s") % account_number, text_fmt)
                        sheet.write_number(row, 1, amount, number_fmt)
                        row += 1
                else:
                    sheet.write(row, 0, _("Amount to be paid"), text_fmt)
                    sheet.write_number(row, 1, payslip.net_wage or 0.0, number_fmt)
            else:
                sheet.write(
                    row,
                    0,
                    _("The net amount will be recovered from the first positive remuneration."),
                    warning_fmt,
                )

        workbook.close()
        return workbook_buffer.getvalue()
