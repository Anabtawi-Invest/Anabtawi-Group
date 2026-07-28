import json
import logging

from odoo import _, models

_logger = logging.getLogger(__name__)


class AiReportingOdooAiBridge(models.AbstractModel):
    _name = "ai.reporting.odoo_ai_bridge"
    _description = "AI Reporting Native Odoo AI Bridge"

    # Kept for informational detection only (soft/optional, never depended on):
    # - ai.agent / ai.topic / ai.embedding / ai.composer / ai.prompt.button / ai.agent.source:
    #   the real Odoo Enterprise "ai" app (technical name "ai", installable app "ai_app").
    #   Verified against the actual module source: ai.topic.tool_ids is a Many2many to
    #   ir.actions.server, domain=[('use_in_ai', '=', True)] -- "AI Tools" are just server
    #   actions with a few extra fields (see _register_native_ai_tools below).
    # - ai.tool / ai.connection / ai.bridge: the unrelated OCA https://github.com/OCA/ai
    #   addons, kept only as a secondary, harmless soft-integration (see
    #   services/optional_ai_tool.py and the _ai_tool_* methods on our own models).
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

    # -- Real native "ai" app integration (ir.actions.server "AI Tools") -----
    # Fixed names used to find our own previously-created tool/topic records on
    # every re-run, so upgrades update them in place instead of duplicating them.
    _NATIVE_TOOL_DEFINITIONS = [
        {
            "name": "AI Reporting: List Advanced Reports",
            "target_model": "ai.reporting.saved.report",
            "code": "ai['result'] = model.env['ai.reporting.saved.report']._ai_tool_list_reports()",
            "description": (
                "List the Advanced Reports (custom AI Reporting module) the current user is "
                "allowed to run, with their id, name and description."
            ),
            "schema": {
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "AI Reporting: Run Advanced Report",
            "target_model": "ai.reporting.saved.report",
            "code": (
                "ai['result'] = model.env['ai.reporting.saved.report']"
                "._ai_tool_run_report(report_id)"
            ),
            "description": (
                "Run one saved Advanced Report (custom AI Reporting module) by id and return its "
                "rows and totals. Use ai_reporting_list_reports first to find the report id. "
                "Runs with the current user's own permissions; nothing is bypassed."
            ),
            "schema": {
                "properties": {
                    "report_id": {"type": "integer", "description": "The id of the saved report to run."},
                },
                "required": ["report_id"],
            },
        },
        {
            "name": "AI Reporting: Draft Advanced Report",
            "target_model": "ai.reporting.request",
            "code": (
                "ai['result'] = model.env['ai.reporting.request']"
                "._ai_tool_create_advanced_report(question)"
            ),
            "description": (
                "Draft and preview a new Advanced Report (custom AI Reporting module) from a "
                "natural-language question, e.g. a procurement or sales comparison report. "
                "This only creates a draft preview -- nothing is saved until a human opens it in "
                "Odoo (AI Reporting > Advanced Report Builder) and explicitly confirms it."
            ),
            "schema": {
                "properties": {
                    "question": {"type": "string", "description": "The report requirement in plain language."},
                },
                "required": ["question"],
            },
        },
    ]
    _NATIVE_TOPIC_NAME = "AI Reporting: Advanced Reports"
    _NATIVE_TOPIC_INSTRUCTIONS = (
        "Use these tools when the user wants to design, list, or run a saved Advanced Report from "
        "the AI Reporting module, as opposed to an ordinary one-off business question. "
        "Creating a report draft never saves anything by itself -- always tell the user to open it "
        "in Odoo to review and confirm it before it becomes a saved report."
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
        native_ai_app_installed = self._native_ai_app_ready()
        status = {
            "available": bool(installed or module_names),
            "models": installed,
            "modules": module_names,
            "native_available": native_ai_app_installed,
            "oca_available": any(model in installed for model in ("ai.connection", "ai.bridge", "ai.tool")),
            "provider_configured": False,
            "third_party": self.env["ai.reporting.third_party_ai_provider"].get_status(),
            "native_tools_registered": 0,
            "notes": (
                _("Native Odoo AI app ('ai'/'ai_app') detected -- registering AI Reporting tools into it.")
                if native_ai_app_installed
                else _("Native Odoo AI app was not found on this database; using the direct provider fallback instead.")
            ),
        }
        status["provider_configured"] = status["third_party"].get("configured", False)
        self.env["ir.config_parameter"].set_param(
            "ai_reporting.native_ai_status",
            "connected" if native_ai_app_installed else ("available" if status["available"] else "unavailable"),
        )
        return status

    def register_integration(self):
        status = self.detect_native_ai()
        if status["native_available"]:
            try:
                status["native_tools_registered"] = self._register_native_ai_tools()
            except Exception:
                # Never let a shape mismatch on someone else's app block our own
                # install/upgrade/cron -- log it and keep the direct-provider fallback usable.
                _logger.exception("AI Reporting: could not register native AI tools; continuing without them.")
                status["native_tools_registered"] = 0
                status["native_available"] = False
        return status

    def _native_ai_app_ready(self):
        """True only once every field this bridge writes to has been verified to exist,
        so we never guess at someone else's schema (see the real fields confirmed
        against the installed 'ai' app: ir.actions.server.use_in_ai/ai_tool_description/
        ai_tool_schema, and ai.topic.tool_ids)."""
        if "ir.actions.server" not in self.env or "ai.topic" not in self.env or "ai.agent" not in self.env:
            return False
        action_fields = self.env["ir.actions.server"]._fields
        required_action_fields = {"use_in_ai", "ai_tool_description", "ai_tool_schema"}
        if not required_action_fields.issubset(action_fields):
            return False
        topic_fields = self.env["ai.topic"]._fields
        return {"tool_ids", "instructions", "name"}.issubset(topic_fields)

    def _register_native_ai_tools(self):
        if not self._native_ai_app_ready():
            return 0
        action_model = self.env["ir.actions.server"]
        tool_actions = action_model
        for definition in self._NATIVE_TOOL_DEFINITIONS:
            if definition["target_model"] not in self.env:
                continue
            model_record = self.env["ir.model"]._get_id(definition["target_model"])
            vals = {
                "name": definition["name"],
                "model_id": model_record,
                "state": "code",
                "code": definition["code"],
                "use_in_ai": True,
                "ai_tool_description": definition["description"],
                "ai_tool_schema": json.dumps(definition["schema"]),
            }
            existing = action_model.search([
                ("name", "=", definition["name"]),
                ("model_id", "=", model_record),
            ], limit=1)
            if existing:
                existing.write(vals)
                tool_actions |= existing
            else:
                tool_actions |= action_model.create(vals)
        if not tool_actions:
            return 0
        topic_model = self.env["ai.topic"]
        topic = topic_model.search([("name", "=", self._NATIVE_TOPIC_NAME)], limit=1)
        topic_vals = {
            "name": self._NATIVE_TOPIC_NAME,
            "instructions": self._NATIVE_TOPIC_INSTRUCTIONS,
            "tool_ids": [(6, 0, tool_actions.ids)],
        }
        if topic:
            topic.write(topic_vals)
        else:
            topic = topic_model.create(topic_vals)
        default_agent = self.env.ref("ai.ai_default_agent", raise_if_not_found=False)
        if default_agent is not None and hasattr(default_agent, "topic_ids") and topic.id not in default_agent.topic_ids.ids:
            default_agent.write({"topic_ids": [(4, topic.id)]})
        return len(tool_actions)

    def route_ask_ai_question(self, question, parameters=None):
        return self.env["ai.reporting.memory_service"].answer_question(question, parameters or {})

    def format_local_memory_chat_reply(self, question, result):
        """Turn a query_execution_service result (rows/record_count/...) into
        a short markdown chat message, used by the ai_reporting_ai_bridge
        glue addon to answer native Ask AI questions straight from Local
        Memory instead of calling the LLM. Kept here (not in the glue addon)
        so it can be unit tested without the real Enterprise "ai" app
        installed."""
        rows = result.get("rows") or []
        record_count = result.get("record_count", len(rows))
        lines = [
            _("Answered from AI Reporting Local Memory (no AI call needed) -- %(count)s result(s) for \"%(question)s\".")
            % {"count": record_count, "question": question}
        ]
        if rows:
            columns = [key for key in rows[0].keys() if key != "id"][:6] or list(rows[0].keys())[:6]
            lines.append("")
            lines.append("| " + " | ".join(columns) + " |")
            lines.append("| " + " | ".join(["---"] * len(columns)) + " |")
            for row in rows[:20]:
                cells = []
                for column in columns:
                    value = row.get(column)
                    if isinstance(value, (list, tuple)) and len(value) == 2:
                        value = value[1]
                    cells.append("" if value in (False, None) else str(value))
                lines.append("| " + " | ".join(cells) + " |")
            if len(rows) > 20:
                lines.append("")
                lines.append(_("... and %s more row(s). Open AI Reporting > Local Memory or Advanced Reports for the full result.") % (len(rows) - 20))
        return "\n".join(lines)

    def format_local_memory_comparison_reply(self, question, result):
        """Format a query_execution_service.execute_comparison() result
        (label_a/label_b/totals with delta + delta_percent per measure) as a
        short markdown chat message for a period-over-period question such as
        "compare sales this month vs last month"."""
        label_a = result.get("label_a") or _("Period A")
        label_b = result.get("label_b") or _("Period B")
        lines = [
            _("Answered from AI Reporting Local Memory (no AI call needed) -- comparing %(label_a)s vs %(label_b)s for \"%(question)s\".")
            % {"label_a": label_a, "label_b": label_b, "question": question}
        ]
        totals = result.get("totals") or []
        if totals:
            lines.append("")
            lines.append("| %s | %s | %s | %s |" % (_("Measure"), label_a, label_b, _("Change")))
            lines.append("| --- | --- | --- | --- |")
            for entry in totals:
                arrow = "+" if entry.get("delta", 0) >= 0 else ""
                lines.append(
                    "| %s | %s | %s | %s%s (%s%s%%) |"
                    % (
                        entry.get("alias") or entry.get("field") or "",
                        self._format_number(entry.get("total_a")),
                        self._format_number(entry.get("total_b")),
                        arrow,
                        self._format_number(entry.get("delta")),
                        arrow,
                        entry.get("delta_percent", 0.0),
                    )
                )
        else:
            lines.append(_("%(count_a)s record(s) in %(label_a)s vs %(count_b)s record(s) in %(label_b)s.") % {
                "count_a": result.get("result_a", {}).get("record_count", 0),
                "label_a": label_a,
                "count_b": result.get("result_b", {}).get("record_count", 0),
                "label_b": label_b,
            })
        return "\n".join(lines)

    def _format_number(self, value):
        if value is None:
            return "0"
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        if number == int(number):
            return "{:,}".format(int(number))
        return "{:,.2f}".format(number)

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
