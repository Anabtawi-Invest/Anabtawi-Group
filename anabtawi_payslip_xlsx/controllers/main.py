import base64
import re

from odoo import _, http
from odoo.http import content_disposition, request
from odoo.tools import osutil


class PayslipXlsxController(http.Controller):
    @http.route(
        ["/anabtawi_payroll/payslips/xlsx"],
        type="http",
        auth="user",
    )
    def download_payslips_xlsx(self, list_ids="", **kwargs):
        if (
            not request.env.user.has_group("hr_payroll.group_hr_payroll_user")
            or not list_ids
            or re.search("[^0-9|,]", list_ids)
        ):
            return request.not_found()

        ids = [int(item) for item in list_ids.split(",") if item]
        payslips = request.env["hr.payslip"].browse(ids)
        if not payslips.exists():
            return request.not_found()

        xlsx_content = payslips._generate_payslips_xlsx()
        if len(payslips) == 1:
            filename = _("Payslip - %s") % (payslips.name or payslips.employee_id.name)
        else:
            filename = _("Payslips")
        filename = osutil.clean_filename(filename + ".xlsx")

        headers = [
            (
                "Content-Type",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            ("Content-Disposition", content_disposition(filename)),
        ]
        return request.make_response(xlsx_content, headers=headers)

    @http.route(
        ["/anabtawi_payroll/payrun/xlsx"],
        type="http",
        auth="user",
    )
    def download_payrun_xlsx(self, payrun_id=None, payslip_ids=None, **kwargs):
        if (
            not request.env.user.has_group("hr_payroll.group_hr_payroll_user")
            or (not payrun_id and not payslip_ids)
        ):
            return request.not_found()

        parsed_payslip_ids = None
        if payslip_ids and isinstance(payslip_ids, str):
            try:
                parsed_payslip_ids = [int(x) for x in payslip_ids.split(",") if x.strip().isdigit()]
            except ValueError:
                parsed_payslip_ids = None

        payrun = None
        if payrun_id:
            try:
                payrun = request.env["hr.payslip.run"].browse(int(payrun_id))
                if not payrun.exists():
                    payrun = None
            except (ValueError, TypeError):
                payrun = None

        if not payrun and parsed_payslip_ids:
            payslips = request.env["hr.payslip"].browse(parsed_payslip_ids)
            if payslips.exists():
                payrun = payslips.mapped("payslip_run_id")[:1]
                if not payrun:
                    payrun = request.env["hr.payslip.run"].sudo().search([], limit=1)

        if not payrun:
            return request.not_found()

        # Paid only: first download after paid saves audit_file once; later downloads reuse it.
        # Before paid: always live generate — do not save to audit_file.
        is_paid = payrun.state in ("03_paid", "paid") or (
            payrun.slip_ids and all(s.state in ("paid", "done") for s in payrun.slip_ids)
        )

        if is_paid:
            if not payrun.audit_file:
                payrun._freeze_payrun_audit()
            if payrun.audit_file:
                xlsx_content = base64.b64decode(payrun.audit_file)
            else:
                xlsx_content = payrun._generate_payrun_xlsx()
        else:
            xlsx_content = payrun._generate_payrun_xlsx(payslip_ids=parsed_payslip_ids)

        period_str = payrun.date_start.strftime("%Y%m") if payrun.date_start else ""
        if period_str:
            filename = f"PayRun_Audit_{period_str}"
        else:
            filename = f"PayRun_Audit_{payrun.name or 'Report'}"
        filename = osutil.clean_filename(filename + ".xlsx")

        headers = [
            (
                "Content-Type",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            ("Content-Disposition", content_disposition(filename)),
        ]
        return request.make_response(xlsx_content, headers=headers)
