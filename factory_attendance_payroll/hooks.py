from odoo import api, SUPERUSER_ID

def post_init_hook(env):
    # 1. Universal Binding: Bind rules to ALL Jordan payroll structures in the system
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

    # 2. Safely ensure wage=500 on all overtime demo employee refs
    for ref_xml_id in ['factory_emp_ot', 'test_factory_employee', 'factory_test_1_employee']:
        emp = env.ref(f'factory_attendance_payroll.{ref_xml_id}', raise_if_not_found=False)
        if emp:
            emp.sudo().write({'wage': 500.0, 'name': 'Factory Employee Overtime'})

    # 3. Safely ensure wage=500 on all undertime demo employee refs
    for ref_xml_id in ['factory_emp_ut', 'test_undertime_employee', 'factory_test_2_employee']:
        emp = env.ref(f'factory_attendance_payroll.{ref_xml_id}', raise_if_not_found=False)
        if emp:
            emp.sudo().write({'wage': 500.0, 'name': 'Factory Employee Undertime'})
