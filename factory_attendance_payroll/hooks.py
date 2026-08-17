from odoo import api, SUPERUSER_ID

def post_init_hook(env):
    # 1. Bind rules to Jordan structure
    structure = env['hr.payroll.structure'].search([('name', '=', 'Jordan: Employee THE ONE')], limit=1)
    if not structure:
        structure = env['hr.payroll.structure'].search([('name', 'ilike', 'Jordan')], limit=1)
    if structure:
        rules = env['hr.salary.rule'].search([('code', 'in', ['ATT_RECON_VAR', 'OT_NET', 'DED_UNDERTIME'])])
        rules.write({'struct_id': structure.id})

    # 2. Search for Employee 1: Factory Test 1 (+5:00 Net OT)
    emp1 = env.ref('factory_attendance_payroll.test_factory_employee', raise_if_not_found=False)
    if not emp1:
        emp1 = env['hr.employee'].sudo().search([('work_email', '=', 'factorytest1@example.com')], limit=1)
    if emp1:
        emp1.sudo().write({'name': 'Factory Test 1'})

    # 3. Search for Employee 2: Factory Test 2 (-2:00 Net Undertime)
    emp2 = env.ref('factory_attendance_payroll.test_undertime_employee', raise_if_not_found=False)
    if not emp2:
        emp2 = env['hr.employee'].sudo().search([('work_email', '=', 'factorytest2@example.com')], limit=1)
    if emp2:
        emp2.sudo().write({'name': 'Factory Test 2'})

    if not emp1 or not emp2:
        return

    # 4. Create July 2026 attendances for Factory Test 1 if none exist
    existing_att_1 = env['hr.attendance'].sudo().search_count([('employee_id', '=', emp1.id)])
    if existing_att_1 == 0:
        emp1_attendances = []
        for day in range(1, 11):
            d_str = f"2026-07-{day:02d}"
            emp1_attendances.append({
                'employee_id': emp1.id,
                'check_in': f"{d_str} 08:00:00",
                'check_out': f"{d_str} 18:30:00",
            })
        for day in range(13, 18):
            d_str = f"2026-07-{day:02d}"
            emp1_attendances.append({
                'employee_id': emp1.id,
                'check_in': f"{d_str} 10:00:00",
                'check_out': f"{d_str} 17:00:00",
            })
        for day in list(range(20, 25)) + list(range(27, 32)):
            d_str = f"2026-07-{day:02d}"
            emp1_attendances.append({
                'employee_id': emp1.id,
                'check_in': f"{d_str} 08:00:00",
                'check_out': f"{d_str} 17:00:00",
            })

        for vals in emp1_attendances:
            env['hr.attendance'].sudo().create(vals)

    # 5. Create July 2026 attendances for Factory Test 2 if none exist
    existing_att_2 = env['hr.attendance'].sudo().search_count([('employee_id', '=', emp2.id)])
    if existing_att_2 == 0:
        emp2_attendances = []
        for day in range(1, 5):
            d_str = f"2026-07-{day:02d}"
            emp2_attendances.append({
                'employee_id': emp2.id,
                'check_in': f"{d_str} 08:00:00",
                'check_out': f"{d_str} 18:00:00",
            })
        for day in range(6, 9):
            d_str = f"2026-07-{day:02d}"
            emp2_attendances.append({
                'employee_id': emp2.id,
                'check_in': f"{d_str} 10:00:00",
                'check_out': f"{d_str} 17:00:00",
            })
        std_days = [9, 10] + list(range(13, 18)) + list(range(20, 25)) + list(range(27, 32))
        for day in std_days:
            d_str = f"2026-07-{day:02d}"
            emp2_attendances.append({
                'employee_id': emp2.id,
                'check_in': f"{d_str} 08:00:00",
                'check_out': f"{d_str} 17:00:00",
            })

        for vals in emp2_attendances:
            env['hr.attendance'].sudo().create(vals)
