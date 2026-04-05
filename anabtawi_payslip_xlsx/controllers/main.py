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
