# -*- coding: utf-8 -*-
{
    "name": "Sale Discount Exception Approval",
    "summary": "Quantity-based discount ceilings + dual approvals when discount > 5% (keeps standard line discount).",
    "version": "19.0.2.0.0",
    "category": "Sales/Sales",
    "license": "LGPL-3",
    "author": "Softobia",
    "depends": ["sale", "mail"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/sale_order_views.xml",
    ],
    "installable": True,
    "application": False,
}
