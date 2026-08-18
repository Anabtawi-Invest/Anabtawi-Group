from odoo import api, SUPERUSER_ID

def post_init_hook(env):
    # 1. Bind rules to Jordan structure
    structure = env['hr.payroll.structure'].search([('name', '=', 'Jordan: Employee THE ONE')], limit=1)
    if not structure:
        structure = env['hr.payroll.structure'].search([('name', 'ilike', 'Jordan')], limit=1)
    if structure:
        rules = env['hr.salary.rule'].search([('code', 'in', ['ATT_RECON_VAR', 'OT_NET', 'DED_UNDERTIME'])])
        rules.write({'struct_id': structure.id})

    # 2. Ensure Wage = 500 JOD for demo employees
    demo_emp1 = env.ref('factory_attendance_payroll.factory_emp_ot', raise_if_not_found=False)
    if not demo_emp1:
        demo_emp1 = env['hr.employee'].sudo().search([('work_email', '=', 'factory.ot@example.com')], limit=1)
    if demo_emp1:
        demo_emp1.sudo().write({'wage': 500.0, 'name': 'Factory Employee Overtime'})

    demo_emp2 = env.ref('factory_attendance_payroll.factory_emp_ut', raise_if_not_found=False)
    if not demo_emp2:
        demo_emp2 = env['hr.employee'].sudo().search([('work_email', '=', 'factory.ut@example.com')], limit=1)
    if demo_emp2:
        demo_emp2.sudo().write({'wage': 500.0, 'name': 'Factory Employee Undertime'})
