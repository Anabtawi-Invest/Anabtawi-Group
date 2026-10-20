import calendar
import io

from odoo import _, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.misc import format_date


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # Related from pay run — shown on payslip Other Info tab
    payrun_audit_file = fields.Binary(
        related="payslip_run_id.audit_file",
        string="PayRun Audit File",
        readonly=True,
    )
    payrun_audit_filename = fields.Char(
        related="payslip_run_id.audit_filename",
        string="PayRun Audit Filename",
        readonly=True,
    )
    payrun_audit_file_generated_at = fields.Datetime(
        related="payslip_run_id.audit_file_generated_at",
        string="Audit Snapshot Date",
        readonly=True,
    )

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

    def action_export_payrun_excel(self):
        payrun = self.mapped("payslip_run_id")[:1]
        selected_ids = ",".join(str(i) for i in self.ids)
        if payrun:
            url = f"/anabtawi_payroll/payrun/xlsx?payrun_id={payrun.id}&payslip_ids={selected_ids}"
        else:
            url = f"/anabtawi_payroll/payrun/xlsx?payslip_ids={selected_ids}"
        return {
            "name": "PayRun Audit",
            "type": "ir.actions.act_url",
            "url": url,
            "target": "self",
        }

    # ------------------------------------------------------------------
    # Worked days helpers (one definition shared by the payslip and pay run exports)
    # ------------------------------------------------------------------
    def _xlsx_classify_worked_day(self, wd):
        """'absent' | 'lateness' | 'out_of_contract' | 'ignore' (unpaid / overtime) | 'paid'.
        'paid' covers Attendance, Public Holiday, Annual, Sick, Paid Time Off, Travel, Work Injury..."""
        code = (wd.work_entry_type_id.code or wd.code or "").strip().upper()
        name = (wd.name or "").strip().lower()
        type_name = (wd.work_entry_type_id.name or "").strip().lower()
        text = f"{name} {type_name}"

        if code in ("ABS", "ABSENT") or any(k in text for k in ("absent", "absence", "غياب")):
            return "absent"
        if code in ("LAT", "LATE", "LATENESS") or "lateness" in text or "تأخير" in text:
            return "lateness"
        if code in ("OUT", "OUTCON", "OUT_OF_CONTRACT") or any(k in text for k in ("out of contract", "خارج العقد")):
            return "out_of_contract"
        if (
            code in ("OVERTIME", "EXTRA", "EXTRA_HOURS", "OT", "OTW", "OTR", "PHO",
                     "LEAVEUNPAID", "UN_PAID", "UNPAID", "UNP", "LEAVE500", "SICKLEAVE0")
            or any(k in text for k in ("overtime", "extra", "unpaid", "بدون راتب", "غير مدفوع"))
        ):
            return "ignore"
        return "paid"

    def _xlsx_pay_factor(self, wd):
        """Share of the day that is paid (e.g. Work Injury = 7.5%), from the work entry type."""
        pct = getattr(wd.work_entry_type_id, "pfr_pay_percent", None)
        return 1.0 if pct is None else pct / 100.0

    def _xlsx_daily_wage(self):
        self.ensure_one()
        wage = self.employee_id.wage or 0.0
        if not wage and self.version_id:
            wage = self.version_id._get_contract_wage() or 0.0
        if not self.date_to or wage <= 0:
            return 0.0
        month_days = calendar.monthrange(self.date_to.year, self.date_to.month)[1]
        return wage / float(month_days)

    def _xlsx_is_travel_suspension(self, wd):
        """Travel Suspension Deduction (code TSD) lines are excluded from Attendance Days."""
        code = (wd.work_entry_type_id.code or wd.code or "").strip().upper()
        text = f"{wd.name or ''} {wd.work_entry_type_id.name or ''}".lower()
        return code == "TSD" or "travel suspension" in text

    def _xlsx_attendance_summary(self):
        """Attendance days = every paid line (attendance, public holiday and all paid leaves merged),
        weighted by its pay %, capped at the days of the period. Absent and lateness never count."""
        self.ensure_one()
        att_days = absent_hrs = lateness_hrs = out_days = 0.0
        for wd in self.worked_days_line_ids:
            if self._xlsx_is_travel_suspension(wd):
                continue  # travel suspension deduction days are not attendance
            kind = self._xlsx_classify_worked_day(wd)
            if kind == "paid":
                att_days += (wd.number_of_days or 0.0) * self._xlsx_pay_factor(wd)
            elif kind == "absent":
                absent_hrs += wd.number_of_hours or 0.0
            elif kind == "lateness":
                lateness_hrs += wd.number_of_hours or 0.0
            elif kind == "out_of_contract":
                out_days += wd.number_of_days if wd.number_of_days else ((wd.number_of_hours or 0.0) / 8.0)
        if self.date_from and self.date_to:
            att_days = min(att_days, float((self.date_to - self.date_from).days + 1))
        return {
            "att_days": round(att_days, 2),
            "absent_hrs": absent_hrs,
            "lateness_hrs": lateness_hrs,
            "out_of_contract_days": out_days,
        }

    def _xlsx_worked_day_amount(self, wd, daily_wage):
        """Money shown next to a worked-day line: days x pay % x daily wage (lateness: hours x hourly)."""
        kind = self._xlsx_classify_worked_day(wd)
        if kind == "paid":
            return round((wd.number_of_days or 0.0) * self._xlsx_pay_factor(wd) * daily_wage, 3)
        if kind == "absent":
            days = wd.number_of_days or ((wd.number_of_hours or 0.0) / 8.0)
            return round(days * daily_wage, 3)
        if kind == "lateness":
            return round((wd.number_of_hours or 0.0) * daily_wage / 8.0, 3)
        return 0.0

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
                daily_wage = payslip._xlsx_daily_wage()
                paid_amount = 0.0
                for line in worked_lines:
                    amount = payslip._xlsx_worked_day_amount(line, daily_wage)
                    if payslip._xlsx_classify_worked_day(line) == "paid":
                        paid_amount += amount
                    sheet.write(row, 0, line.name, text_fmt)
                    sheet.write_number(row, 1, line.number_of_hours or 0.0, number_fmt)
                    sheet.write_number(row, 2, line.number_of_days or 0.0, number_fmt)
                    sheet.write_number(row, 3, amount, number_fmt)
                    row += 1

                # Total amount = paid lines only, so it matches the Actual Salary
                sheet.write(row, 0, _("Total"), total_fmt)
                sheet.write_number(row, 1, sum(worked_lines.mapped("number_of_hours")), total_num_fmt)
                sheet.write_number(row, 2, sum(worked_lines.mapped("number_of_days")), total_num_fmt)
                sheet.write_number(row, 3, paid_amount, total_num_fmt)
                row += 1
                sheet.write(row, 0, _("Attendance Days (paid, merged)"), label_fmt)
                sheet.write_number(row, 2, payslip._xlsx_attendance_summary()["att_days"], total_num_fmt)
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
