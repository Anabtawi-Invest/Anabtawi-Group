{
    "name": "Partner Vendor/Customer Flags (Strict)",
    "version": "19.0.1.0.0",
    "author":"Ameen Arabiyat",
    "category": "Accounting",
    "summary": "Adds Is Vendor / Is Customer flags and enforces them on bills/invoices",
    "depends": ["contacts", "account"],
    "data": [
        "views/res_partner_views.xml",
        "views/account_move_views.xml",
    ],
    "installable": True,
    "application": False,
}
