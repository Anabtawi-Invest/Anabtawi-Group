# -*- coding: utf-8 -*-
import json
from odoo import http
from odoo.http import request


class HrPayrollDashboardController(http.Controller):

    @http.route("/anabtawi_payroll/dashboard/data", type="json", auth="user")
    def get_dashboard_data(self, **kwargs):
        """API endpoint for fetching executive dashboard data asynchronously."""
        date_from = kwargs.get("date_from")
        date_to = kwargs.get("date_to")
        payrun_id = kwargs.get("payrun_id")
        company_id = kwargs.get("company_id")
        department_ids = kwargs.get("department_ids")

        data = request.env["hr.payroll.dashboard"].get_dashboard_data(
            date_from=date_from,
            date_to=date_to,
            payrun_id=payrun_id,
            company_id=company_id,
            department_ids=department_ids,
        )
        return data
