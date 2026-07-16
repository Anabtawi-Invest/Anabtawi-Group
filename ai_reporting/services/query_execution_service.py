import time

from odoo import _, models
from odoo.exceptions import AccessError, ValidationError


class AiReportingQueryExecutionService(models.AbstractModel):
    _name = "ai.reporting.query_execution_service"
    _description = "AI Reporting Query Execution Service"

    def execute_plan(self, plan, parameters=None, preview=False):
        started = time.monotonic()
        self.env["ai.reporting.report_plan_validator"].validate_plan(plan, mode="query")
        model_name = plan.get("model")
        if not model_name:
            raise ValidationError(_("The plan must define a source model."))
        model = self.env[model_name]
        access_mode = "read"
        if not model.browse().has_access(access_mode):
            raise AccessError(_("You do not have read access to %s.") % model_name)
        domain = self.env["ai.reporting.parameter_resolver"].resolve_domain(plan.get("domain", []), parameters)
        fields_to_read = self._fields_to_read(plan)
        limit = min(int(plan.get("limit") or 80), 80 if preview else int(plan.get("limit") or 500))
        groupby = plan.get("groupby") or []
        measures = plan.get("measures") or []
        if measures:
            result = self._read_group(model, domain, groupby, measures, limit, self._plan_order(plan))
        else:
            result = {
                "rows": model.search_read(domain, fields_to_read, limit=limit, order=self._plan_order(plan)),
                "grouped": False,
            }
        result.update({
            "model": model_name,
            "record_count": len(result.get("rows", [])),
            "execution_time": round(time.monotonic() - started, 4),
        })
        return result

    def _fields_to_read(self, plan):
        fields_to_read = set(plan.get("fields") or [])
        fields_to_read.update(field for field in plan.get("groupby", []) or [] if isinstance(field, str))
        for measure in plan.get("measures", []) or []:
            fields_to_read.add(measure if isinstance(measure, str) else measure.get("field"))
        return [field for field in fields_to_read if field]

    def _plan_order(self, plan):
        order = plan.get("order") or []
        if isinstance(order, str):
            return order
        return ", ".join(item for item in order if isinstance(item, str))

    def _read_group(self, model, domain, groupby, measures, limit, orderby=None):
        fields_spec = []
        for measure in measures:
            if isinstance(measure, str):
                fields_spec.append(measure)
            else:
                field = measure.get("field")
                aggregation = measure.get("aggregation", "sum")
                alias = measure.get("alias") or field
                fields_spec.append("%s:%s(%s)" % (alias, aggregation, field))
        read_limit = None if orderby else limit
        rows = model.read_group(domain, fields_spec, groupby, limit=read_limit, lazy=False)
        if orderby:
            rows = self._sort_grouped_rows(rows, orderby, limit)
        return {"rows": rows, "grouped": True}

    def _sort_grouped_rows(self, rows, orderby, limit):
        parts = (orderby or "").split()
        key = parts[0] if parts else ""
        reverse = len(parts) > 1 and parts[1].lower() == "desc"
        if not key or not rows or key not in rows[0]:
            return rows[:limit]
        return sorted(rows, key=lambda row: row.get(key) or 0, reverse=reverse)[:limit]
