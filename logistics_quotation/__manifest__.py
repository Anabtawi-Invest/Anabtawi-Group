# -*- coding: utf-8 -*-
{
    'name': 'Logistics Quotation & Freight Management',
    'version': '17.0.1.0.0',
    'category': 'Operations/Logistics',
    'summary': 'Manage forwarder RFQs, multi-modal shipping, landed costs for imports, and customer shipping charges for sales.',
    'author': 'Anabtawi Group',
    'depends': [
        'base',
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
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
