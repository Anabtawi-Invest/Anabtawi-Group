import logging

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ProductPricelist(models.Model):
    _inherit = "product.pricelist"

    cap_enabled = fields.Boolean(string="Enable Cap Discount")
    cap_amount = fields.Float(string="Cap Amount")
    has_fees = fields.Boolean(string="Has Fees")

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        if "cap_enabled" not in fields_to_load:
            fields_to_load.append("cap_enabled")
        if "cap_amount" not in fields_to_load:
            fields_to_load.append("cap_amount")
        if "has_fees" not in fields_to_load:
            fields_to_load.append("has_fees")
        return fields_to_load

    @api.model
    def get_pos_cap_evaluations(self, pricelist_id, lines):
        _logger.info(
            "POS discount cap evaluation started: pricelist_id=%s, line_count=%s, lines=%s",
            pricelist_id,
            len(lines or []),
            lines,
        )
        try:
            pricelist = self.browse(pricelist_id).exists()
            if not pricelist:
                _logger.warning(
                    "POS discount cap evaluation aborted: pricelist %s not found",
                    pricelist_id,
                )
                return []
            pricelist.ensure_one()

            Product = self.env["product.product"]
            date = fields.Datetime.now()
            result = []

            for line in lines or []:
                line_uuid = line.get("line_uuid")
                product_id = line.get("product_id")
                try:
                    product = Product.browse(product_id).exists()
                    qty = abs(float(line.get("qty") or 0.0))
                    price_type = line.get("price_type", "original")
                    is_original_price = price_type == "original"
                    can_apply_cap = bool(product and qty > 0 and is_original_price)

                    discounted_unit_price = 0.0
                    base_unit_price = 0.0
                    cap_eligible = False
                    rule_id = False

                    if product and qty > 0:
                        rule = pricelist._get_pos_preferred_rule(product, qty, date=date)
                        if rule:
                            rule_id = rule.id
                            _logger.debug(
                                "POS discount cap line %s: product_id=%s, rule_id=%s, "
                                "compute_price=%s, cap_eligible=%s",
                                line_uuid,
                                product_id,
                                rule_id,
                                rule.compute_price,
                                rule.cap_eligible,
                            )
                            price_kwargs = {
                                "product": product,
                                "quantity": qty,
                                "uom": product.uom_id,
                                "date": date,
                                "currency": pricelist.currency_id,
                            }
                            discounted_unit_price = rule._compute_price(**price_kwargs)
                            base_unit_price = rule._compute_price_before_discount(**price_kwargs)
                            cap_eligible = bool(rule.cap_eligible)
                        else:
                            discounted_unit_price, _rule_id = pricelist._get_product_price_rule(
                                product,
                                qty,
                                uom=product.uom_id,
                                date=date,
                            )
                            rule_id = _rule_id
                            base_unit_price = discounted_unit_price
                            _logger.debug(
                                "POS discount cap line %s: product_id=%s, no preferred rule, "
                                "fallback rule_id=%s, price=%s",
                                line_uuid,
                                product_id,
                                rule_id,
                                discounted_unit_price,
                            )
                    else:
                        _logger.debug(
                            "POS discount cap line %s skipped: product_id=%s, product_exists=%s, "
                            "qty=%s, price_type=%s",
                            line_uuid,
                            product_id,
                            bool(product),
                            qty,
                            price_type,
                        )

                    line_base_amount = (
                        qty * base_unit_price if cap_eligible and can_apply_cap else 0.0
                    )
                    pricelist_discount_percent = 0.0
                    full_line_discount_amount = 0.0
                    if cap_eligible and can_apply_cap and base_unit_price > 0:
                        pricelist_discount_percent = max(
                            0.0,
                            min(
                                100.0,
                                (1.0 - (discounted_unit_price / base_unit_price)) * 100.0,
                            ),
                        )
                        full_line_discount_amount = max(
                            0.0, qty * max(0.0, base_unit_price - discounted_unit_price)
                        )
                    result.append(
                        {
                            "line_uuid": line_uuid,
                            "cap_eligible": cap_eligible,
                            "can_apply_cap": can_apply_cap,
                            "line_base_amount": line_base_amount,
                            "discounted_unit_price": discounted_unit_price,
                            "base_unit_price": base_unit_price,
                            "pricelist_discount_percent": pricelist_discount_percent,
                            "full_line_discount_amount": full_line_discount_amount,
                            "rule_id": rule_id,
                        }
                    )
                except Exception:
                    _logger.exception(
                        "POS discount cap evaluation failed for line_uuid=%s, product_id=%s, "
                        "line_payload=%s",
                        line_uuid,
                        product_id,
                        line,
                    )
                    raise

            _logger.info(
                "POS discount cap evaluation completed: pricelist_id=%s, result=%s",
                pricelist_id,
                result,
            )
            return result
        except Exception:
            _logger.exception(
                "POS discount cap evaluation failed: pricelist_id=%s, lines=%s",
                pricelist_id,
                lines,
            )
            raise

    def _get_pos_preferred_rule(self, product, quantity, date=False):
        self.ensure_one()
        product.ensure_one()
        date = date or fields.Datetime.now()
        qty = abs(float(quantity or 0.0))
        if qty <= 0:
            return self.env["product.pricelist.item"]

        # Keep Odoo default order, but prefer cap-eligible when multiple rules match.
        rules = self._get_applicable_rules(product, date)
        applicable_rules = rules.filtered(lambda r: r._is_applicable_for(product, qty))
        cap_rules = applicable_rules.filtered("cap_eligible")
        return (cap_rules[:1] or applicable_rules[:1]) if applicable_rules else self.env[
            "product.pricelist.item"
        ]


class ProductPricelistItem(models.Model):
    _inherit = "product.pricelist.item"

    cap_eligible = fields.Boolean(string="Cap Eligible", default=False)

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        if "cap_eligible" not in fields_to_load:
            fields_to_load.append("cap_eligible")
        return fields_to_load

    @api.constrains("cap_eligible", "compute_price")
    def _check_cap_eligible_price_type(self):
        invalid_rules = self.filtered(
            lambda r: r.cap_eligible and r.compute_price not in ("percentage", "formula")
        )
        if invalid_rules:
            raise ValidationError(
                "Cap Eligible can only be used with percentage or formula pricelist rules."
            )

    @api.constrains(
        "cap_eligible", "applied_on", "pricelist_id", "product_id", "product_tmpl_id", "categ_id"
    )
    def _check_cap_eligible_uniqueness(self):
        for rule in self.filtered("cap_eligible"):
            domain = [
                ("id", "!=", rule.id),
                ("pricelist_id", "=", rule.pricelist_id.id),
                ("cap_eligible", "=", True),
            ]
            if rule.product_id:
                domain += [
                    "|",
                    ("product_id", "=", rule.product_id.id),
                    ("product_tmpl_id", "=", rule.product_id.product_tmpl_id.id),
                ]
            elif rule.product_tmpl_id:
                domain += [
                    "|",
                    ("product_tmpl_id", "=", rule.product_tmpl_id.id),
                    ("product_id.product_tmpl_id", "=", rule.product_tmpl_id.id),
                ]
            elif rule.categ_id:
                domain += [
                    ("categ_id", "=", rule.categ_id.id),
                    ("product_id", "=", False),
                    ("product_tmpl_id", "=", False),
                ]
            else:
                # Generic rules without product/template/category are also unique per pricelist.
                domain += [
                    ("categ_id", "=", False),
                    ("product_id", "=", False),
                    ("product_tmpl_id", "=", False),
                ]

            if self.search_count(domain):
                if rule.categ_id:
                    raise ValidationError(
                        "A category can only be included once in Cap Eligible rules for the same pricelist."
                    )
                raise ValidationError(
                    "Cap Eligible rules cannot be duplicated for the same target in one pricelist."
                )


class PosConfig(models.Model):
    _inherit = "pos.config"

    fee_product_id = fields.Many2one(
        "product.product",
        string="Fees Product",
        domain=[("sale_ok", "=", True), ("available_in_pos", "=", True)],
        help="Product used to add the POS fee line during order validation.",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_fee_product_id = fields.Many2one(
        "product.product",
        related="pos_config_id.fee_product_id",
        string="Fees Product",
        readonly=False,
        domain=[("sale_ok", "=", True), ("available_in_pos", "=", True)],
    )
