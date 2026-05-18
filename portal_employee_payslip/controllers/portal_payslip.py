from odoo import _, http
from odoo.http import content_disposition, request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class PortalEmployeePayslipController(CustomerPortal):
    _items_per_page = 20

    def _get_current_employee(self):
        return request.env["hr.employee"].sudo().search(
            [("user_id", "=", request.env.user.id)],
            limit=1,
        )

    def _get_payslip_domain(self, employee):
        return [
            ("employee_id", "=", employee.id),
            ("state", "in", ["done", "paid"]),
        ]

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if "payslip_count" not in counters:
            return values

        employee = self._get_current_employee()
        if not employee:
            values["payslip_count"] = 0
            return values

        payslip_count = request.env["hr.payslip"].sudo().search_count(
            self._get_payslip_domain(employee)
        )
        values["payslip_count"] = payslip_count
        return values

    def _get_payslip_report_name(self):
        report = request.env["ir.actions.report"].sudo().search(
            [
                ("model", "=", "hr.payslip"),
                ("report_type", "=", "qweb-pdf"),
            ],
            order="id",
            limit=1,
        )
        return report.report_name if report else False

    @http.route(
        ["/my/payslips", "/my/payslips/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_payslips(self, page=1, **kwargs):
        values = self._prepare_portal_layout_values()
        employee = self._get_current_employee()

        Payslip = request.env["hr.payslip"].sudo()
        payslips = Payslip
        pager = {}
        if employee:
            domain = self._get_payslip_domain(employee)
            pager = portal_pager(
                url="/my/payslips",
                total=Payslip.search_count(domain),
                page=page,
                step=self._items_per_page,
                url_args=kwargs,
            )
            payslips = Payslip.search(
                domain,
                order="date_to desc, id desc",
                limit=self._items_per_page,
                offset=pager["offset"],
            )

        values.update(
            {
                "page_name": "my_payslips",
                "employee": employee,
                "payslips": payslips,
                "pager": pager,
                "download_enabled": bool(self._get_payslip_report_name()),
            }
        )
        request.session["my_payslips_history"] = payslips.ids[:100]
        return request.render("portal_employee_payslip.portal_my_payslips", values)

    @http.route(
        "/my/payslips/<int:payslip_id>/download",
        type="http",
        auth="user",
        website=True,
    )
    def portal_download_payslip(self, payslip_id, **kwargs):
        del kwargs
        employee = self._get_current_employee()
        if not employee:
            return request.redirect("/my/payslips")

        payslip = request.env["hr.payslip"].sudo().search(
            [
                ("id", "=", payslip_id),
                ("employee_id", "=", employee.id),
                ("state", "in", ["done", "paid"]),
            ],
            limit=1,
        )
        if not payslip:
            return request.not_found()

        report_name = self._get_payslip_report_name()
        if not report_name:
            return request.not_found()

        pdf_content = request.env["ir.actions.report"].sudo()._render_qweb_pdf(
            report_name, [payslip.id]
        )[0]
        filename = "%s.pdf" % (payslip.display_name or _("Payslip"))
        return request.make_response(
            pdf_content,
            headers=[
                ("Content-Type", "application/pdf"),
                ("Content-Disposition", content_disposition(filename)),
            ],
        )
