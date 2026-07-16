from odoo import fields, models

from odoo.addons.ai_reporting.models.ai_reporting_memory import _json_dumps, normalize_text, stable_hash


class AiReportingDiscoveryService(models.AbstractModel):
    _name = "ai.reporting.discovery.service"
    _description = "AI Reporting Discovery Service"

    def refresh_metadata(self, scan_addons=True, build_templates=True):
        models_count = self.env["ir.model"].search_count([])
        fields_count = self.env["ir.model.fields"].search_count([])
        addons = self._scan_installed_addons() if scan_addons else {"installed": 0, "with_manifest": 0, "addons": []}
        self.env["ir.config_parameter"].set_param("ai_reporting.last_discovery_at", fields.Datetime.now())
        self.env["ir.config_parameter"].set_param("ai_reporting.discovery_model_count", models_count)
        self.env["ir.config_parameter"].set_param("ai_reporting.discovery_field_count", fields_count)
        self.env["ir.config_parameter"].set_param("ai_reporting.discovery_addon_count", addons["installed"])
        self.env["ir.config_parameter"].set_param("ai_reporting.discovery_manifest_count", addons["with_manifest"])
        self.env["ai.reporting.odoo_ai_bridge"].register_integration()
        templates = self.build_query_templates() if build_templates else {"created": 0, "skipped": 0}
        return {"models": models_count, "fields": fields_count, "addons": addons, "templates": templates}

    def _scan_installed_addons(self):
        try:
            from odoo.modules.module import Manifest
        except Exception:
            Manifest = False
        result = []
        installed = self.env["ir.module.module"].search([("state", "=", "installed")], order="name")
        for addon in installed:
            manifest = Manifest.for_addon(addon.name, display_warning=False) if Manifest else False
            values = {
                "name": addon.name,
                "shortdesc": addon.shortdesc,
                "category": addon.category_id.name if addon.category_id else False,
                "has_manifest": bool(manifest),
                "depends": [],
                "data_files": 0,
                "demo_files": 0,
            }
            if manifest:
                values.update({
                    "shortdesc": manifest.get("name") or values["shortdesc"],
                    "category": manifest.get("category") or values["category"],
                    "depends": manifest.get("depends") or [],
                    "data_files": len(manifest.get("data") or []),
                    "demo_files": len(manifest.get("demo") or []),
                })
            result.append(values)
        return {
            "installed": len(result),
            "with_manifest": len([addon for addon in result if addon["has_manifest"]]),
            "addons": result[:300],
        }

    def build_query_templates(self):
        created = 0
        skipped = 0
        for template in self._business_templates():
            try:
                supported = self._template_supported(template)
            except Exception:
                supported = False
            if not supported:
                skipped += 1
                continue
            try:
                saved = self._upsert_memory_template(template)
            except Exception:
                saved = False
            if saved:
                created += 1
            else:
                skipped += 1
        self.env["ir.config_parameter"].set_param("ai_reporting.discovery_template_count", created)
        return {"created": created, "skipped": skipped}

    def _upsert_memory_template(self, template):
        memory_model = self.env["ai.reporting.memory"]
        normalized_question = normalize_text(template["phrases"][0])
        question_hash = stable_hash(normalized_question)
        plan_fingerprint = stable_hash(_json_dumps(template["plan"]))
        base_domain = [
            ("memory_type", "=", "answer_query"),
            ("company_id", "=", self.env.company.id),
        ]
        existing = (
            memory_model.search(base_domain + [("intent_code", "=", template["intent_code"])], limit=1)
            or memory_model.search(base_domain + [("question_hash", "=", question_hash)], limit=1)
            or memory_model.search(base_domain + [("plan_fingerprint", "=", plan_fingerprint)], limit=1)
        )
        vals = {
            "name": template["name"],
            "memory_type": "answer_query",
            "intent_code": template["intent_code"],
            "source_model_name": template["plan"]["model"],
            "normalized_question": normalized_question,
            "plan_json": template["plan"],
            "parameter_schema_json": template.get("parameter_schema", {}),
            "state": "approved",
            "confidence_score": 1.0,
            "visibility": "company",
        }
        memory = existing
        if existing:
            existing.write(vals)
        else:
            memory = memory_model.create(vals)
        self._sync_phrases(memory, template["phrases"])
        return True

    def _sync_phrases(self, memory, phrases):
        phrase_model = self.env["ai.reporting.memory.phrase"]
        existing = {phrase.normalized_phrase: phrase for phrase in memory.phrase_ids}
        seen = set()
        for phrase in phrases:
            normalized_text = self._normalize(phrase)
            if not normalized_text or normalized_text in seen:
                continue
            seen.add(normalized_text)
            if normalized_text in existing:
                existing[normalized_text].active = True
                continue
            phrase_model.create({
                "memory_id": memory.id,
                "phrase": phrase,
                "variant_type": "canonical" if phrase == phrases[0] else "paraphrase",
                "translation_status": "approved",
            })

    def _template_supported(self, template):
        plan = template["plan"]
        model_name = plan.get("model")
        if not model_name or model_name not in self.env:
            return False
        available_fields = self.env[model_name]._fields
        for field_name in plan.get("fields", []) or []:
            if field_name not in available_fields:
                return False
        for field_name in plan.get("groupby", []) or []:
            if field_name not in available_fields:
                return False
        for measure in plan.get("measures", []) or []:
            field_name = measure if isinstance(measure, str) else measure.get("field")
            if field_name and field_name not in available_fields:
                return False
        for item in plan.get("domain", []) or []:
            if isinstance(item, (list, tuple)) and len(item) == 3 and item[0] not in available_fields:
                return False
        return True

    def _business_templates(self):
        templates = []
        templates += self._accounting_templates()
        templates += self._purchase_templates()
        templates += self._sales_templates()
        templates += self._inventory_templates()
        templates += self._generic_model_templates()
        return templates

    def _accounting_templates(self):
        templates = [
            {
                "name": "Vendor bills on date",
                "intent_code": "account_vendor_bills_on_date",
                "phrases": [
                    "purchase invoices on {invoice_date}",
                    "vendor bills on {invoice_date}",
                    "invoices purchased on {invoice_date}",
                    "what are the purchase invoices on {invoice_date}",
                ],
                "plan": {
                    "model": "account.move",
                    "domain": [["move_type", "=", "in_invoice"], ["invoice_date", "=", "$invoice_date"]],
                    "fields": ["name", "partner_id", "invoice_date", "amount_total", "state"],
                    "limit": 80,
                },
                "parameter_schema": {"parameters": {"invoice_date": {"type": "date", "target": "invoice_date"}}},
            },
            {
                "name": "Vendor bills by date range",
                "intent_code": "account_vendor_bills_date_range",
                "phrases": [
                    "purchase invoices from {date_from} to {date_to}",
                    "vendor bills from {date_from} to {date_to}",
                    "invoices purchased from {date_from} to {date_to}",
                ],
                "plan": {
                    "model": "account.move",
                    "domain": [["move_type", "=", "in_invoice"], ["invoice_date", ">=", "$date_from"], ["invoice_date", "<=", "$date_to"]],
                    "fields": ["name", "partner_id", "invoice_date", "amount_total", "state"],
                    "limit": 100,
                },
                "parameter_schema": {
                    "parameters": {
                        "date_from": {"type": "date", "target": "date_from"},
                        "date_to": {"type": "date", "target": "date_to"},
                    }
                },
            },
        ]
        branch_field = self._first_field("account.move", ["branch_id", "company_id"])
        if branch_field:
            branch_model = self.env["account.move"]._fields[branch_field].comodel_name or "res.company"
            templates.append({
                "name": "Vendor bills by branch and date",
                "intent_code": "account_vendor_bills_branch_date",
                "phrases": [
                    "purchase invoices for {branch} on {invoice_date}",
                    "vendor bills for {branch} on {invoice_date}",
                    "invoices purchased for {branch} on {invoice_date}",
                ],
                "plan": {
                    "model": "account.move",
                    "domain": [
                        ["move_type", "=", "in_invoice"],
                        [branch_field, "=", "$branch_id"],
                        ["invoice_date", "=", "$invoice_date"],
                    ],
                    "fields": ["name", "partner_id", branch_field, "invoice_date", "amount_total", "state"],
                    "limit": 80,
                },
                "parameter_schema": {
                    "parameters": {
                        "branch": {"model": branch_model, "search_field": "name", "target": "branch_id"},
                        "invoice_date": {"type": "date", "target": "invoice_date"},
                    }
                },
            })
            templates.append({
                "name": "Vendor bills by branch and date range",
                "intent_code": "account_vendor_bills_branch_date_range",
                "phrases": [
                    "purchase invoices for {branch} from {date_from} to {date_to}",
                    "vendor bills for {branch} from {date_from} to {date_to}",
                    "invoices purchased for {branch} from {date_from} to {date_to}",
                ],
                "plan": {
                    "model": "account.move",
                    "domain": [
                        ["move_type", "=", "in_invoice"],
                        [branch_field, "=", "$branch_id"],
                        ["invoice_date", ">=", "$date_from"],
                        ["invoice_date", "<=", "$date_to"],
                    ],
                    "fields": ["name", "partner_id", branch_field, "invoice_date", "amount_total", "state"],
                    "limit": 100,
                },
                "parameter_schema": {
                    "parameters": {
                        "branch": {"model": branch_model, "search_field": "name", "target": "branch_id"},
                        "date_from": {"type": "date", "target": "date_from"},
                        "date_to": {"type": "date", "target": "date_to"},
                    }
                },
            })
        return templates

    def _purchase_templates(self):
        templates = [
            {
                "name": "Most purchased items by date range",
                "intent_code": "purchase_top_items_date_range",
                "phrases": [
                    "most purchased item from {date_from} to {date_to}",
                    "what is the most purchased item from {date_from} to {date_to}",
                    "top purchased items from {date_from} to {date_to}",
                ],
                "plan": {
                    "model": "purchase.order.line",
                    "domain": [["date_order", ">=", "$date_from"], ["date_order", "<=", "$date_to"]],
                    "fields": ["product_id"],
                    "groupby": ["product_id"],
                    "measures": [{"field": "product_qty", "aggregation": "sum", "alias": "qty_purchased"}],
                    "order": "qty_purchased desc",
                    "limit": 10,
                },
                "parameter_schema": {
                    "parameters": {
                        "date_from": {"type": "date", "target": "date_from"},
                        "date_to": {"type": "date", "target": "date_to"},
                    }
                },
            },
            {
                "name": "Purchase item min and max cost by date range",
                "intent_code": "purchase_item_min_max_cost_date_range",
                "phrases": [
                    "min and max purchased cost from {date_from} to {date_to}",
                    "minimum and maximum purchase cost from {date_from} to {date_to}",
                    "what is the min cost purchased and max cost purchased from {date_from} to {date_to}",
                ],
                "plan": {
                    "model": "purchase.order.line",
                    "domain": [["date_order", ">=", "$date_from"], ["date_order", "<=", "$date_to"]],
                    "fields": ["product_id"],
                    "groupby": ["product_id"],
                    "measures": [
                        {"field": "product_qty", "aggregation": "sum", "alias": "qty_purchased"},
                        {"field": "price_unit", "aggregation": "min", "alias": "min_purchase_cost"},
                        {"field": "price_unit", "aggregation": "max", "alias": "max_purchase_cost"},
                    ],
                    "order": "qty_purchased desc",
                    "limit": 20,
                },
                "parameter_schema": {
                    "parameters": {
                        "date_from": {"type": "date", "target": "date_from"},
                        "date_to": {"type": "date", "target": "date_to"},
                    }
                },
            },
        ]
        branch_field = self._first_field("purchase.order.line", ["branch_id", "company_id"])
        if branch_field:
            branch_model = self.env["purchase.order.line"]._fields[branch_field].comodel_name or "res.company"
            templates.append({
                "name": "Most purchased items by branch and date range",
                "intent_code": "purchase_top_items_branch_date_range",
                "phrases": [
                    "most purchased item for {branch} from {date_from} to {date_to}",
                    "top purchased items for {branch} from {date_from} to {date_to}",
                    "what is the most purchased item for {branch} from {date_from} to {date_to}",
                ],
                "plan": {
                    "model": "purchase.order.line",
                    "domain": [
                        [branch_field, "=", "$branch_id"],
                        ["date_order", ">=", "$date_from"],
                        ["date_order", "<=", "$date_to"],
                    ],
                    "fields": ["product_id", branch_field],
                    "groupby": ["product_id"],
                    "measures": [{"field": "product_qty", "aggregation": "sum", "alias": "qty_purchased"}],
                    "order": "qty_purchased desc",
                    "limit": 10,
                },
                "parameter_schema": {
                    "parameters": {
                        "branch": {"model": branch_model, "search_field": "name", "target": "branch_id"},
                        "date_from": {"type": "date", "target": "date_from"},
                        "date_to": {"type": "date", "target": "date_to"},
                    }
                },
            })
            templates.append({
                "name": "Purchase item min and max cost by branch and date range",
                "intent_code": "purchase_item_min_max_cost_branch_date_range",
                "phrases": [
                    "min and max purchased cost for {branch} from {date_from} to {date_to}",
                    "minimum and maximum purchase cost for {branch} from {date_from} to {date_to}",
                    "what is the min cost purchased and max cost purchased for {branch} from {date_from} to {date_to}",
                ],
                "plan": {
                    "model": "purchase.order.line",
                    "domain": [
                        [branch_field, "=", "$branch_id"],
                        ["date_order", ">=", "$date_from"],
                        ["date_order", "<=", "$date_to"],
                    ],
                    "fields": ["product_id", branch_field],
                    "groupby": ["product_id"],
                    "measures": [
                        {"field": "product_qty", "aggregation": "sum", "alias": "qty_purchased"},
                        {"field": "price_unit", "aggregation": "min", "alias": "min_purchase_cost"},
                        {"field": "price_unit", "aggregation": "max", "alias": "max_purchase_cost"},
                    ],
                    "order": "qty_purchased desc",
                    "limit": 20,
                },
                "parameter_schema": {
                    "parameters": {
                        "branch": {"model": branch_model, "search_field": "name", "target": "branch_id"},
                        "date_from": {"type": "date", "target": "date_from"},
                        "date_to": {"type": "date", "target": "date_to"},
                    }
                },
            })
        return templates

    def _sales_templates(self):
        branch_field = self._first_field("sale.order", ["branch_id", "warehouse_id", "company_id"])
        templates = [
            {
                "name": "Sales by date range",
                "intent_code": "sales_date_range",
                "phrases": [
                    "sales from {date_from} to {date_to}",
                    "show sales from {date_from} to {date_to}",
                    "what are the sales from {date_from} to {date_to}",
                ],
                "plan": {
                    "model": "sale.order",
                    "domain": [["date_order", ">=", "$date_from"], ["date_order", "<=", "$date_to"]],
                    "fields": ["name", "partner_id", "date_order", "amount_total", "state"],
                    "limit": 100,
                },
                "parameter_schema": {
                    "parameters": {
                        "date_from": {"type": "date", "target": "date_from"},
                        "date_to": {"type": "date", "target": "date_to"},
                    }
                },
            },
        ]
        if branch_field:
            branch_model = self.env["sale.order"]._fields[branch_field].comodel_name or "res.company"
            templates.append({
                "name": "Sales by branch and date range",
                "intent_code": "sales_branch_date_range",
                "phrases": [
                    "sales for {branch} from {date_from} to {date_to}",
                    "sales in {branch} from {date_from} to {date_to}",
                    "show sales for {branch} from {date_from} to {date_to}",
                ],
                "plan": {
                    "model": "sale.order",
                    "domain": [[branch_field, "=", "$branch_id"], ["date_order", ">=", "$date_from"], ["date_order", "<=", "$date_to"]],
                    "fields": ["name", "partner_id", branch_field, "date_order", "amount_total", "state"],
                    "limit": 100,
                },
                "parameter_schema": {
                    "parameters": {
                        "branch": {"model": branch_model, "search_field": "name", "target": "branch_id"},
                        "date_from": {"type": "date", "target": "date_from"},
                        "date_to": {"type": "date", "target": "date_to"},
                    }
                },
            })
        return templates

    def _inventory_templates(self):
        return [
            {
                "name": "Inventory by product",
                "intent_code": "inventory_by_product",
                "phrases": [
                    "inventory for {product}",
                    "stock for {product}",
                    "available quantity for {product}",
                ],
                "plan": {
                    "model": "stock.quant",
                    "domain": [["product_id", "=", "$product_id"]],
                    "fields": ["product_id", "location_id", "quantity", "reserved_quantity"],
                    "limit": 80,
                },
                "parameter_schema": {"parameters": {"product": {"model": "product.product", "search_field": "name", "target": "product_id"}}},
            },
        ]

    def _first_field(self, model_name, field_names):
        if model_name not in self.env:
            return False
        for field_name in field_names:
            if field_name in self.env[model_name]._fields:
                return field_name
        return False

    def _generic_model_templates(self):
        templates = []
        model_records = self.env["ir.model"].search([("model", "not ilike", "ai.reporting.%")], order="model")
        for model_record in model_records:
            model_name = model_record.model
            if not self._is_generic_model_supported(model_name):
                continue
            model_label = self._model_label(model_record)
            addon_context = self._model_addon_context(model_record)
            fields_to_read = self._default_read_fields(model_name)
            if not fields_to_read:
                continue
            date_field = self._first_existing(model_name, [
                "date",
                "date_order",
                "invoice_date",
                "create_date",
                "write_date",
                "scheduled_date",
                "accounting_date",
            ])
            branch_field = self._first_existing(model_name, ["branch_id", "warehouse_id", "company_id"])
            partner_field = self._first_existing(model_name, ["partner_id", "commercial_partner_id", "vendor_id", "customer_id"])
            product_field = self._first_existing(model_name, ["product_id", "product_tmpl_id"])
            state_field = self._first_existing(model_name, ["state", "stage_id", "status"])
            numeric_fields = self._numeric_fields(model_name)
            if date_field:
                templates.append(self._generic_date_template(model_name, model_label, fields_to_read, date_field, addon_context))
            if date_field and branch_field:
                templates.append(self._generic_relation_date_template(
                    model_name,
                    model_label,
                    fields_to_read,
                    date_field,
                    branch_field,
                    "branch",
                    "branch_id",
                    addon_context,
                ))
            if date_field and partner_field:
                templates.append(self._generic_relation_date_template(
                    model_name,
                    model_label,
                    fields_to_read,
                    date_field,
                    partner_field,
                    "partner",
                    "partner_id",
                    addon_context,
                ))
            if date_field and product_field:
                templates.append(self._generic_relation_date_template(
                    model_name,
                    model_label,
                    fields_to_read,
                    date_field,
                    product_field,
                    "product",
                    "product_id",
                    addon_context,
                ))
            if state_field:
                templates.append(self._generic_state_template(model_name, model_label, fields_to_read, state_field, addon_context))
            if date_field and numeric_fields:
                templates.append(self._generic_min_max_template(model_name, model_label, date_field, numeric_fields[0], addon_context))
            if date_field and product_field and numeric_fields:
                templates.append(self._generic_top_by_relation_template(
                    model_name,
                    model_label,
                    date_field,
                    product_field,
                    numeric_fields[0],
                    "product",
                    addon_context,
                ))
            elif date_field and partner_field and numeric_fields:
                templates.append(self._generic_top_by_relation_template(
                    model_name,
                    model_label,
                    date_field,
                    partner_field,
                    numeric_fields[0],
                    "partner",
                    addon_context,
                ))
        return templates

    def _is_generic_model_supported(self, model_name):
        if not model_name or model_name not in self.env:
            return False
        if model_name.startswith(("ir.", "base.", "bus.", "mail.", "web.", "iap.", "auth.", "digest.")):
            return False
        try:
            model = self.env[model_name]
            if getattr(model, "_abstract", False) or getattr(model, "_transient", False):
                return False
            return bool(model.browse().has_access("read"))
        except Exception:
            return False

    def _model_label(self, model_record):
        return self._normalize(model_record.name or model_record.model).replace(".", " ")

    def _model_addon_context(self, model_record):
        data_records = self.env["ir.model.data"].search([
            ("model", "=", "ir.model"),
            ("res_id", "=", model_record.id),
        ], limit=3)
        addon_names = [record.module for record in data_records if record.module]
        if not addon_names:
            addon_names = [model_record.model.split(".", 1)[0]]
        addon_records = self.env["ir.module.module"].search([
            ("name", "in", addon_names),
            ("state", "=", "installed"),
        ], limit=3)
        labels = [self._normalize(addon.shortdesc or addon.name).replace("_", " ") for addon in addon_records]
        return {
            "addons": addon_names,
            "addon_label": labels[0] if labels else addon_names[0].replace("_", " "),
        }

    def _default_read_fields(self, model_name):
        priority = [
            "name",
            "display_name",
            "partner_id",
            "product_id",
            "date",
            "date_order",
            "invoice_date",
            "amount_total",
            "price_unit",
            "quantity",
            "product_qty",
            "state",
            "company_id",
            "branch_id",
        ]
        available = self.env[model_name]._fields
        selected = [field_name for field_name in priority if field_name in available]
        if selected:
            return selected[:8]
        for field_name, field in available.items():
            if field_name == "id" or field_name.startswith("_"):
                continue
            if field.type in ("char", "text", "html", "selection", "date", "datetime", "many2one", "integer", "float", "monetary"):
                selected.append(field_name)
            if len(selected) >= 8:
                break
        return selected

    def _numeric_fields(self, model_name):
        preferred = [
            "amount_total",
            "amount_untaxed",
            "balance",
            "price_unit",
            "price_subtotal",
            "quantity",
            "product_qty",
            "qty_done",
            "reserved_quantity",
        ]
        available = self.env[model_name]._fields
        fields_found = [
            field_name
            for field_name in preferred
            if field_name in available and available[field_name].type in ("integer", "float", "monetary")
        ]
        for field_name, field in available.items():
            if field_name not in fields_found and field.type in ("integer", "float", "monetary"):
                fields_found.append(field_name)
            if len(fields_found) >= 3:
                break
        return fields_found[:3]

    def _first_existing(self, model_name, field_names):
        available = self.env[model_name]._fields
        for field_name in field_names:
            if field_name in available:
                return field_name
        return False

    def _generic_date_template(self, model_name, model_label, fields_to_read, date_field, addon_context=None):
        addon_context = addon_context or {}
        return {
            "name": "%s by date range" % model_label.title(),
            "intent_code": "generic_%s_date_range" % self._code(model_name),
            "phrases": [
                "%s from {date_from} to {date_to}" % model_label,
                "show %s from {date_from} to {date_to}" % model_label,
                "what are the %s from {date_from} to {date_to}" % model_label,
                "%s %s from {date_from} to {date_to}" % (addon_context.get("addon_label", ""), model_label),
            ],
            "plan": {
                "model": model_name,
                "addon_names": addon_context.get("addons", []),
                "domain": [[date_field, ">=", "$date_from"], [date_field, "<=", "$date_to"]],
                "fields": fields_to_read,
                "limit": 100,
            },
            "parameter_schema": self._date_range_schema(),
        }

    def _generic_relation_date_template(self, model_name, model_label, fields_to_read, date_field, relation_field, label, target, addon_context=None):
        addon_context = addon_context or {}
        relation_model = self.env[model_name]._fields[relation_field].comodel_name
        if not relation_model:
            relation_model = "res.company"
        return {
            "name": "%s by %s and date range" % (model_label.title(), label),
            "intent_code": "generic_%s_%s_date_range" % (self._code(model_name), label),
            "phrases": [
                "%s for {%s} from {date_from} to {date_to}" % (model_label, label),
                "show %s for {%s} from {date_from} to {date_to}" % (model_label, label),
                "%s %s for {%s} from {date_from} to {date_to}" % (addon_context.get("addon_label", ""), model_label, label),
            ],
            "plan": {
                "model": model_name,
                "addon_names": addon_context.get("addons", []),
                "domain": [[relation_field, "=", "$%s" % target], [date_field, ">=", "$date_from"], [date_field, "<=", "$date_to"]],
                "fields": self._include_fields(fields_to_read, [relation_field]),
                "limit": 100,
            },
            "parameter_schema": {
                "parameters": {
                    label: {"model": relation_model, "search_field": "name", "target": target},
                    "date_from": {"type": "date", "target": "date_from"},
                    "date_to": {"type": "date", "target": "date_to"},
                }
            },
        }

    def _generic_state_template(self, model_name, model_label, fields_to_read, state_field, addon_context=None):
        addon_context = addon_context or {}
        field = self.env[model_name]._fields[state_field]
        target = "status_id" if field.type == "many2one" else "status"
        parameter = {"type": "char", "target": target}
        if field.type == "many2one" and field.comodel_name:
            parameter = {"model": field.comodel_name, "search_field": "name", "target": target}
        return {
            "name": "%s by status" % model_label.title(),
            "intent_code": "generic_%s_state" % self._code(model_name),
            "phrases": [
                "%s with status {status}" % model_label,
                "show %s with status {status}" % model_label,
                "%s %s with status {status}" % (addon_context.get("addon_label", ""), model_label),
            ],
            "plan": {
                "model": model_name,
                "addon_names": addon_context.get("addons", []),
                "domain": [[state_field, "=", "$%s" % target]],
                "fields": self._include_fields(fields_to_read, [state_field]),
                "limit": 100,
            },
            "parameter_schema": {"parameters": {"status": parameter}},
        }

    def _generic_min_max_template(self, model_name, model_label, date_field, numeric_field, addon_context=None):
        addon_context = addon_context or {}
        return {
            "name": "%s min and max %s" % (model_label.title(), numeric_field.replace("_", " ")),
            "intent_code": "generic_%s_min_max_%s" % (self._code(model_name), numeric_field),
            "phrases": [
                "min and max %s for %s from {date_from} to {date_to}" % (numeric_field.replace("_", " "), model_label),
                "minimum and maximum %s for %s from {date_from} to {date_to}" % (numeric_field.replace("_", " "), model_label),
            ],
            "plan": {
                "model": model_name,
                "addon_names": addon_context.get("addons", []),
                "domain": [[date_field, ">=", "$date_from"], [date_field, "<=", "$date_to"]],
                "fields": [],
                "groupby": [],
                "measures": [
                    {"field": numeric_field, "aggregation": "min", "alias": "minimum_%s" % numeric_field},
                    {"field": numeric_field, "aggregation": "max", "alias": "maximum_%s" % numeric_field},
                    {"field": numeric_field, "aggregation": "sum", "alias": "total_%s" % numeric_field},
                ],
                "limit": 20,
            },
            "parameter_schema": self._date_range_schema(),
        }

    def _generic_top_by_relation_template(self, model_name, model_label, date_field, relation_field, numeric_field, label, addon_context=None):
        addon_context = addon_context or {}
        return {
            "name": "Top %s in %s" % (label, model_label.title()),
            "intent_code": "generic_%s_top_%s_%s" % (self._code(model_name), label, numeric_field),
            "phrases": [
                "top %s for %s from {date_from} to {date_to}" % (label, model_label),
                "most %s in %s from {date_from} to {date_to}" % (label, model_label),
            ],
            "plan": {
                "model": model_name,
                "addon_names": addon_context.get("addons", []),
                "domain": [[date_field, ">=", "$date_from"], [date_field, "<=", "$date_to"]],
                "fields": [relation_field],
                "groupby": [relation_field],
                "measures": [{"field": numeric_field, "aggregation": "sum", "alias": "total_%s" % numeric_field}],
                "order": "total_%s desc" % numeric_field,
                "limit": 20,
            },
            "parameter_schema": self._date_range_schema(),
        }

    def _date_range_schema(self):
        return {
            "parameters": {
                "date_from": {"type": "date", "target": "date_from"},
                "date_to": {"type": "date", "target": "date_to"},
            }
        }

    def _include_fields(self, fields_to_read, extra_fields):
        result = list(fields_to_read)
        for field_name in extra_fields:
            if field_name and field_name not in result:
                result.append(field_name)
        return result[:8]

    def _code(self, value):
        return self._normalize(value).replace(".", "_").replace(" ", "_")

    def _normalize(self, text):
        return normalize_text(text)
