{
    "name": "Sale Delivery Split by Group",
    "version": "19.0.1.0.1",
    "category": "Inventory/Delivery",
    "author": "Anabtawi",
    "summary": "Split sale order deliveries by a delivery group set on each line "
               "when the customer location is one of the configured locations.",
    "depends": ["sale_stock"],
    "data": [
        "security/ir.model.access.csv",
        "views/sale_delivery_group_views.xml",
        "views/res_config_settings_views.xml",
        "views/sale_order_views.xml",
        "views/stock_picking_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
