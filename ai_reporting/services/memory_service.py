import re

from dateutil import parser

from odoo import fields, models

from odoo.addons.ai_reporting.models.ai_reporting_memory import normalize_text, stable_hash


class AiReportingMemoryService(models.AbstractModel):
    _name = "ai.reporting.memory_service"
    _description = "AI Reporting Local Memory Service"

    def resolve_question(self, question, parameters=None):
        normalized = normalize_text(question)
        question_hash = stable_hash(normalized)
        memory = self.env["ai.reporting.memory"].search([
            ("active", "=", True),
            ("state", "=", "approved"),
            ("memory_type", "=", "answer_query"),
            ("question_hash", "=", question_hash),
        ], limit=1)
        if memory:
            return {"resolution_type": "exact_cache", "memory": memory}
        phrase = self.env["ai.reporting.memory.phrase"].search([
            ("active", "=", True),
            ("phrase_hash", "=", question_hash),
            ("memory_id.state", "=", "approved"),
        ], limit=1)
        if phrase:
            return {"resolution_type": "semantic_cache", "memory": phrase.memory_id, "similarity_score": 1.0}
        parameterized = self._resolve_parameterized_intent(normalized, parameters or {})
        if parameterized:
            return parameterized
        return {"resolution_type": "external_provider", "memory": self.env["ai.reporting.memory"]}

    def answer_question(self, question, parameters=None):
        resolved = self.resolve_question(question, parameters or {})
        memory = resolved.get("memory")
        if memory:
            execution_parameters = dict(parameters or {})
            execution_parameters.update(resolved.get("parameters") or {})
            plan = memory.plan_json or {}
            executor = self.env["ai.reporting.query_execution_service"]
            if plan.get("plan_type") == "comparison":
                result = executor.execute_comparison(plan, execution_parameters)
            else:
                result = executor.execute_plan(plan, execution_parameters)
            memory.record_execution(
                question,
                resolution_type=resolved.get("resolution_type"),
                tokens_saved=memory.original_token_usage or 0,
                similarity_score=resolved.get("similarity_score", 0.0),
            )
            return result
        return self.env["ai.reporting.odoo_ai_bridge"].ask_native_provider(question, parameters or {})

    def create_memory_candidate(self, question, plan, provider_name=None, token_usage=0):
        return self.env["ai.reporting.memory"].create({
            "name": question[:120],
            "memory_type": "answer_query",
            "normalized_question": normalize_text(question),
            "plan_json": plan,
            "provider_name": provider_name,
            "original_token_usage": token_usage,
            "state": "validated",
            "confidence_score": 0.7,
        })

    def _resolve_parameterized_intent(self, normalized_question, parameters=None):
        memories = self.env["ai.reporting.memory"].search([
            ("active", "=", True),
            ("state", "=", "approved"),
            ("memory_type", "=", "answer_query"),
        ], limit=200)
        for memory in memories:
            candidate = self._match_memory_pattern(memory, normalized_question, parameters or {})
            if candidate:
                candidate.update({
                    "resolution_type": "parameterized_intent",
                    "memory": memory,
                    "similarity_score": 1.0,
                })
                return candidate
        return False

    def _match_memory_pattern(self, memory, normalized_question, parameters):
        schema = memory.parameter_schema_json or {}
        phrases = [memory.normalized_question or memory.name or ""]
        phrases += memory.phrase_ids.filtered("active").mapped("normalized_phrase")
        for phrase in phrases:
            pattern = self._compile_parameterized_phrase(phrase)
            if not pattern:
                continue
            match = pattern.match(normalized_question)
            if not match:
                continue
            extracted = {key: value.strip() for key, value in match.groupdict().items() if value and value.strip()}
            resolved = self._resolve_parameter_values(memory.plan_json or {}, schema, extracted, parameters)
            if resolved is not False:
                return {"parameters": resolved, "extracted_parameters": extracted}
        return False

    def _compile_parameterized_phrase(self, phrase):
        normalized = normalize_text(phrase)
        if "{" not in normalized or "}" not in normalized:
            return False
        parts = []
        cursor = 0
        for match in re.finditer(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", normalized):
            parts.append(re.escape(normalized[cursor:match.start()]))
            parts.append("(?P<%s>.+?)" % match.group(1))
            cursor = match.end()
        parts.append(re.escape(normalized[cursor:]))
        return re.compile("^%s$" % "".join(parts))

    def _resolve_parameter_values(self, plan, schema, extracted, explicit_parameters):
        resolved = dict(explicit_parameters or {})
        definitions = schema.get("parameters", schema if isinstance(schema, dict) else {})
        for name, raw_value in extracted.items():
            definition = definitions.get(name, {}) if isinstance(definitions, dict) else {}
            resolved[name] = raw_value
            target_name = definition.get("target") or definition.get("target_parameter") or name
            value = self._resolve_single_parameter(plan, name, raw_value, definition)
            if value is False:
                return False
            resolved[target_name] = value
        return resolved

    def _resolve_single_parameter(self, plan, name, raw_value, definition):
        parameter_type = definition.get("type")
        if parameter_type == "date":
            return self._parse_date(raw_value)
        if parameter_type in ("integer", "int"):
            try:
                return int(raw_value)
            except ValueError:
                return False
        if parameter_type in ("float", "number"):
            try:
                return float(raw_value)
            except ValueError:
                return False
        if parameter_type in ("char", "text", "string"):
            return raw_value
        model_name = definition.get("model") or self._infer_parameter_model(plan, definition.get("target") or name)
        if not model_name:
            return raw_value
        if model_name not in self.env:
            return False
        model = self.env[model_name]
        if not model.browse().has_access("read"):
            return False
        search_field = definition.get("search_field") or definition.get("field") or "name"
        if search_field not in model._fields:
            search_field = "display_name"
        operator = definition.get("operator") or "ilike"
        records = model.search([(search_field, operator, raw_value)], limit=2)
        if len(records) != 1:
            return False
        return records.id

    def _parse_date(self, raw_value):
        text = (raw_value or "").strip()
        shortcuts = {
            "today": fields.Date.context_today(self),
            "yesterday": fields.Date.subtract(fields.Date.context_today(self), days=1),
        }
        if text.lower() in shortcuts:
            return shortcuts[text.lower()]
        try:
            return fields.Date.to_date(text)
        except Exception:
            try:
                return parser.parse(text, dayfirst=True, fuzzy=True).date()
            except Exception:
                return False

    def _infer_parameter_model(self, plan, parameter_name):
        placeholder = "$%s" % parameter_name
        for item in plan.get("domain", []) or []:
            if not isinstance(item, (list, tuple)) or len(item) != 3:
                continue
            field_name, _operator, value = item
            if value != placeholder or not plan.get("model") or plan["model"] not in self.env:
                continue
            field = self.env[plan["model"]]._fields.get(field_name)
            if field and getattr(field, "comodel_name", None):
                return field.comodel_name
        return False
