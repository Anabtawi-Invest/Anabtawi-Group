# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ReportEmployeeProfileDocument(models.AbstractModel):
    _name = 'report.anabtawi_employee_profile.report_employee_profile_document'
    _description = 'Employee Profile PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['hr.employee'].sudo().browse(docids)
        dep_map = {
            emp.id: emp.health_insurance_ids.filtered(
                lambda r: r.relationship != 'employee'
            )
            for emp in docs
        }
        tz_now = fields.Datetime.context_timestamp(
            self.env.user, fields.Datetime.now()
        )
        return {
            'doc_ids': docids,
            'doc_model': 'hr.employee',
            'docs': docs,
            'dep_map': dep_map,
            'print_user': self.env.user,
            'print_time': tz_now,
        }
