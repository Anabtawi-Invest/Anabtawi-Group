from odoo import api, SUPERUSER_ID

def pre_init_hook(env):
    """
    Pre-Init Hook (Runs before XML data loading):
    Sets noupdate=True on ALL ir.model.data records belonging to factory_attendance_payroll.
    This permanently prevents Odoo module upgrader from attempting to delete ANY legacy record
    (hr.employee, hr.attendance, hr.work.entry, etc.) on existing staging/test databases!
    """
    try:
        model_data = env['ir.model.data'].sudo().search([
            ('module', '=', 'factory_attendance_payroll')
        ])
        if model_data:
            model_data.write({'noupdate': True})
    except Exception:
        pass

def post_init_hook(env):
    """
    Post-Init Hook:
    Binds attendance reconciliation rules (ATT_RECON_VAR, OT_NET, DED_UNDERTIME)
    dynamically to ALL Payroll Structures in the database, allowing HR to choose any structure ID!
    """
    try:
        structures = env['hr.payroll.structure'].sudo().search([])
        rules = env['hr.salary.rule'].sudo().search([('code', 'in', ['ATT_RECON_VAR', 'OT_NET', 'DED_UNDERTIME'])])
        
        for structure in structures:
            for rule in rules:
                existing = env['hr.salary.rule'].sudo().search([
                    ('code', '=', rule.code),
                    ('struct_id', '=', structure.id)
                ], limit=1)
                if not existing:
                    rule.sudo().copy({'struct_id': structure.id})
    except Exception:
        pass
