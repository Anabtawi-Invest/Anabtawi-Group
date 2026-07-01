{
    "name": "POS Provider Pricelist Report",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Provider pricelist fields and Talabat contribution report for POS orders",
    "author": "Anabtawi",
    "depends": ["point_of_sale", "product", "pos_pricelist_id"],
    "data": [
        "security/ir.model.access.csv",
        "views/product_pricelist_views.xml",
        "views/provider_pricelist_report_views.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
