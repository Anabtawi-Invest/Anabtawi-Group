# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

class CeoCostDashboardController(http.Controller):

    @http.route('/ceo_cost_dashboard/get_data', type='json', auth='user')
    def get_dashboard_data(self, **kwargs):
        report_model = request.env['ceo.cost.dashboard.report']
        return report_model.get_executive_dashboard_data(kwargs)
