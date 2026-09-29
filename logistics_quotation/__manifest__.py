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
* Multi-modal shipping support: Air, Land, and Sea freight.
* Environmental controls: Dry, Cooling, and Freezer cargo specifications.
* Container specifications: 20ft, 40ft, Reefer, LCL, Pallets, CBM volume.
* Forwarder RFQs & bid comparison: Log freight costs, handling fees, and transit times per carrier.
* Inbound Import Logistics: Automatically generates Purchase Orders to winning freight forwarders and enables Landed Cost allocation on stock pickings.
* Outbound Customer Logistics: Automatically injects Freight & Handling charges into originating Sales Orders.
* Native Smart Buttons on Sales Orders and Purchase Orders.
""",
    'author': 'Anabtawi Group',
    'website': 'https://www.anabtawisweets.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'sale_management',
        'purchase',
        'stock',
        'stock_landed_costs',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/product_data.xml',
        'views/logistics_request_views.xml',
    ],
    'assets': {},
    'installable': True,
    'application': True,
    'auto_install': False,
}
