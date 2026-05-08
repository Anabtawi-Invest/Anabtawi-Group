# -*- coding: utf-8 -*-

from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    ae_is_non_resident = fields.Boolean(
        string="Non-resident",
        groups="hr.group_hr_user",
        help="Indicates the employee should be classified as non-resident for statutory fields.",
    )
    ae_children_of_jordanian_mother = fields.Boolean(
        string="Children of Jordanian Mothers",
        groups="hr.group_hr_user",
    )
    ae_gaza_resident = fields.Boolean(
        string="Gaza Residents",
        groups="hr.group_hr_user",
    )
