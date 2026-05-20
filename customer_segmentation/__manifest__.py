{
    'name': 'Customer Segmentation',
    'version': '19.0.1.0.0',
    'category': 'Sales',
    'summary': 'Department-based customer segmentation with bulk import functionality',
    'description': '''
        This module provides:
        - Customer categorization by department (Export Sales, Local Sales, Procurement/Vendors, POS)
        - Department-specific access control via record rules
        - Unified Excel bulk import tool for customers and vendors
        - Automatic category assignment based on department selection
    ''',
    'author': 'Your Company',
    'website': 'https://github.com/yourrepo',
    'depends': [
        'base',
        'sale',
        'purchase',
        'point_of_sale',
    ],
    'data': [
        'security/ir_rule.xml',
        'security/ir_model_access.xml',
        'views/res_partner_views.xml',
        'views/customer_import_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
