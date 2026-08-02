# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CakeSize(models.Model):
    _name = "cake.size"
    _description = "Cake Size"
    _order = "pieces asc"

    pieces = fields.Integer(string="Cake Pieces", required=True)
    product_id = fields.Many2one(
        "product.product",
        string="POS Product",
        required=True,
        domain=[("available_in_pos", "=", True)],
    )
    cake_base_cost = fields.Float(
        string="Cake Base",
        digits="Product Price",
        default=0.0,
        help="Fixed base cost for this cake size. Added once to the total components cost.",
    )
    active = fields.Boolean(default=True)
    name = fields.Char(string="Name", compute="_compute_name", store=True)

    _sql_constraints = [
        ("pieces_unique", "unique(pieces)", "Cake pieces must be unique."),
    ]

    @api.depends("pieces")
    def _compute_name(self):
        for record in self:
            record.name = _("%s Pieces", record.pieces) if record.pieces else ""

    @api.constrains("pieces")
    def _check_pieces(self):
        for record in self:
            if record.pieces <= 0:
                raise ValidationError(_("Cake pieces must be greater than zero."))

    @api.constrains("cake_base_cost")
    def _check_cake_base_cost(self):
        for record in self:
            if record.cake_base_cost < 0:
                raise ValidationError(_("Cake base cost cannot be negative."))

    def name_get(self):
        return [(record.id, record.name or str(record.pieces)) for record in self]
