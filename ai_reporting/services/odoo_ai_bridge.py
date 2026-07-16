from odoo import _, models


class AiReportingOdooAiBridge(models.AbstractModel):
    _name = "ai.reporting.odoo_ai_bridge"
    _description = "AI Reporting Native Odoo AI Bridge"

    _candidate_models = (
        "ai.agent",
        "ai.topic",
        "ai.tool",
        "ai.provider",
        "ai.request",
        "ai.connection",
        "ai.bridge",
        "ai.bridge.execution",
        "html.editor",
        "website",
    )

    def detect_native_ai(self):
        installed = []
        registry_models = set(getattr(self.env.registry, "models", {}) or {})
        for model_name in self._candidate_models:
            if model_name in registry_models:
                installed.append(model_name)
        module_names = self.env["ir.module.module"].search([
            ("name", "ilike", "ai"),
            ("state", "=", "installed"),
        ]).mapped("name")
        status = {
            "available": bool(installed or module_names),
            "models": installed,
            "modules": module_names,
            "native_available": any(model in installed for model in ("ai.agent", "ai.topic", "ai.provider", "ai.request")),
            "oca_available": any(model in installed for model in ("ai.connection", "ai.bridge", "ai.tool")),
            "provider_configured": False,
            "third_party": self.env["ai.reporting.third_party_ai_provider"].get_status(),
            "notes": _("Native business Ask AI was not found in the inspected Community checkout; runtime registry probing is used."),
        }
        status["provider_configured"] = status["third_party"].get("configured", False)
        self.env["ir.config_parameter"].set_param("ai_reporting.native_ai_status", "available" if status["available"] else "unavailable")
        return status

    def register_integration(self):
        return self.detect_native_ai()

    def route_ask_ai_question(self, question, parameters=None):
        return self.env["ai.reporting.memory_service"].answer_question(question, parameters or {})

    def ask_native_provider(self, question, parameters=None):
        status = self.detect_native_ai()
        if status["third_party"].get("configured"):
            return self.env["ai.reporting.third_party_ai_provider"].answer_question(question, parameters or {})
        return {
            "provider_called": False,
            "answer": _("Configure OpenAI or Claude in AI Reporting settings, then set the matching API key environment variable on the Odoo server."),
            "status": status,
        }

    def create_report_draft(self, question):
        provider_plan = self.env["ai.reporting.third_party_ai_provider"].generate_report_definition(question)
        if provider_plan:
            return provider_plan
        model = self._infer_model(question)
        return {
            "definition": {
                "title": question[:80],
                "description": question,
                "model": model,
                "models": [model],
                "domain": [],
                "fields": ["display_name"],
                "groupby": [],
                "measures": [],
                "calculated_measures": [],
                "report_type": "table",
                "visualization_type": "table",
                "limit": 20,
                "assumptions": [_("Draft created locally because no native business Ask AI provider source was detected.")],
            },
            "parameters": {},
        }

    def adjust_report_draft(self, definition, adjustment):
        provider_plan = self.env["ai.reporting.third_party_ai_provider"].generate_report_definition(
            question=(definition or {}).get("description") or (definition or {}).get("title") or "",
            current_definition=definition,
            adjustment=adjustment,
        )
        if provider_plan:
            return provider_plan
        updated = dict(definition or {})
        adjustments = list(updated.get("adjustments", []))
        adjustments.append(adjustment)
        updated["adjustments"] = adjustments
        updated["description"] = (updated.get("description") or "") + "\n" + adjustment
        return {"definition": updated, "parameters": updated.get("parameters", {})}

    def _infer_model(self, question):
        lowered = (question or "").lower()
        if "purchase" in lowered or "procurement" in lowered or "vendor" in lowered:
            return "purchase.order.line" if "purchase.order.line" in self.env else "purchase.order"
        if "sale" in lowered or "sales" in lowered:
            return "sale.order" if "sale.order" in self.env else "res.partner"
        if "invoice" in lowered or "receivable" in lowered:
            return "account.move" if "account.move" in self.env else "res.partner"
        if "stock" in lowered or "inventory" in lowered:
            return "stock.quant" if "stock.quant" in self.env else "product.product"
        return "res.partner"

    def _get_oca_connection(self):
        if "ai.connection" not in self.env:
            return self.env["ir.model"].browse()
        return self.env["ai.connection"].search([("active", "=", True)], order="id", limit=1)

    def _run_oca_connection(self, prompt, system_prompt=None, tools=None):
        connection = self._get_oca_connection()
        if not connection:
            return {"content": False, "input_tokens": 0, "output_tokens": 0, "iterations": 0}
        result = connection._run(
            prompt=prompt,
            tools=tools or self._get_oca_tools(),
            system_prompt=system_prompt,
        )
        content, input_tokens, output_tokens, iterations = result
        return {
            "content": content,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "iterations": iterations,
        }

    def _get_oca_tools(self):
        if "ai.tool" not in self.env:
            return self.env["ir.model"].browse()
        return self.env["ai.tool"].search([])

    def _parse_report_definition(self, content):
        import json

        if not content:
            return False
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            payload = json.loads(text)
        except Exception:
            return False
        definition = payload.get("definition", payload)
        if not isinstance(definition, dict) or not definition.get("model"):
            return False
        return {
            "definition": definition,
            "parameters": payload.get("parameters", definition.get("parameters", {})),
        }

    def _ask_ai_system_prompt(self):
        return _(
            "You are an Odoo business-data assistant. Return concise answers. "
            "Do not propose SQL, Python, JavaScript, shell commands, or unsafe actions."
        )

    def _advanced_report_system_prompt(self):
        return _(
            "You design safe Odoo advanced report definitions. "
            "Return only strict JSON with keys definition and parameters. "
            "The definition must include model, domain, fields, groupby, measures, "
            "calculated_measures, report_type, visualization_type, and limit. "
            "Do not include SQL, Python, JavaScript, shell commands, URLs, or sudo."
        )

    def _adjustment_prompt(self, definition, adjustment):
        import json

        return _(
            "Update this Odoo report definition according to the adjustment.\n\n"
            "Definition:\n%(definition)s\n\nAdjustment:\n%(adjustment)s"
        ) % {
            "definition": json.dumps(definition or {}, ensure_ascii=False, sort_keys=True),
            "adjustment": adjustment,
        }
