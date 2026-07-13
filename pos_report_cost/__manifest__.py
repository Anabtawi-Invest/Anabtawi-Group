{
    'name': 'POS Order Report - Cost',
    'version': '19.0.2.0.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Adds the product Cost (standard_price) to the POS Orders report',
    'depends': ['point_of_sale'],
    'data': [
        'views/pos_order_report_view.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
