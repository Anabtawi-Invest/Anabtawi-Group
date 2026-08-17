from odoo import api, SUPERUSER_ID

def post_init_hook(env):
    structure = env['hr.payroll.structure'].search([('name', '=', 'Jordan: Employee THE ONE')], limit=1)
    if not structure:
        structure = env['hr.payroll.structure'].search([('name', 'ilike', 'Jordan')], limit=1)
    if structure:
        rules = env['hr.salary.rule'].search([('code', 'in', ['ATT_RECON_VAR', 'OT_NET', 'DED_UNDERTIME'])])
        rules.write({'struct_id': structure.id})

    # Purge old test data for test employees to ensure 100% clean calculation
    test_employees = env['hr.employee'].sudo().search([
        ('work_email', 'in', ['factory.test@example.com', 'factory.undertime@example.com'])
    ])
    if test_employees:
        old_attendances = env['hr.attendance'].sudo().search([('employee_id', 'in', test_employees.ids)])
        old_attendances.unlink()
        old_overtimes = env['hr.attendance.overtime.line'].sudo().search([('employee_id', 'in', test_employees.ids)])
        old_overtimes.unlink()
