{
    "name": "Sale Line Approval",
    "version": "19.0.1.0.0",
    "category": "Sales",
    "author":"Anabtawi",
    "summary": "Per-line sale approvals for discounts and price overrides.",
    "depends": ["sale", "sale_stock", "approvals", "mail"],
    "data": [
        "views/approval_category_views.xml",
        "views/approval_request_views.xml",
        "views/sale_order_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
