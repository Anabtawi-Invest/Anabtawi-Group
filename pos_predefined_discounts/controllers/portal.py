from odoo import http
from odoo.http import request


class PortalEmployeeCodeController(http.Controller):
    def _get_current_employee(self):
        return request.env["hr.employee"].sudo().search(
            [("user_id", "=", request.env.user.id)],
            limit=1,
        )

    @http.route(["/my/employee-code"], type="http", auth="user", website=True)
    def portal_my_employee_code(self, **kwargs):
        employee = self._get_current_employee()
        values = {
            "page_name": "my_employee_code",
            "employee": employee,
            "employee_password": employee.employee_password if employee else False,
        }
        return request.render("pos_predefined_discounts.portal_my_employee_code", values)
