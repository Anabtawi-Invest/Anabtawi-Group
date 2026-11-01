# -*- coding: utf-8 -*-

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    employees = env["hr.employee"].with_context(active_test=False).search([("work_contact_id", "!=", False)])
    employees.work_contact_id._refresh_pos_customer_account_due()
