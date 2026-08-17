from odoo import api, SUPERUSER_ID

def post_init_hook(env):
    # 1. Bind rules to Jordan structure
    structure = env['hr.payroll.structure'].search([('name', '=', 'Jordan: Employee THE ONE')], limit=1)
    if not structure:
        structure = env['hr.payroll.structure'].search([('name', 'ilike', 'Jordan')], limit=1)
    if structure:
        rules = env['hr.salary.rule'].search([('code', 'in', ['ATT_RECON_VAR', 'OT_NET', 'DED_UNDERTIME'])])
        rules.write({'struct_id': structure.id})

    # 2. Get or create Employee 1: Test 1 (+5:00 Net OT)
    emp1 = env['hr.employee'].sudo().search([('work_email', '=', 'test1@example.com')], limit=1)
    if not emp1:
        emp1 = env['hr.employee'].sudo().create({
            'name': 'Test 1',
            'job_title': 'Factory Operator Test 1',
            'work_email': 'test1@example.com',
        })
    else:
        emp1.sudo().write({'name': 'Test 1'})

    # 3. Get or create Employee 2: Test 2 (-2:00 Net Undertime)
    emp2 = env['hr.employee'].sudo().search([('work_email', '=', 'test2@example.com')], limit=1)
    if not emp2:
        emp2 = env['hr.employee'].sudo().create({
            'name': 'Test 2',
            'job_title': 'Factory Operator Test 2',
            'work_email': 'test2@example.com',
        })
    else:
        emp2.sudo().write({'name': 'Test 2'})

    # 4. Clean old attendance and overtime records for Test 1 and Test 2
    test_emp_ids = [emp1.id, emp2.id]
    env['hr.attendance'].sudo().search([('employee_id', 'in', test_emp_ids)]).unlink()
    if 'hr.attendance.overtime.line' in env:
        env['hr.attendance.overtime.line'].sudo().search([('employee_id', 'in', test_emp_ids)]).unlink()

    # 5. Populate fresh July 2026 attendances for Test 1 (+5:00 Net OT)
    emp1_attendances = []
    # 10 Overtime Days (July 1 - 10) -> +1.5h OT each = 15:00 Gross OT
    for day in range(1, 11):
        d_str = f"2026-07-{day:02d}"
        emp1_attendances.append({
            'employee_id': emp1.id,
            'check_in': f"{d_str} 08:00:00",
            'check_out': f"{d_str} 18:30:00",
        })
    # 5 Short Days (July 13 - 17) -> -2.0h UT each = 10:00 Gross UT
    for day in range(13, 18):
        d_str = f"2026-07-{day:02d}"
        emp1_attendances.append({
            'employee_id': emp1.id,
            'check_in': f"{d_str} 10:00:00",
            'check_out': f"{d_str} 17:00:00",
        })
    # Standard Days
    for day in list(range(20, 25)) + list(range(27, 32)):
        d_str = f"2026-07-{day:02d}"
        emp1_attendances.append({
            'employee_id': emp1.id,
            'check_in': f"{d_str} 08:00:00",
            'check_out': f"{d_str} 17:00:00",
        })

    for vals in emp1_attendances:
        env['hr.attendance'].sudo().create(vals)

    # 6. Populate fresh July 2026 attendances for Test 2 (-2:00 Net Undertime)
    emp2_attendances = []
    # 4 Overtime Days (July 1 - 4) -> +1.0h OT each = 04:00 Gross OT
    for day in range(1, 5):
        d_str = f"2026-07-{day:02d}"
        emp2_attendances.append({
            'employee_id': emp2.id,
            'check_in': f"{d_str} 08:00:00",
            'check_out': f"{d_str} 18:00:00",
        })
    # 3 Short Days (July 6 - 8) -> -2.0h UT each = 06:00 Gross UT
    for day in range(6, 9):
        d_str = f"2026-07-{day:02d}"
        emp2_attendances.append({
            'employee_id': emp2.id,
            'check_in': f"{d_str} 10:00:00",
            'check_out': f"{d_str} 17:00:00",
        })
    # Standard Days
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
