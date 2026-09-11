# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)


class PosOnsitePosLoadMixin(models.AbstractModel):
    _name = "pos.onsite.pos.load.mixin"
    _description = "Force full POS load of on-site price records"

    def _last_server_date_to_load(self):
        # These tables are small. Incremental IndexedDB sync skipped records
        # created before the models were registered, so always send a full load.
        return False

    @api.model
    def _load_pos_data_search_read(self, data, config):
        records = super(PosOnsitePosLoadMixin, self.sudo())._load_pos_data_search_read(data, config)
        _logger.info(
            "[ONSITE] Loaded %s for POS config id=%s count=%s",
            self._name,
            getattr(config, "id", config),
            len(records or []),
        )
        return records


class PosOnsitePriceMenu(models.Model):
    _name = "pos.onsite.price.menu"
    _description = "POS On-Site Price Menu"
    _inherit = ["pos.load.mixin", "pos.onsite.pos.load.mixin"]
    _order = "id"

    name = fields.Char(string="Name", related="pos_config_id.name", store=True, readonly=True)
    pos_config_id = fields.Many2one(
        "pos.config",
        string="Point of Sale",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        related="pos_config_id.company_id",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="pos_config_id.currency_id",
        store=True,
        readonly=True,
    )
    range_ids = fields.One2many(
        "pos.onsite.price.range",
        "menu_id",
        string="Quantity Ranges",
    )
    product_line_ids = fields.One2many(
        "pos.onsite.price.product",
        "menu_id",
        string="Products",
    )

    _pos_config_uniq = models.Constraint(
        "unique(pos_config_id)",
        "Only one on-site price menu is allowed per Point of Sale.",
    )

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [("pos_config_id", "=", config.id)]

    @api.model
    def _load_pos_data_fields(self, config):
        return ["id", "name", "pos_config_id"]


class PosOnsitePriceRange(models.Model):
    _name = "pos.onsite.price.range"
    _description = "POS On-Site Price Range"
    _inherit = ["pos.load.mixin", "pos.onsite.pos.load.mixin"]
    _order = "is_on_site desc, min_qty, id"

    menu_id = fields.Many2one(
        "pos.onsite.price.menu",
        string="On-Site Price Menu",
        required=True,
        ondelete="cascade",
        index=True,
    )
    name = fields.Char(compute="_compute_name", store=True)
    is_on_site = fields.Boolean(
        string="On Site",
        default=True,
        help="True: used when the cashier answers Yes. False: used when the cashier answers No.",
    )
    min_qty = fields.Float(string="Min Quantity", required=True, default=0.0)
    max_qty = fields.Float(string="Max Quantity", required=True, default=0.0)
    price_per_kilo = fields.Float(
        string="Price Per Kilo",
        digits="Product Price",
        required=True,
        default=0.0,
    )
    currency_id = fields.Many2one(related="menu_id.currency_id", store=True, readonly=True)

    @api.depends("min_qty", "max_qty", "is_on_site")
    def _compute_name(self):
        for rng in self:
            label = _("On Site") if rng.is_on_site else _("Not On Site")
            rng.name = "%s: %s - %s" % (label, rng.min_qty or 0.0, rng.max_qty or 0.0)

    @api.constrains("min_qty", "max_qty", "price_per_kilo")
    def _check_range_values(self):
        for rng in self:
            if float_compare(rng.min_qty, 0.0, precision_digits=4) < 0:
                raise ValidationError(_("Min quantity cannot be negative."))
            if float_compare(rng.max_qty, rng.min_qty, precision_digits=4) < 0:
                raise ValidationError(_("Max quantity must be greater than or equal to min quantity."))
            if float_compare(rng.price_per_kilo, 0.0, precision_digits=4) < 0:
                raise ValidationError(_("Price per kilo cannot be negative."))

    @api.constrains("menu_id", "is_on_site", "min_qty", "max_qty")
    def _check_ranges_do_not_overlap(self):
        for rng in self:
            siblings = self.search(
                [
                    ("menu_id", "=", rng.menu_id.id),
                    ("is_on_site", "=", rng.is_on_site),
                    ("id", "!=", rng.id),
                ]
            )
            for other in siblings:
                overlap = (
                    float_compare(rng.min_qty, other.max_qty, precision_digits=4) <= 0
                    and float_compare(other.min_qty, rng.max_qty, precision_digits=4) <= 0
                )
                if overlap:
                    raise ValidationError(
                        _("Quantity ranges for the same On Site value cannot overlap (%s and %s).")
                        % (rng.name or rng.id, other.name or other.id)
                    )

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [("menu_id.pos_config_id", "=", config.id)]

    @api.model
    def _load_pos_data_fields(self, config):
        return ["id", "menu_id", "name", "is_on_site", "min_qty", "max_qty", "price_per_kilo"]


class PosOnsitePriceProduct(models.Model):
    _name = "pos.onsite.price.product"
    _description = "POS On-Site Price Product"
    _inherit = ["pos.load.mixin", "pos.onsite.pos.load.mixin"]
    _order = "id"

    menu_id = fields.Many2one(
        "pos.onsite.price.menu",
        string="On-Site Price Menu",
        required=True,
        ondelete="cascade",
        index=True,
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        domain=[("available_in_pos", "=", True)],
    )
    multiple = fields.Float(
        string="Multiple",
        required=True,
        default=1.0,
        help="Conversion factor: effective quantity = order quantity × multiple.",
    )

    _product_menu_uniq = models.Constraint(
        "unique(menu_id, product_id)",
        "Each product can appear only once in an on-site price menu.",
    )

    @api.constrains("multiple")
    def _check_multiple_positive(self):
        for line in self:
            if float_compare(line.multiple, 0.0, precision_digits=4) <= 0:
                raise ValidationError(_("Multiple must be greater than zero."))

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [("menu_id.pos_config_id", "=", config.id)]

    @api.model
    def _load_pos_data_fields(self, config):
        return ["id", "menu_id", "product_id", "multiple"]
