{
    "name": "Negative Stock-Anabtawi",
    "version": "19.0.1.1.0",
    "category": "Inventory",
    "summary": "Block negative stock when source location is flagged, with allowed users",
    "depends": ["stock"],
    "data": [
        "security/ir.model.access.csv",
        "views/stock_location_views.xml",
    ],
    "installable": True,
    "application": False,
}

