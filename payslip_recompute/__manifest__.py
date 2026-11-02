{
    'name': 'Payslip Recompute',
    'version': '19.0.1.0.9',
    'category': 'Human Resources/Payroll',
    'summary': 'Recompute a period of payslips in the background, with a log of errors and slips left untouched.',
    'author': 'Anabtawi Group',
    'license': 'OPL-1',
    'depends': [
        'hr_payroll',
        'payroll_fix_recon',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/payslip_recompute_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
