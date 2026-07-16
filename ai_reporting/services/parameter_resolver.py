from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import fields, models


class AiReportingParameterResolver(models.AbstractModel):
    _name = "ai.reporting.parameter_resolver"
    _description = "AI Reporting Parameter Resolver"

    def resolve(self, value, parameters=None):
        parameters = parameters or {}
        if isinstance(value, str):
            return self._resolve_string(value, parameters)
        if isinstance(value, list):
            return [self.resolve(item, parameters) for item in value]
        if isinstance(value, dict):
            return {key: self.resolve(child, parameters) for key, child in value.items()}
        return value

    def _resolve_string(self, value, parameters):
        if not value.startswith("$"):
            return parameters.get(value, value)
        today = fields.Date.context_today(self)
        report_date = fields.Date.to_date(parameters.get("report_date") or today)
        mapping = {
            "$today": today,
            "$current_user": self.env.user.id,
            "$active_company_ids": self.env.companies.ids,
            "$period_start": parameters.get("period_start"),
            "$period_end": parameters.get("period_end"),
            "$month_start(report_date)": report_date.replace(day=1),
            "$month_end(report_date)": report_date.replace(day=1) + relativedelta(months=1) - timedelta(days=1),
            "$previous_month_start(report_date)": report_date.replace(day=1) - relativedelta(months=1),
            "$previous_month_end(report_date)": report_date.replace(day=1) - timedelta(days=1),
        }
        return mapping.get(value, parameters.get(value[1:], value))

    def resolve_domain(self, domain, parameters=None):
        return self.resolve(domain or [], parameters or {})

