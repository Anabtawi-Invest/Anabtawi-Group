# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PortalTransferLocationMap(models.Model):
    _name = "portal.transfer.location.map"
    _description = "Portal Transfer Source Location Mapping"
    _rec_name = "user_id"
    _order = "user_id"

    user_id = fields.Many2one(
        "res.users",
        string="Portal User",
        required=True,
        ondelete="cascade",
        index=True,
        domain="[('share', '=', True)]",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Source Location",
        required=True,
        ondelete="restrict",
        domain="[('usage', '=', 'internal'), ('active', '=', True)]",
        check_company=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="location_id.company_id",
        store=True,
        readonly=True,
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "portal_transfer_location_map_user_uniq",
            "unique(user_id)",
            "Each portal user can have only one source location mapping.",
        ),
    ]

    @api.constrains("location_id")
    def _check_location_internal(self):
        for rec in self:
            if rec.location_id and rec.location_id.usage != "internal":
                raise ValidationError(_("Source location must be an internal location."))
