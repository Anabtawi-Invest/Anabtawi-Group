# -*- coding: utf-8 -*-

from odoo import api, models


class HrVersion(models.Model):
    _inherit = "hr.version"

    @api.model_create_multi
    def create(self, vals_list):
        versions = super().create(vals_list)
        versions.employee_id._sync_employee_due_credit_limit()
        return versions

    def write(self, vals):
        res = super().write(vals)
        if {"wage", "date_version", "employee_id"} & set(vals):
            self.employee_id._sync_employee_due_credit_limit()
        return res
