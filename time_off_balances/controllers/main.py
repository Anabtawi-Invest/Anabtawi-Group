# -*- coding: utf-8 -*-
import re
from odoo import _, http
from odoo.http import content_disposition, request
from odoo.tools import osutil


class TimeOffBalancesXlsxController(http.Controller):

    @http.route(
        ['/time_off_balances/export_xlsx/<int:wizard_id>'],
        type='http',
        auth='user',
    )
    def download_time_off_balances_xlsx(self, wizard_id, **kwargs):
        wizard = request.env['time.off.balances.wizard'].browse(wizard_id)
        if not wizard.exists():
            return request.not_found()

        xlsx_data = wizard._generate_xlsx_content()
        emp_name = wizard.employee_id.name or 'Employee'
        # Sanitize filename
        safe_name = re.sub(r'[\\/*?:"<>| ]', '_', emp_name)
        filename = f"Vacations_{safe_name}.xlsx"

        headers = [
            (
                'Content-Type',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            ),
            ('Content-Disposition', content_disposition(filename)),
        ]
        return request.make_response(xlsx_data, headers=headers)
