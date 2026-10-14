# -*- coding: utf-8 -*-
from odoo import fields, models


class HrWorkLocation(models.Model):
    _inherit = "hr.work.location"

    is_administration = fields.Boolean(
        string="Administration",
        help="Employees of this work location are not counted in the POS dashboard "
             "attendance, labor cost and extra hours figures.",
    )
    pos_config_id = fields.Many2one(
        "pos.config",
        string="POS Branch",
        help="Attendances checked in within this location's radius are credited to this POS branch.",
    )
