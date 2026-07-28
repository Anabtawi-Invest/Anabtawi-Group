from odoo import _, models
from odoo.exceptions import ValidationError


class AiReportingReportPlanValidator(models.AbstractModel):
    _name = "ai.reporting.report_plan_validator"
    _description = "AI Reporting Report Plan Validator"

    _blocked_tokens = ("select ", "insert ", "update ", "delete ", "drop ", "alter ", "sudo", "eval(", "exec(", "http://", "https://")
    _operators = {"=", "!=", ">", ">=", "<", "<=", "in", "not in", "ilike", "not ilike", "like", "not like", "child_of", "parent_of"}
    _calculations = {"add", "subtract", "multiply", "divide", "ratio", "percentage_change", "absolute_difference"}

    def validate_plan(self, plan, mode="report"):
        if not isinstance(plan, dict):
            raise ValidationError(_("The AI plan must be a JSON object."))
        self._reject_unsafe_payload(plan)
        model_name = plan.get("model")
        if model_name:
            self._validate_model(model_name)
        for model_name in plan.get("models", []) or []:
            self._validate_model(model_name)
        self._validate_domain(plan.get("domain", []), model_name=plan.get("model"))
        for field_name in plan.get("groupby", []) or []:
            self._validate_field(plan.get("model"), field_name)
        for measure in plan.get("measures", []) or []:
            if isinstance(measure, str):
                self._validate_field(plan.get("model"), measure)
            else:
                self._validate_field(plan.get("model"), measure.get("field"))
        for calculation in plan.get("calculated_measures", []) or []:
            operation = calculation.get("operation")
            if operation not in self._calculations:
                raise ValidationError(_("Unsupported calculation operation: %s") % operation)
        limit = int(plan.get("limit") or 500)
        max_sync = int(self.env["ir.config_parameter"].sudo().get_param("ai_reporting.maximum_synchronous_records", 5000))
        if limit < 1 or limit > max_sync:
            raise ValidationError(_("The report row limit must be between 1 and %s.") % max_sync)
        return {"valid": True, "mode": mode, "model": plan.get("model"), "limit": limit}

    def _reject_unsafe_payload(self, value):
        if isinstance(value, dict):
            for key, child in value.items():
                self._reject_unsafe_text(str(key))
                self._reject_unsafe_payload(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                self._reject_unsafe_payload(child)
        elif isinstance(value, str):
            self._reject_unsafe_text(value)

    def _reject_unsafe_text(self, text):
        lowered = (text or "").lower()
        if any(token in lowered for token in self._blocked_tokens):
            raise ValidationError(_("Unsafe plan content was rejected."))

    def _validate_model(self, model_name):
        if not model_name:
            raise ValidationError(_("Unsupported or unavailable model: %s") % (model_name or ""))
        if model_name not in self.env:
            raise ValidationError(_("Model is not loaded in this registry: %s") % model_name)
        # Metadata lookup only -- actual record access is enforced later by
        # query_execution_service using the caller's own ACLs.
        if not self.env["ir.model"].sudo().search_count([("model", "=", model_name)]):
            raise ValidationError(_("Unsupported or unavailable model: %s") % model_name)

    def _validate_field(self, model_name, field_name):
        if not model_name or not field_name:
            return
        if "." in field_name:
            head, tail = field_name.split(".", 1)
            field = self.env[model_name]._fields.get(head)
            if not field or not getattr(field, "comodel_name", None):
                raise ValidationError(_("Unsupported related field: %s") % field_name)
            return self._validate_field(field.comodel_name, tail)
        if field_name not in self.env[model_name]._fields:
            raise ValidationError(_("Unsupported field %(field)s on %(model)s.") % {"field": field_name, "model": model_name})

    def _validate_domain(self, domain, model_name=None):
        if domain in (None, False):
            return
        if not isinstance(domain, list):
            raise ValidationError(_("The domain must be a JSON list."))
        for item in domain:
            if item in ("&", "|", "!"):
                continue
            if not isinstance(item, (list, tuple)) or len(item) != 3:
                raise ValidationError(_("Unsupported domain element: %s") % item)
            field_name, operator, _value = item
            if operator not in self._operators:
                raise ValidationError(_("Unsupported domain operator: %s") % operator)
            self._validate_field(model_name, field_name)

