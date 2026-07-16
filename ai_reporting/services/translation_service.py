from odoo import models

from odoo.addons.ai_reporting.models.ai_reporting_memory import normalize_text


class AiReportingTranslationService(models.AbstractModel):
    _name = "ai.reporting.translation_service"
    _description = "AI Reporting Local Translation Service"

    def normalize_arabic(self, text):
        return normalize_text(text)

    def generate_phrase_variants(self, text, language_code="en"):
        normalized = normalize_text(text)
        variants = [text, normalized]
        if language_code == "en":
            variants.append("show %s" % normalized)
        return list(dict.fromkeys(filter(None, variants)))

