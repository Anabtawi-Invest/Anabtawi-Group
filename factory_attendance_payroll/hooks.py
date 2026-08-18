from odoo import api, SUPERUSER_ID

def post_init_hook(env):
    """
    Production Post-Init Hook:
    1. Binds attendance reconciliation rules (ATT_RECON_VAR, OT_NET, DED_UNDERTIME)
       dynamically to all Jordan payroll structures in production.
    """
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
