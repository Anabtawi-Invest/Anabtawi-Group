# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    ceo_dashboard_monthly_revenue_target = fields.Monetary(
        string='Monthly Revenue Target', currency_field='currency_id', default=0.0)
    ceo_dashboard_billable_hours_target = fields.Float(
        string='Monthly Billable Hours Target', default=0.0)
    ceo_dashboard_late_checkin_time = fields.Float(
        string='Expected Check-in Time (Late After)', default=9.5,
        help='Hour of day (24h, decimal) after which a clock-in is considered late, e.g. 9.5 = 9:30 AM')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ceo_dashboard_monthly_revenue_target = fields.Monetary(
        related='company_id.ceo_dashboard_monthly_revenue_target', readonly=False,
        currency_field='currency_id')
    ceo_dashboard_billable_hours_target = fields.Float(
        related='company_id.ceo_dashboard_billable_hours_target', readonly=False)
    ceo_dashboard_late_checkin_time = fields.Float(
        related='company_id.ceo_dashboard_late_checkin_time', readonly=False)
    currency_id = fields.Many2one(related='company_id.currency_id', readonly=True)
