# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    legal_first_name = fields.Char(string="First", groups="hr.group_hr_user")
    legal_father_name = fields.Char(string="Father", groups="hr.group_hr_user")
    legal_grandfather_name = fields.Char(string="Grandfather", groups="hr.group_hr_user")
    legal_family_name = fields.Char(string="Family", groups="hr.group_hr_user")
    tax_id = fields.Char(
        string="Tax ID",
        related='work_contact_id.vat',
        store=True,
        readonly=False,
        groups="hr.group_hr_user",
    )
