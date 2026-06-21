# -*- coding: utf-8 -*-

from odoo import fields, models


class PlanningSlot(models.Model):
    _inherit = 'planning.slot'

    visit_ids = fields.One2many(
        'sales.visit',
        'planning_slot_id',
        string='Customer Visits',
        help="Sales visits assigned to this planning schedule."
    )


class SalesVisit(models.Model):
    _inherit = 'sales.visit'

    planning_slot_id = fields.Many2one(
        'planning.slot',
        string='Planning Slot',
        tracking=True,
        help="The employee planning shift during which this visit is scheduled."
    )
