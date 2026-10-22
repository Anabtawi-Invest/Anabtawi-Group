{
    "name": "Stock Picking Location Access",
    "version": "19.0.1.0.1",
    "category": "Inventory/Inventory",
    "summary": "Restrict edit/validate of internal transfers by From/To location and group",
    "author": "Anabtawi",
    "depends": ["stock"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/stock_picking_location_access_views.xml",
        "views/stock_picking_views.xml",
        "views/menu.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
