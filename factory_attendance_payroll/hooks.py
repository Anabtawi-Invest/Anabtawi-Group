from odoo import api, SUPERUSER_ID

def pre_init_hook(env):
    """
    Pre-Init Hook (Runs before XML data loading):
    Decouples all legacy employee XML ID tracking entries in ir.model.data by setting noupdate=True.
    This permanently prevents Odoo module upgrader from attempting to delete hr.employee records
    that have linked hr.work.entry records on staging databases.
    """
    try:
        model_data = env['ir.model.data'].sudo().search([
            ('module', '=', 'factory_attendance_payroll'),
            ('model', '=', 'hr.employee')
        ])
        if model_data:
            model_data.write({'noupdate': True})
    except Exception:
        pass

def post_init_hook(env):
    """
    Post-Init Hook:
    Binds attendance reconciliation rules (ATT_RECON_VAR, OT_NET, DED_UNDERTIME)
    dynamically to all Jordan payroll structures in production.
    """
    try:
        structures = env['hr.payroll.structure'].search([('name', 'ilike', 'Jordan')])
        if not structures:
            structures = env['hr.payroll.structure'].search([])
            
        rules = env['hr.salary.rule'].search([('code', 'in', ['ATT_RECON_VAR', 'OT_NET', 'DED_UNDERTIME'])])
        
        for structure in structures:
            for rule in rules:
                existing = env['hr.salary.rule'].search([
                    ('code', '=', rule.code),
                    ('struct_id', '=', structure.id)
                ], limit=1)
                if not existing:
                    rule.write({'struct_id': structure.id})
    except Exception:
        pass
