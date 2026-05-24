{
    "name": "POS Apex ECR Payment Integration",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Connect Odoo 19 POS with Apex ECR EFTPOS terminal (SALE, REFUND, VOID, CANCEL, Enquiry)",
    "description": """
Integrates the Apex ECR EFTPOS terminal with Odoo 19 Point of Sale via SOAP/XML.

Supported transactions:
- SALE
- REFUND
- VOID (by invoice number)
- CANCEL last request
- ECR Enquiry (recover a transaction approved at POS but lost at ECR level)

Frontend is built with Odoo 19's OWL framework:
- Intercepts validation when an Apex payment line is present
- Shows a full-screen waiting dialog while the terminal processes the card
- Stores all response fields on the pos.payment record:
  RRN, auth code, card scheme, masked PAN, batch, STAN, receipt text
    """,
    "author": "Custom",
    "depends": ["point_of_sale"],
    "data": [
        "security/ir.model.access.csv",
        "views/pos_payment_method_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_apex_ecr_payment/static/src/css/apex_payment.css",
            "pos_apex_ecr_payment/static/src/js/apex_payment_service.js",
            "pos_apex_ecr_payment/static/src/js/apex_payment_method.js",
            "pos_apex_ecr_payment/static/src/xml/apex_payment.xml",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
