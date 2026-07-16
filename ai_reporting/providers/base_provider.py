from odoo import models


class AiReportingProvider(models.AbstractModel):
    _name = "ai.reporting.provider"
    _description = "AI Reporting Provider"

    def get_supported_models(self):
        names = ["sale.order", "purchase.order", "purchase.order.line", "stock.quant", "account.move", "res.partner"]
        return [name for name in names if name in self.env]

    def get_data_sources(self):
        return [{"model": name, "name": self.env[name]._description} for name in self.get_supported_models()]

    def get_measures(self):
        return {
            "sale.order": ["amount_total", "amount_untaxed"],
            "purchase.order.line": ["product_qty", "qty_received", "price_unit"],
            "stock.quant": ["quantity", "reserved_quantity"],
            "account.move": ["amount_total", "amount_residual"],
        }

    def get_dimensions(self):
        return {
            "sale.order": ["partner_id", "user_id", "company_id"],
            "purchase.order.line": ["product_id", "partner_id", "company_id"],
            "account.move": ["partner_id", "journal_id", "company_id"],
        }

    def get_default_filters(self):
        return {"active_company_ids": "$active_company_ids"}

    def get_standard_queries(self):
        return []

    def get_report_templates(self):
        return []

    def get_bilingual_terms(self):
        return {"sales": "المبيعات", "purchase": "المشتريات", "inventory": "المخزون"}

    def validate_report_plan(self, report_plan):
        return self.env["ai.reporting.report_plan_validator"].validate_plan(report_plan, mode="report")

    def execute_report_plan(self, report_plan):
        return self.env["ai.reporting.report_execution_service"].preview_report(report_plan)

