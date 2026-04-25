{
    "name": "Ameen-Anabtawi , Creating Contact Approval",
    "version": "19.0.1.0.0",
    "category": "Approvals",
    "summary": "Create a new Contact from a specific Approval Category when request_status becomes approved, with smart links.",
    "depends": ["approvals", "contacts", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "views/approval_category_views.xml",
        "views/approval_request_views.xml",
        "views/res_partner_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
