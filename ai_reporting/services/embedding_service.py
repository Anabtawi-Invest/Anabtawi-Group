from odoo import models

from odoo.addons.ai_reporting.models.ai_reporting_memory import normalize_text, stable_hash


class AiReportingEmbeddingService(models.AbstractModel):
    _name = "ai.reporting.embedding.service"
    _description = "AI Reporting Local Embedding Service"

    def embed_text(self, text, language_code=None):
        normalized = normalize_text(text)
        digest = stable_hash("%s:%s" % (language_code or "", normalized))
        return [int(digest[index:index + 2], 16) / 255.0 for index in range(0, 64, 2)]

    def embed_batch(self, texts, language_code=None):
        return [self.embed_text(text, language_code=language_code) for text in texts]

    def semantic_search(self, embedding, company_ids, limit=10):
        domain = [("state", "=", "approved"), ("active", "=", True)]
        if company_ids:
            domain.append(("company_id", "in", company_ids))
        return self.env["ai.reporting.memory"].search(domain, limit=limit)

    def health_check(self):
        return {"available": True, "backend": "local_hash_fallback", "paid_api": False}

