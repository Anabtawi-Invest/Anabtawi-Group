{
    "name": "Anabtawi Deferred Expense Models",
    "version": "19.0.1.1.0",
    "category": "Accounting/Accounting",
    "summary": "Odoo 15-style deferred expense models with per-model prepaid accounts",
    "author": "Anabtawi Group",
    "license": "LGPL-3",
    "depends": [
        "account_accountant",
        "product",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/deferred_expense_model_views.xml",
        "views/product_views.xml",
        "views/account_move_views.xml",
    ],
    "installable": True,
    "application": False,
}
