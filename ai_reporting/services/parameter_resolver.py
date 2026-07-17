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
        month_start = report_date.replace(day=1)
        week_start = report_date - timedelta(days=report_date.weekday())
        quarter_index = (report_date.month - 1) // 3
        quarter_start = report_date.replace(month=quarter_index * 3 + 1, day=1)
        year_start = report_date.replace(month=1, day=1)
        mapping = {
            "$today": today,
            "$yesterday": report_date - timedelta(days=1),
            "$current_user": self.env.user.id,
            "$active_company_ids": self.env.companies.ids,
            "$period_start": parameters.get("period_start"),
            "$period_end": parameters.get("period_end"),
            "$date": parameters.get("date"),
            "$invoice_date": parameters.get("invoice_date"),
            "$date_from": parameters.get("date_from"),
            "$date_to": parameters.get("date_to"),
            "$branch_id": parameters.get("branch_id"),
            "$company_id": parameters.get("company_id"),
            "$partner_id": parameters.get("partner_id"),
            "$product_id": parameters.get("product_id"),
            # Relative date-range helpers, all computed from "report_date"
            # (defaults to today). Used by Discovery-generated templates such
            # as "sales this month" / "sales last quarter" so those phrases
            # need no free-text parameters and stay correct on every run.
            "$week_start(report_date)": week_start,
            "$week_end(report_date)": week_start + timedelta(days=6),
            "$previous_week_start(report_date)": week_start - timedelta(days=7),
            "$previous_week_end(report_date)": week_start - timedelta(days=1),
            "$month_start(report_date)": month_start,
            "$month_end(report_date)": month_start + relativedelta(months=1) - timedelta(days=1),
            "$previous_month_start(report_date)": month_start - relativedelta(months=1),
            "$previous_month_end(report_date)": month_start - timedelta(days=1),
            "$quarter_start(report_date)": quarter_start,
            "$quarter_end(report_date)": quarter_start + relativedelta(months=3) - timedelta(days=1),
            "$previous_quarter_start(report_date)": quarter_start - relativedelta(months=3),
            "$previous_quarter_end(report_date)": quarter_start - timedelta(days=1),
            "$year_start(report_date)": year_start,
            "$year_end(report_date)": year_start + relativedelta(years=1) - timedelta(days=1),
            "$previous_year_start(report_date)": year_start - relativedelta(years=1),
            "$previous_year_end(report_date)": year_start - timedelta(days=1),
        }
        return mapping.get(value, parameters.get(value[1:], value))

    def resolve_domain(self, domain, parameters=None):
        return self.resolve(domain or [], parameters or {})
