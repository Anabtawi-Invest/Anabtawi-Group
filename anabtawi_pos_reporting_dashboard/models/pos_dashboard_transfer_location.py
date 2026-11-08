# -*- coding: utf-8 -*-
from odoo import fields, models


class PosDashboardTransferLocation(models.Model):
    """POS branch → stock location used only by the Transfers dashboard."""

    _name = "pos.dashboard.transfer.location"
    _description = "POS Dashboard Transfer Location"
    _order = "config_id"
    _rec_name = "config_id"

    config_id = fields.Many2one(
        "pos.config",
        string="POS Branch",
        required=True,
        ondelete="cascade",
        index=True,
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Transfer Stock Location",
        required=True,
        ondelete="restrict",
        domain="[('usage', '=', 'internal')]",
        help="Destination location (or parent) of branch receipts from تسليم الطلبيات. "
             "Used only by the POS Transfers dashboard.",
    )
    company_id = fields.Many2one(
        related="config_id.company_id",
        store=True,
        readonly=True,
    )
    active = fields.Boolean(default=True)

    _config_uniq = models.Constraint(
        "unique(config_id)",
        "This POS branch already has a transfer location for the dashboard.",
    )
