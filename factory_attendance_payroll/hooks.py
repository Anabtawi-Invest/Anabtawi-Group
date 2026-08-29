from odoo import api, SUPERUSER_ID

def pre_init_hook(env):
    """
    Pre-Init Hook (Runs before XML data loading):
    Safely ensures all required PostgreSQL columns exist and cleans up legacy views using savepoints.
    """
    with env.cr.savepoint():
        try:
            env.cr.execute("""
                ALTER TABLE res_company 
                ADD COLUMN IF NOT EXISTS enable_overtime_calculation BOOLEAN DEFAULT TRUE;
            """)
        except Exception:
            pass

    with env.cr.savepoint():
        try:
            env.cr.execute("""
                ALTER TABLE hr_attendance 
                ADD COLUMN IF NOT EXISTS daily_undertime_hours DOUBLE PRECISION DEFAULT 0.0,
                ADD COLUMN IF NOT EXISTS daily_overtime_hours DOUBLE PRECISION DEFAULT 0.0;
            """)
        except Exception:
            pass

    with env.cr.savepoint():
        try:
            env.cr.execute("""
                ALTER TABLE hr_payslip 
                ADD COLUMN IF NOT EXISTS remaining_extra_hours_balance DOUBLE PRECISION DEFAULT 0.0;
            """)
        except Exception:
            pass

    with env.cr.savepoint():
        try:
            env.cr.execute("""
                UPDATE ir_model_data 
                SET noupdate = FALSE 
                WHERE module = 'factory_attendance_payroll' 
                  AND model = 'ir.ui.view';
            """)
        except Exception:
            pass

    with env.cr.savepoint():
        try:
            env.cr.execute("""
                UPDATE hr_work_entry 
                SET state = 'draft' 
                WHERE state = 'validated';
            """)
        except Exception:
            pass

def post_init_hook(env):
    """
    Post-Init Hook:
    1. Binds attendance reconciliation rules (ATT_RECON_VAR, OT_NET, DED_UNDERTIME)
       dynamically to ALL Payroll Structures in the database.
    2. Patches BASIC (Actual Salary) rule and DED_UNDERTIME to use dynamic hourly rate:
       hourly_rate = wage / sum(worked_days_line_ids.number_of_hours)
    """
    # -----------------------------------------------------------------------
    # Step 1: Bind reconciliation rules to all salary structures
    # -----------------------------------------------------------------------
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

    # -----------------------------------------------------------------------
    # Step 2: Patch BASIC (Actual Salary) rule with dynamic hourly rate
    # -----------------------------------------------------------------------
    BASIC_PYTHON_CODE = """\
wage = employee.wage or 0.0
# Dynamic hourly rate: wage / total scheduled hours (attendance + absent)
total_scheduled_hours = sum(line.number_of_hours for line in payslip.worked_days_line_ids)
if total_scheduled_hours > 0:
    hourly_rate = wage / total_scheduled_hours
else:
    weekly_hours = employee.resource_calendar_id.full_time_required_hours or 49.5
    hourly_rate = (wage / 26.0) / (weekly_hours / 6.0)
hourly_rate = round(hourly_rate, 4)

# Actual salary = raw attendance hours × hourly rate
actual_hours = sum(
    line.number_of_hours for line in payslip.worked_days_line_ids
    if (line.code or '').strip().upper() in ('WORK100', 'A', 'ATTENDANCE', 'WORK100_ATTENDANCE')
)
result = round(hourly_rate * actual_hours, 3)
"""

    # -----------------------------------------------------------------------
    # Step 3: Patch DED_UNDERTIME rule with dynamic hourly rate
    # -----------------------------------------------------------------------
    DED_UNDERTIME_PYTHON_CODE = """\
deficit_hours = round(payslip.undertime_cash_deduction_hours, 2) if payslip else 0.0
if deficit_hours < 0.01:
    result = 0.0
else:
    wage = employee.wage or 0.0
    # Dynamic hourly rate: wage / total scheduled hours (attendance + absent)
    total_scheduled_hours = sum(line.number_of_hours for line in payslip.worked_days_line_ids)
    if total_scheduled_hours > 0:
        hourly_rate = wage / total_scheduled_hours
    else:
        weekly_hours = employee.resource_calendar_id.full_time_required_hours or 49.5
        hourly_rate = (wage / 26.0) / (weekly_hours / 6.0)
    hourly_rate = round(hourly_rate, 4)
    result = -(deficit_hours * hourly_rate)
"""

    try:
        # Patch ALL BASIC rules (one per salary structure)
        basic_rules = env['hr.salary.rule'].sudo().search([('code', '=', 'BASIC')])
        for rule in basic_rules:
            rule.sudo().write({
                'amount_select': 'code',
                'amount_python_compute': BASIC_PYTHON_CODE,
            })
    except Exception:
        pass

    try:
        # Patch ALL DED_UNDERTIME rules (one per salary structure)
        ded_rules = env['hr.salary.rule'].sudo().search([('code', '=', 'DED_UNDERTIME')])
        for rule in ded_rules:
            rule.sudo().write({
                'amount_select': 'code',
                'amount_python_compute': DED_UNDERTIME_PYTHON_CODE,
            })
    except Exception:
        pass
