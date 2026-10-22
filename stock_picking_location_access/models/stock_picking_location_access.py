from odoo import api, fields, models
from odoo.exceptions import ValidationError


class StockPickingLocationAccess(models.Model):
    _name = "stock.picking.location.access"
    _description = "Transfer Location Access Rule"
    _order = "location_id, location_dest_id"

    name = fields.Char(compute="_compute_name", store=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    location_id = fields.Many2one(
        "stock.location",
        string="From Location",
        required=True,
        index=True,
        check_company=True,
    )
    location_dest_id = fields.Many2one(
        "stock.location",
        string="To Location",
        required=True,
        index=True,
        check_company=True,
    )
    user_ids = fields.Many2many(
        "res.users",
        "stock_picking_location_access_user_rel",
        "access_id",
        "user_id",
        string="Allowed Users",
        required=True,
        domain="[('share', '=', False)]",
        help="Only these users can edit, validate, or change transfers "
        "from this From location to this To location. "
        "Other users can still view and print reports. "
        "If no rule exists for a From/To path, normal Odoo access applies.",
    )

    _sql_constraints = [
        (
            "uniq_company_locations",
            "unique(company_id, location_id, location_dest_id)",
            "An access rule already exists for this company and From/To locations.",
        ),
    ]

    @api.depends("location_id", "location_dest_id")
    def _compute_name(self):
        for rule in self:
            src = rule.location_id.display_name or ""
            dest = rule.location_dest_id.display_name or ""
            rule.name = f"{src} → {dest}" if src or dest else ""

    @api.constrains("location_id", "location_dest_id")
    def _check_locations_different(self):
        for rule in self:
            if rule.location_id and rule.location_dest_id and rule.location_id == rule.location_dest_id:
                raise ValidationError(
                    self.env._("From Location and To Location must be different.")
                )

    @api.constrains("user_ids")
    def _check_user_ids(self):
        for rule in self:
            if not rule.user_ids:
                raise ValidationError(
                    self.env._("Please select at least one allowed user.")
                )
