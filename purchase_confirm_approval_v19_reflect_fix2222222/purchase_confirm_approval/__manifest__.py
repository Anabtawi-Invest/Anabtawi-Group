{
    'name': 'Purchase Confirm Dynamic Approval',
    'version': '19.0.1.0.1',
    "by": "Anabtawi Group",
    'category': 'Purchase',
    'summary': 'Dynamic approval stages for Purchase Order confirmation',
    'depends': ['purchase', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/purchase_confirm_approval_views.xml',
        'views/purchase_order_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
