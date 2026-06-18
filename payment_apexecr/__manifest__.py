# -*- coding: utf-8 -*-
{
    "name": "ApexECR POS Integration (Mock-First)",
    "version": "1.0.0",
    "category": "Point of Sale",
    "summary": "Integrate Odoo POS with ApexECR SOAP (with mock server support).",
    "depends": ["point_of_sale"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "views/pos_payment_method_views.xml",
        "views/apexecr_log_views.xml",
    ],
    "assets": {
        "point_of_sale.assets_prod": [
            "payment_apexecr/static/src/app/**/*",
        ],
    },
    "installable": True,
    "license": "LGPL-3",
}

