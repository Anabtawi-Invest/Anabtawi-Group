# -*- coding: utf-8 -*-

from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    visit_ids = fields.One2many(
        'sales.visit',
        'employee_id',
        string='Sales Visits'
    )
    route_point_ids = fields.One2many(
        'sales.route.point',
        'employee_id',
        string='Route Tracking Logs'
    )
