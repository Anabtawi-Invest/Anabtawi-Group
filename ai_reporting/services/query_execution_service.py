import time
from datetime import date, datetime

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
        self._check_date_range(domain)
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

    def execute_comparison(self, plan, parameters=None):
        """Run a two-period comparison plan: same model/measures, two
        separate domains (domain_a/domain_b), executed and validated exactly
        like any other plan (each side goes through the normal execute_plan
        safety checks), then summed per measure so callers get a clean
        current-vs-previous total plus the delta."""
        parameters = parameters or {}
        shared_keys = {"model", "fields", "groupby", "measures", "order", "limit"}
        base_plan = {key: value for key, value in plan.items() if key in shared_keys}
        plan_a = dict(base_plan, domain=plan.get("domain_a") or [])
        plan_b = dict(base_plan, domain=plan.get("domain_b") or [])
        result_a = self.execute_plan(plan_a, parameters, preview=False)
        result_b = self.execute_plan(plan_b, parameters, preview=False)
        return {
            "comparison": True,
            "label_a": plan.get("label_a") or _("Period A"),
            "label_b": plan.get("label_b") or _("Period B"),
            "result_a": result_a,
            "result_b": result_b,
            "totals": self._compare_totals(result_a, result_b, plan.get("measures") or []),
            "model": plan.get("model"),
            "record_count": result_a.get("record_count", 0) + result_b.get("record_count", 0),
        }

    def _compare_totals(self, result_a, result_b, measures):
        totals = []
        for measure in measures:
            if isinstance(measure, str):
                field, alias = measure, measure
            else:
                field = measure.get("field")
                alias = measure.get("alias") or field
            total_a = self._sum_alias(result_a.get("rows", []), alias)
            total_b = self._sum_alias(result_b.get("rows", []), alias)
            delta = total_a - total_b
            delta_percent = round((delta / total_b) * 100.0, 2) if total_b else (100.0 if total_a else 0.0)
            totals.append({
                "field": field,
                "alias": alias,
                "total_a": total_a,
                "total_b": total_b,
                "delta": delta,
                "delta_percent": delta_percent,
            })
        return totals

    def _sum_alias(self, rows, alias):
        return sum((row.get(alias) or 0) for row in rows) if rows else 0

    def _check_date_range(self, domain):
        """Enforce the configured maximum date-range span once placeholders
        such as $date_from/$date_to are resolved to concrete values. Only
        acts on same-field >=/<= pairs it can parse; it never blocks a domain
        it cannot confidently interpret, since the row/limit cap already
        bounds worst-case execution cost."""
        bounds = {}
        for item in domain or []:
            if not isinstance(item, (list, tuple)) or len(item) != 3:
                continue
            field_name, operator, value = item
            parsed = self._parse_date_value(value)
            if parsed is None:
                continue
            if operator in (">=", ">"):
                bounds.setdefault(field_name, {})["start"] = parsed
            elif operator in ("<=", "<"):
                bounds.setdefault(field_name, {})["end"] = parsed
        if not bounds:
            return
        max_days = int(self.env["ir.config_parameter"].sudo().get_param("ai_reporting.maximum_date_range", 366) or 366)
        for field_name, span in bounds.items():
            start = span.get("start")
            end = span.get("end")
            if start is None or end is None:
                continue
            span_days = (end - start).days
            if span_days > max_days:
                raise ValidationError(_(
                    "The date range on %(field)s spans %(days)s days, which is more than the "
                    "configured maximum of %(max_days)s days. Narrow the date range and try again."
                ) % {"field": field_name, "days": span_days, "max_days": max_days})

    def _parse_date_value(self, value):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                return None
        return None

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
