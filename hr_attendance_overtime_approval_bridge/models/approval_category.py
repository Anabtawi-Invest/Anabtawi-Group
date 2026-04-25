# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ApprovalCategory(models.Model):
    _inherit = "approval.category"

    is_overtime_category = fields.Boolean(
        string="Overtime Category",
        help="Use this category for overtime requests linked to attendance extra hours.",
    )
