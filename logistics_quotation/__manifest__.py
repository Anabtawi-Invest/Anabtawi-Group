# -*- coding: utf-8 -*-
{
    'name': 'Logistics Quotation & Freight Management',
    'version': '19.0.1.0.0',
    'category': 'Operations/Logistics',
    'summary': 'Manage forwarder RFQs, multi-modal shipping, landed costs for imports, and customer shipping charges for sales.',
    'description': """
Logistics Quotation & Freight Management for Odoo 19
===================================================
Integrated freight forwarder bidding and quotation management system.

Features:
---------
* Forwarder Security & Accounting Approval Workflow on Vendors (res.partner).
* Zero-Selection Automated RFQ Broadcast to Accounting-Approved Forwarders.
* Secure Tokenized Public Web Portal for Forwarders to submit quotes & PDF documents online.
* Real-Time Bidding Dashboard & Response Tracker (Responded vs Pending).
* Commercial Confidentiality: Item descriptions & packaging specs extracted without selling/purchase prices.
* Automatic Forwarder Purchase Order Generation & Sales Order / Landed Cost updates.
""",
    'author': 'Anabtawi Group',
    'website': 'https://www.anabtawisweets.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'product',
        'sale_management',
        'purchase',
        'stock',
        'stock_landed_costs',
        'website',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/product_data.xml',
        'report/logistics_request_report.xml',
        'data/mail_template_data.xml',
        'views/portal_templates.xml',
        'views/res_partner_views.xml',
        'views/crm_team_views.xml',
        'views/logistics_request_views.xml',
    ],
    'assets': {},
    'installable': True,
    'application': True,
    'auto_install': False,
}
