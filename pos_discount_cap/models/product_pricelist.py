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
        if not fields_to_load:
            return fields_to_load
        if "cap_enabled" not in fields_to_load:
            fields_to_load.append("cap_enabled")
        if "cap_amount" not in fields_to_load:
            fields_to_load.append("cap_amount")
        if "has_fees" not in fields_to_load:
            fields_to_load.append("has_fees")
        return fields_to_load

    @staticmethod
    def _get_rule_discount_percent(rule):
        if not rule:
            return 0.0
        if rule.compute_price == "percentage":
            return rule.percent_price or 0.0
        if rule.compute_price == "formula" and rule.base != "standard_price":
            return rule.price_discount or 0.0
        return 0.0

    def _get_cap_eligible_rules_domain(self, date=False):
        self.ensure_one()
        date = date or fields.Datetime.now()
        return [
            ("pricelist_id", "=", self.id),
            ("cap_eligible", "=", True),
            "|",
            ("date_start", "=", False),
            ("date_start", "<=", date),
            "|",
            ("date_end", "=", False),
            ("date_end", ">=", date),
        ]

    def _get_pos_cap_rule(self, product, quantity, date=False, debug=None):
        """Return the cap-eligible pricelist rule for a POS line."""
        self.ensure_one()
        if debug is not None:
            debug.setdefault("steps", [])

        def _step(message, **extra):
            if debug is not None:
                entry = {"message": message}
                entry.update(extra)
                debug["steps"].append(entry)
            _logger.info(
                "[pos_discount_cap] pricelist=%s product=%s qty=%s | %s | %s",
                self.id,
                product.id if product else None,
                quantity,
                message,
                extra,
            )

        if not product:
            _step("no_product")
            return self.env["product.pricelist.item"]
        product.ensure_one()
        date = date or fields.Datetime.now()
        qty = abs(float(quantity or 0.0))
        if qty <= 0:
            _step("invalid_qty", qty=qty)
            return self.env["product.pricelist.item"]

        Item = self.env["product.pricelist.item"]
        applicable_rules = self._get_applicable_rules(product, date)
        _step(
            "applicable_rules_loaded",
            rule_count=len(applicable_rules),
            rule_ids=applicable_rules.ids,
        )

        for rule in applicable_rules:
            is_applicable = rule._is_applicable_for(product, qty)
            _step(
                "check_applicable_rule",
                rule_id=rule.id,
                cap_eligible=rule.cap_eligible,
                applied_on=rule.applied_on,
                is_applicable=is_applicable,
            )
            if rule.cap_eligible and is_applicable:
                _step("matched_applicable_cap_rule", rule_id=rule.id)
                return rule

        rule_id = self._get_product_rule(
            product,
            quantity=qty,
            uom=product.uom_id,
            date=date,
        )
        _step("product_rule_lookup", rule_id=rule_id)
        if rule_id:
            rule = Item.browse(rule_id)
            if rule.exists() and rule.cap_eligible:
                _step("matched_product_cap_rule", rule_id=rule.id)
                return rule
            _step(
                "product_rule_not_cap_eligible",
                rule_id=rule_id,
                cap_eligible=bool(rule.cap_eligible) if rule.exists() else False,
            )

        cap_rules = Item.search(
            self._get_cap_eligible_rules_domain(date),
            order="applied_on, min_quantity desc, categ_id desc, id desc",
        )
        _step(
            "cap_rules_search",
            rule_count=len(cap_rules),
            rule_ids=cap_rules.ids,
        )
        for rule in cap_rules:
            is_applicable = rule._is_applicable_for(product, qty)
            _step(
                "check_cap_rule",
                rule_id=rule.id,
                applied_on=rule.applied_on,
                is_applicable=is_applicable,
            )
            if is_applicable:
                _step("matched_cap_rule_search", rule_id=rule.id)
                return rule

        global_cap_rules = cap_rules.filtered(lambda r: r.applied_on == "3_global")
        if global_cap_rules:
            _step("matched_global_cap_rule", rule_id=global_cap_rules[0].id)
            return global_cap_rules[0]

        _step("no_cap_rule_found")
        return Item

    @staticmethod
    def _line_skip_reason(product, qty, price_type, can_apply_cap, cap_eligible, rule_id):
        if not product:
            return "missing_product"
        if qty <= 0:
            return "invalid_qty"
        if price_type == "manual":
            return "manual_price_type"
        if not cap_eligible:
            return "no_cap_eligible_rule" if not rule_id else "rule_not_cap_eligible"
        if not can_apply_cap:
            return "cannot_apply_cap"
        return None

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
            date = fields.Datetime.now()

            cap_rules_on_pricelist = self.env["product.pricelist.item"].search(
                pricelist._get_cap_eligible_rules_domain(date)
            )
            _logger.info(
                "[pos_discount_cap] pricelist context: id=%s name=%s cap_enabled=%s "
                "cap_amount=%s cap_rule_count=%s cap_rule_ids=%s cap_rules=%s",
                pricelist.id,
                pricelist.display_name,
                pricelist.cap_enabled,
                pricelist.cap_amount,
                len(cap_rules_on_pricelist),
                cap_rules_on_pricelist.ids,
                [
                    {
                        "id": rule.id,
                        "applied_on": rule.applied_on,
                        "compute_price": rule.compute_price,
                        "price_discount": rule.price_discount,
                        "percent_price": rule.percent_price,
                        "cap_eligible": rule.cap_eligible,
                        "base": rule.base,
                        "base_pricelist_id": rule.base_pricelist_id.id
                        if rule.base_pricelist_id
                        else False,
                    }
                    for rule in cap_rules_on_pricelist
                ],
            )

            Product = self.env["product.product"]
            result = []

            for line in lines or []:
                line_uuid = line.get("line_uuid")
                product_id = line.get("product_id")
                if isinstance(product_id, (list, tuple)):
                    product_id = product_id[0] if product_id else False
                try:
                    product = Product.browse(product_id).exists()
                    qty = abs(float(line.get("qty") or 0.0))
                    price_type = line.get("price_type", "original")
                    line_price_unit = abs(float(line.get("price_unit") or 0.0))
                    can_apply_cap = bool(
                        product and qty > 0 and price_type != "manual"
                    )

                    discounted_unit_price = 0.0
                    base_unit_price = 0.0
                    cap_eligible = False
                    rule_id = False
                    line_debug = {}

                    if product and qty > 0:
                        rule = pricelist._get_pos_cap_rule(
                            product, qty, date=date, debug=line_debug
                        )
                        if rule:
                            rule_id = rule.id
                            _logger.info(
                                "[pos_discount_cap] line %s product=%s (%s) matched rule=%s "
                                "cap_eligible=%s compute_price=%s discount=%s",
                                line_uuid,
                                product_id,
                                product.display_name,
                                rule_id,
                                rule.cap_eligible,
                                rule.compute_price,
                                self._get_rule_discount_percent(rule),
                            )
                            price_kwargs = {
                                "product": product,
                                "quantity": qty,
                                "uom": product.uom_id,
                                "date": date,
                                "currency": pricelist.currency_id,
                            }
                            cap_eligible = bool(rule.cap_eligible)
                            rule_discount_percent = self._get_rule_discount_percent(rule)
                            if can_apply_cap and line_price_unit > 0:
                                base_unit_price = line_price_unit
                            else:
                                base_unit_price = rule._compute_price_before_discount(
                                    **price_kwargs
                                )
                            if rule_discount_percent and base_unit_price > 0:
                                unit_discount = base_unit_price * (
                                    rule_discount_percent / 100.0
                                )
                                discounted_unit_price = base_unit_price - unit_discount
                            else:
                                discounted_unit_price = rule._compute_price(**price_kwargs)
                                if not base_unit_price:
                                    base_unit_price = rule._compute_price_before_discount(
                                        **price_kwargs
                                    )
                        else:
                            discounted_unit_price, _rule_id = pricelist._get_product_price_rule(
                                product,
                                qty,
                                uom=product.uom_id,
                                date=date,
                            )
                            rule_id = _rule_id
                            fallback_rule = self.env["product.pricelist.item"].browse(
                                rule_id
                            ).exists()
                            if fallback_rule and fallback_rule.cap_eligible:
                                rule = fallback_rule
                                cap_eligible = True
                                rule_discount_percent = self._get_rule_discount_percent(rule)
                                if can_apply_cap and line_price_unit > 0:
                                    base_unit_price = line_price_unit
                                else:
                                    base_unit_price = rule._compute_price_before_discount(
                                        product=product,
                                        quantity=qty,
                                        uom=product.uom_id,
                                        date=date,
                                        currency=pricelist.currency_id,
                                    )
                                if rule_discount_percent and base_unit_price > 0:
                                    unit_discount = base_unit_price * (
                                        rule_discount_percent / 100.0
                                    )
                                    discounted_unit_price = base_unit_price - unit_discount
                                else:
                                    discounted_unit_price = discounted_unit_price
                            else:
                                base_unit_price = discounted_unit_price
                            _logger.info(
                                "[pos_discount_cap] line %s product=%s fallback rule_id=%s "
                                "cap_eligible=%s price=%s",
                                line_uuid,
                                product_id,
                                rule_id,
                                cap_eligible,
                                discounted_unit_price,
                            )
                    else:
                        _logger.info(
                            "[pos_discount_cap] line %s skipped before rule lookup: "
                            "product_id=%s product_exists=%s qty=%s price_type=%s "
                            "price_unit=%s",
                            line_uuid,
                            product_id,
                            bool(product),
                            qty,
                            price_type,
                            line_price_unit,
                        )

                    skip_reason = self._line_skip_reason(
                        product, qty, price_type, can_apply_cap, cap_eligible, rule_id
                    )
                    if skip_reason:
                        _logger.info(
                            "[pos_discount_cap] line %s NOT eligible: reason=%s "
                            "can_apply_cap=%s cap_eligible=%s rule_id=%s debug=%s",
                            line_uuid,
                            skip_reason,
                            can_apply_cap,
                            cap_eligible,
                            rule_id,
                            line_debug,
                        )

                    line_amount = qty * base_unit_price if cap_eligible and can_apply_cap else 0.0
                    unit_discount = max(0.0, base_unit_price - discounted_unit_price)
                    pricelist_discount_percent = (
                        self._get_rule_discount_percent(
                            self.env["product.pricelist.item"].browse(rule_id)
                        )
                        if cap_eligible and rule_id
                        else 0.0
                    )
                    if not pricelist_discount_percent and base_unit_price > 0 and cap_eligible:
                        pricelist_discount_percent = (unit_discount / base_unit_price) * 100.0
                    line_full_discount_amount = (
                        qty * unit_discount if cap_eligible and can_apply_cap else 0.0
                    )
                    result.append(
                        {
                            "line_uuid": line_uuid,
                            "cap_eligible": cap_eligible,
                            "can_apply_cap": can_apply_cap,
                            "skip_reason": skip_reason,
                            "debug": line_debug,
                            "line_base_amount": line_amount,
                            "line_full_discount_amount": line_full_discount_amount,
                            "pricelist_discount_percent": pricelist_discount_percent,
                            "discounted_unit_price": discounted_unit_price,
                            "base_unit_price": base_unit_price,
                            "rule_id": rule_id,
                            "product_id": product_id,
                            "price_type": price_type,
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

            eligible_count = sum(
                1 for item in result if item.get("cap_eligible") and item.get("can_apply_cap")
            )
            _logger.info(
                "[pos_discount_cap] evaluation summary pricelist_id=%s lines=%s eligible=%s "
                "result=%s",
                pricelist_id,
                len(result),
                eligible_count,
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
        """Backward-compatible alias."""
        return self._get_pos_cap_rule(product, quantity, date=date)


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


class PosOrder(models.Model):
    _inherit = "pos.order"

    promotional_discount_amount = fields.Monetary(
        string="Promotional Discount Amount",
        currency_field="currency_id",
        readonly=True,
        copy=False,
        help="Total promotional discount applied through the POS discount cap.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        # Core pos.order returns [] meaning "load all fields".
        if not fields_to_load:
            return fields_to_load
        if "promotional_discount_amount" not in fields_to_load:
            fields_to_load.append("promotional_discount_amount")
        return fields_to_load


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
