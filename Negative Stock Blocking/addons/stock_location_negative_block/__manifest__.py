{
    "name": "Ameen-Negative Stock",
    "version": "19.0.1.0.0",
    "category": "Inventory",
    "summary": "Block negative stock when source location is flagged",
    "depends": ["stock"],
    "data": [
        "security/ir.model.access.csv",
        "views/stock_location_views.xml",
    ],
    "installable": True,
    "application": False,
}

