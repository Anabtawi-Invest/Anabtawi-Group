from odoo import fields, api, models


class StockPickingExt(models.Model):
    _inherit = 'stock.picking'

    picking_type_id = fields.Many2one(
        'stock.picking.type',
        string="Operation Type",
        domain="[('id', 'in', new_picking_type_ids)]",
    )
    new_picking_type_ids = fields.Many2many(
        'stock.picking.type',
        string="Allowed Operation Types",
        compute='_compute_warehouse_restrictions',
    )

    location_id = fields.Many2one(
        'stock.location',
        string="Source Location",
        domain="[('id', 'in', new_location_ids)]",
    )
    new_location_ids = fields.Many2many(
        'stock.location',
        string="Allowed Source Locations",
        compute='_compute_warehouse_restrictions',
    )

    location_dest_id = fields.Many2one(
        'stock.location',
        string="Destination Location",
        domain="[('id', 'in', new_location_ids)]",
    )

    def _get_user_allowed_picking_type_ids(self):
        """Return picking type ids allowed for the current user (no DB write)."""
        user = self.env.user
        if not user.has_group('warehouse_restriction_for_user.ware_house_user_restrict'):
            return self.env['stock.picking.type'].search([]).ids
        if user.restrict_ware_house:
            warehouse_ids = user.allowed_ware_house_ids.ids
            return self.env['stock.picking.type'].search(
                [('warehouse_id', 'in', warehouse_ids)]
            ).ids
        return self.env['stock.picking.type'].search(
            [('id', 'in', user.ware_house_picking_type_ids.ids)]
        ).ids

    def _get_user_allowed_location_ids(self):
        """Return location ids allowed for the current user (no DB write)."""
        user = self.env.user
        if not user.has_group('warehouse_restriction_for_user.ware_house_user_restrict'):
            return self.env['stock.location'].search([]).ids
        if user.restrict_ware_house:
            warehouse_ids = user.allowed_ware_house_ids.ids
            return self.env['stock.location'].search(
                [('warehouse_id', 'in', warehouse_ids)]
            ).ids
        return user.allow_location_ids.ids

    @api.depends()
    def _compute_warehouse_restrictions(self):
        picking_type_ids = self._get_user_allowed_picking_type_ids()
        location_ids = self._get_user_allowed_location_ids()
        for picking in self:
            picking.new_picking_type_ids = [(6, 0, picking_type_ids)]
            picking.new_location_ids = [(6, 0, location_ids)]

    @api.onchange('user_id')
    def get_records(self):
        return {
            'domain': {
                'picking_type_id': [('id', 'in', self._get_user_allowed_picking_type_ids())],
                'location_id': [('id', 'in', self._get_user_allowed_location_ids())],
                'location_dest_id': [('id', 'in', self._get_user_allowed_location_ids())],
            }
        }
