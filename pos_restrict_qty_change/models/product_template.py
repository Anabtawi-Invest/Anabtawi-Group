from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    pos_allowed_change_qty = fields.Boolean(
        string="Allowed Change Qty",
        default=False,
        help="If checked, users in the 'Restricted users from changing qty in POS' "
        "group cannot change this product's quantity in POS. "
        "Returns/refunds are always allowed. Other apps are not affected.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        if "pos_allowed_change_qty" not in fields_to_load:
            fields_to_load.append("pos_allowed_change_qty")
        return fields_to_load


class ProductProduct(models.Model):
    _inherit = "product.product"

    pos_allowed_change_qty = fields.Boolean(
        related="product_tmpl_id.pos_allowed_change_qty",
        readonly=True,
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        if "pos_allowed_change_qty" not in fields_to_load:
            fields_to_load.append("pos_allowed_change_qty")
        return fields_to_load
