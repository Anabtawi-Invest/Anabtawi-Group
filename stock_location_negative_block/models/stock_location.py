from odoo import fields, models


class StockLocation(models.Model):
    _inherit = "stock.location"

    restrict_negative = fields.Boolean(
        string="Restrict Negative Stock",
        help="If enabled, any stock move leaving this location that would make "
             "stock negative will be blocked, except for Allowed Users.",
    )
    allowed_negative_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="stock_location_allowed_negative_user_rel",
        column1="location_id",
        column2="user_id",
        string="Allowed Users",
        help="Users allowed to create negative stock on this location when "
             "Restrict Negative Stock is enabled.",
    )

    def _blocks_negative_stock_for(self, user=None):
        """Return True if negative stock must be blocked for the given user."""
        self.ensure_one()
        if not self.restrict_negative:
            return False
        user = user or self.env.user
        return user not in self.allowed_negative_user_ids
