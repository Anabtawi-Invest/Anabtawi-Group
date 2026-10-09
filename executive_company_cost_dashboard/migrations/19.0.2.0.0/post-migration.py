# -*- coding: utf-8 -*-
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# Buckets created by version 1 keep their records; give them the v2 names / families.
RENAMES = {
    "REVENUE": ("Other Revenue", "revenue", 18),
    "COGS": ("Cost of Goods & Materials", "expense", 20),
    "RENT": ("Rent & Occupancy", "expense", 40),
    "UTILITIES": ("Utilities (Power, Water, Fuel)", "expense", 50),
    "PAYROLL": ("People & Labor", "expense", 30),
    "TECH": ("IT, Telecom & Software", "expense", 60),
    "DELIVERY": ("Delivery Platform Commissions", "expense", 70),
    "FLEET": ("Fleet & Logistics", "expense", 80),
    "SECURITY": ("Security & Guarding", "expense", 90),
    "MAINTENANCE": ("Maintenance & Cleaning", "expense", 100),
    "LOSS": ("Waste, Shrinkage & Discrepancies", "expense", 110),
    "OTHER_OPEX": ("Other Operating Costs", "expense", 160),
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Bucket = env["ceo.cost.bucket"].with_context(active_test=False)
    for code, (name, family, sequence) in RENAMES.items():
        bucket = Bucket.search([("code", "=", code)], limit=1)
        if bucket:
            bucket.write({"name": name, "category_type": family, "sequence": sequence})
    # v1 mappings were all produced by the old scanner: let the new rules re-classify them
    cr.execute("UPDATE ceo_cost_account_mapping SET auto = TRUE")
    try:
        with cr.savepoint():
            env["ceo.smart.scanner.wizard"]._scan(overwrite=True)
    except Exception:
        _logger.exception("Executive Company Cost Dashboard: migration scan failed")
