# -*- coding: utf-8 -*-
{
    "name": "Talabat Reviews",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Sync Talabat partner reviews and order lines into Odoo for the POS dashboard",
    "author": "Anabtawi",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "base_setup",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/talabat_store_views.xml",
        "views/talabat_review_views.xml",
        "views/res_config_settings_views.xml",
        "wizard/talabat_import_wizard_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
