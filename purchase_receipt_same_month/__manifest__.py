{
    "name": "Purchase Receipt Same Month",
    "version": "19.0.1.0.2",
    "summary": "Block receipt validation when the purchase order month differs from the receipt date",
    "category": "Purchases",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": ["purchase_stock"],
    "data": [
        "security/security.xml",
        "views/res_config_settings_views.xml",
        "views/purchase_order_views.xml",
    ],
    "installable": True,
    "application": False,
}
