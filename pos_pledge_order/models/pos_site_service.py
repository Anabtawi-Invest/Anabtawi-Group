# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class PosSiteServiceMenu(models.Model):
    _name = "pos.site.service.menu"
    _description = "POS Site Service Menu"
    _inherit = ["pos.load.mixin"]
    _order = "id"

    name = fields.Char(string="Menu Name", required=True, default="Site Service")
    active = fields.Boolean(default=True)
    enable_site_service = fields.Boolean(
        string="Site Service",
        default=False,
        help="When enabled, the cutting service logic is applied at every Point of Sale.",
    )
    threshold = fields.Float(
        string="Threshold",
        default=31.0,
        help="Minimum score (sum of Quantity × Multiple) required to waive the cutting service.",
    )
    service_product_id = fields.Many2one(
        "product.product",
        string="Service Product",
        domain=[("available_in_pos", "=", True), ("sale_ok", "=", True)],
        help="Product representing the on-site cutting service.",
    )
    service_price = fields.Float(
        string="Service Price",
        digits="Product Price",
        help="Unit price used when the service product is added automatically.",
    )
    line_ids = fields.One2many(
        "pos.site.service.product.line",
        "menu_id",
        string="Products",
    )

    @api.model_create_multi
    def create(self, vals_list):
        if self.search_count([]):
            raise ValidationError(_("Only one site service configuration is allowed for all companies."))
        return super().create(vals_list)

    @api.constrains(
        "enable_site_service",
        "threshold",
        "service_product_id",
        "service_price",
    )
    def _check_site_service_configuration(self):
        for menu in self:
            if not menu.enable_site_service:
                continue
            if menu.threshold <= 0:
                raise ValidationError(_("Site service threshold must be greater than zero."))
            if not menu.service_product_id:
                raise ValidationError(_("Please select a service product for site service."))
            if menu.service_price < 0:
                raise ValidationError(_("Site service price cannot be negative."))

    @api.model
    def get_settings(self):
        """Return the single global site service record, creating it if needed."""
        menu = self.search([], limit=1)
        if not menu:
            menu = self.create({"name": _("Site Service")})
        return menu

    @api.model
    def action_open_settings(self):
        menu = self.get_settings()
        return {
            "type": "ir.actions.act_window",
            "name": _("Site Service"),
            "res_model": "pos.site.service.menu",
            "view_mode": "form",
            "res_id": menu.id,
            "target": "current",
        }

    @api.model
    def _load_pos_data_search_read(self, data, config):
        try:
            records = super()._load_pos_data_search_read(data, config)
            _logger.info(
                "[SITE_SERVICE] Loaded %s global menu record(s) for POS config id=%s",
                len(records),
                config.id,
            )
            return records
        except Exception:
            _logger.exception(
                "[SITE_SERVICE] Failed to load pos.site.service.menu for POS config id=%s",
                config.id,
            )
            raise

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [("active", "=", True), ("enable_site_service", "=", True)]

    @api.model
    def _load_pos_data_fields(self, config):
        return [
            "id",
            "name",
            "enable_site_service",
            "threshold",
            "service_product_id",
            "service_price",
        ]


class PosSiteServiceProductLine(models.Model):
    _name = "pos.site.service.product.line"
    _description = "POS Site Service Product Line"
    _inherit = ["pos.load.mixin"]
    _order = "id"

    menu_id = fields.Many2one(
        "pos.site.service.menu",
        string="Site Service Menu",
        required=True,
        ondelete="cascade",
        index=True,
    )
    active = fields.Boolean(
        related="menu_id.active",
        store=True,
        readonly=True,
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
        help="Weight factor used in site service score: Quantity × Multiple.",
    )
    pledge_product_id = fields.Many2one(
        "product.product",
        string="Pledge Product",
        domain=[("available_in_pos", "=", True), ("sale_ok", "=", True)],
        help="Pledge product added on advance orders when Site Service is not selected.",
    )

    @api.constrains("multiple")
    def _check_multiple_positive(self):
        for line in self:
            if line.multiple <= 0:
                raise ValidationError(_("Multiple must be greater than zero."))

    @api.model
    def _load_pos_data_search_read(self, data, config):
        try:
            records = super()._load_pos_data_search_read(data, config)
            _logger.info(
                "[SITE_SERVICE] Loaded %s global product line(s) for POS config id=%s",
                len(records),
                config.id,
            )
            return records
        except Exception:
            _logger.exception(
                "[SITE_SERVICE] Failed to load pos.site.service.product.line for POS config id=%s",
                config.id,
            )
            raise

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [
            ("menu_id.active", "=", True),
            ("menu_id.enable_site_service", "=", True),
        ]

    @api.model
    def _load_pos_data_fields(self, config):
        return ["id", "menu_id", "product_id", "multiple", "pledge_product_id", "active"]
