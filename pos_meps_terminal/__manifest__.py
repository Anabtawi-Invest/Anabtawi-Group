# -*- coding: utf-8 -*-
{
    "name": "MEPS / ApexECR Payment Terminal for Point of Sale",
    "version": "19.0.1.0.0",
    "summary": "Accept MEPS card payments in POS with real terminal integration (Sale/Void/Settlement)",
    "description": """
MEPS / ApexECR Payment Terminal for Point of Sale
==================================================
Connect Odoo POS directly to MEPS (ApexECR) EFTPOS terminals over the official
SOAP web service - no manual card entry, no re-keying amounts.

Key features
------------
* Native POS payment terminal integration: Payment Method > Integration: Terminal >
  Integrate with: MEPS - the same mechanism used by Adyen, Six, Stripe, etc.
* Automatic Sale on the physical terminal when a MEPS payment method is selected
* Void and end-of-day Settlement from the backend
* Per-branch Terminal ID / Merchant ID / Secure Key, configurable per Payment Method
* One-click Excel import of the acquirer's terminal list (Tid/Mid/SecureKey)
* Gateway URL and timeout configurable in Settings - works with test or production endpoints
* No customer-specific data shipped in the module - configure once, use anywhere
""",
    "category": "Point of Sale",
    "author": "Custom",
    "website": "",
    "license": "OPL-1",
    "price": 0.0,
    "currency": "USD",
    "images": ["static/description/banner.png"],
    "depends": ["point_of_sale"],
    "external_dependencies": {"python": ["lxml", "requests", "openpyxl"]},
    "data": [
        "security/ir.model.access.csv",
        "views/pos_payment_method_views.xml",
        "views/res_config_settings_views.xml",
        "wizard/meps_terminal_import_wizard_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_meps_terminal/static/src/**/*",
        ],
    },
    "installable": True,
    "application": False,
}
