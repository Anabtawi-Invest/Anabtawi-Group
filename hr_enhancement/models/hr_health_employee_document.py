# -*- coding: utf-8 -*-

from odoo import fields, models


class HrHealthEmployeeDocument(models.Model):
    _inherit = "hr.health.employee.document"

    # 0 = none; 1 = expiring soon; 2 = overdue (used by hr_enhancement expiry cron)
    notify_stage = fields.Integer(string="Notify stage", default=0, copy=False)

    def write(self, vals):
        vals = dict(vals or {})
        if "expiry_date" in vals:
            vals["notify_stage"] = 0
        return super().write(vals)
