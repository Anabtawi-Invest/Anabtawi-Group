# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Ensure each company has its own Create Customer approval category."""
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    env["approval.category"]._ensure_create_customer_categories()
