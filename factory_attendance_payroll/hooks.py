from odoo import api, SUPERUSER_ID

def post_init_hook(env):
    structure = env['hr.payroll.structure'].search([('name', '=', 'Jordan: Employee THE ONE')], limit=1)
    if not structure:
        structure = env['hr.payroll.structure'].search([('name', 'ilike', 'Jordan')], limit=1)
    if structure:
        rules = env['hr.salary.rule'].search([('code', 'in', ['ATT_RECON_VAR', 'OT_NET', 'DED_UNDERTIME'])])
        rules.write({'struct_id': structure.id})
