# -*- coding: utf-8 -*-

from odoo import _
from odoo.exceptions import AccessError, UserError

from .exceptions import AiAssistantError

# Models exposed to list_models(); only installed models with read access are returned.
DEFAULT_MODEL_ALLOWLIST = (
    "res.partner",
    "product.product",
    "product.template",
    "sale.order",
    "sale.order.line",
    "account.move",
    "account.move.line",
    "stock.quant",
    "stock.picking",
    "purchase.order",
    "hr.employee",
    "crm.lead",
)

# Field types omitted from get_model_fields() payloads (too large or not useful for NL queries).
_SKIPPED_FIELD_TYPES = frozenset({"binary", "html", "image"})


class OdooAITools:
    """Generic ORM tools callable by AI service implementations."""

    def __init__(self, env):
        self.env = env

    def _get_model(self, model):
        if model not in self.env:
            raise AiAssistantError(
                _("Model '%(model)s' is not available.", model=model),
                "model_not_found",
            )
        return self.env[model]

    def list_models(self, limit=50):
        """Return models the current user may read (from a safe allowlist)."""
        limit = min(int(limit or 50), 100)
        result = []
        for model_name in DEFAULT_MODEL_ALLOWLIST:
            if model_name not in self.env:
                continue
            try:
                self.env[model_name].check_access("read")
            except AccessError:
                continue
            label = model_name
            ir_model = self.env["ir.model"].sudo().search([("model", "=", model_name)], limit=1)
            if ir_model:
                label = ir_model.name or model_name
            result.append({"model": model_name, "label": label})
            if len(result) >= limit:
                break
        return result

    def get_model_fields(self, model):
        """Return field metadata for a model (fields_get, sanitized)."""
        recordset = self._get_model(model)
        try:
            recordset.check_access("read")
        except AccessError as exc:
            raise AiAssistantError(str(exc), "access_error") from exc

        try:
            raw = recordset.fields_get()
        except UserError as exc:
            raise AiAssistantError(str(exc), "orm_error") from exc

        fields_info = {}
        for name, info in raw.items():
            if name in ("__last_update",):
                continue
            field_type = info.get("type")
            if field_type in _SKIPPED_FIELD_TYPES:
                continue
            fields_info[name] = {
                "string": info.get("string"),
                "type": field_type,
                "relation": info.get("relation"),
                "required": bool(info.get("required")),
                "readonly": bool(info.get("readonly")),
                "store": bool(info.get("store", True)),
            }
        return {"model": model, "fields": fields_info}

    def search_records(self, model, domain=None, fields=None, limit=20):
        """Search records using search_read()."""
        recordset = self._get_model(model)
        try:
            recordset.check_access("read")
        except AccessError as exc:
            raise AiAssistantError(str(exc), "access_error") from exc

        domain = domain or []
        limit = min(int(limit or 20), 100)
        field_list = fields or ["display_name"]
        try:
            return recordset.search_read(domain, field_list, limit=limit)
        except UserError as exc:
            raise AiAssistantError(str(exc), "orm_error") from exc

    def read_records(self, model, ids, fields=None):
        """Read records by id using read()."""
        recordset = self._get_model(model)
        try:
            recordset.check_access("read")
        except AccessError as exc:
            raise AiAssistantError(str(exc), "access_error") from exc

        if not ids:
            raise AiAssistantError(_("ids are required for read_records."), "invalid_tool_args")

        record_ids = [int(i) for i in ids]
        field_list = fields or ["display_name"]
        try:
            return recordset.browse(record_ids).read(field_list)
        except UserError as exc:
            raise AiAssistantError(str(exc), "orm_error") from exc

    def search_count(self, model, domain=None):
        """Count records using search_count()."""
        recordset = self._get_model(model)
        try:
            recordset.check_access("read")
        except AccessError as exc:
            raise AiAssistantError(str(exc), "access_error") from exc

        domain = domain or []
        try:
            return recordset.search_count(domain)
        except UserError as exc:
            raise AiAssistantError(str(exc), "orm_error") from exc

    def aggregate_records(self, model, domain=None, fields=None, groupby=None, limit=10):
        """Aggregate records using read_group()."""
        recordset = self._get_model(model)
        try:
            recordset.check_access("read")
        except AccessError as exc:
            raise AiAssistantError(str(exc), "access_error") from exc

        domain = domain or []
        groupby = groupby or []
        if not groupby:
            raise AiAssistantError(_("groupby is required for aggregation."), "invalid_tool_args")

        limit = min(int(limit or 10), 50)
        field_list = fields or []
        try:
            return recordset.read_group(domain, field_list, groupby, limit=limit)
        except UserError as exc:
            raise AiAssistantError(str(exc), "orm_error") from exc
