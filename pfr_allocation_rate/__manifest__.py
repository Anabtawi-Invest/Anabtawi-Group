{
    'name': 'Payroll Fix Recon - Weighted Allocation',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Allocate Extra Hours x1.25 and Paid Time Off x1.5, with a batched date-range update.',
    'author': 'Anabtawi Group',
    'license': 'OPL-1',
    'depends': [
        'payroll_fix_recon',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/pfr_alloc_rate_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
