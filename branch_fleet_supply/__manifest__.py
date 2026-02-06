{
    "name": "Branch Supply via Fleet",
    "version": "19.0.1.0.0",
    "category": "Inventory/Inventory",
    "summary": "Branch supply workflow via Fleet with true Preparing status.",
    "author": "Custom",
    "license": "LGPL-3",
    "depends": ["stock", "purchase", "mrp", "mail"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "views/menus.xml",
        "views/branch_supply_order_views.xml",
    ],
    "application": True,
    "installable": True,
}