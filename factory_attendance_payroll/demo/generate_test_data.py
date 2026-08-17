"""
Helper script to generate a full month of test attendance records in Odoo for any employee.
Usage in Odoo shell:
    exec(open('NEW PAYROLL/factory_attendance_payroll/demo/generate_test_data.py').read())
    generate_full_month_attendances(env, employee_id=1, year=2026, month=8)
"""

import datetime
import calendar

def generate_full_month_attendances(env, employee_id, year=2026, month=8):
    Employee = env['hr.employee']
    Attendance = env['hr.attendance']

    employee = Employee.browse(employee_id)
    if not employee.exists():
        print(f"Employee ID {employee_id} not found.")
        return

    # Delete existing attendances in this window for clean testing
    start_date = datetime.date(year, month, 1)
    _, last_day = calendar.monthrange(year, month)
    end_date = datetime.date(year, month, last_day)

    existing = Attendance.search([
        ('employee_id', '=', employee.id),
        ('check_in', '>=', datetime.datetime.combine(start_date, datetime.time.min)),
        ('check_in', '<=', datetime.datetime.combine(end_date, datetime.time.max))
    ])
    existing.unlink()

    # Daily shifts pattern:
    created_count = 0
    total_ot_expected = 0.0
    total_undertime_expected = 0.0

    for day in range(1, last_day + 1):
        dt = datetime.date(year, month, day)
        weekday = dt.weekday()

        # Skip Sundays
        if weekday == 6:
            continue

        # Vary shift durations:
        # Mon / Thu: 10h shift (08:00 - 18:00) -> Net 9.0h (+1.0h OT)
        # Wed: 7h shift (08:00 - 15:00) -> Net 6.0h (-2.0h Undertime)
        # Tue / Fri / Sat: 9h shift (08:00 - 17:00) -> Net 8.0h (0.0h variance)
        if weekday in (0, 3):
            check_in = datetime.datetime.combine(dt, datetime.time(8, 0, 0))
            check_out = datetime.datetime.combine(dt, datetime.time(18, 0, 0))
            total_ot_expected += 1.0
        elif weekday == 2:
            check_in = datetime.datetime.combine(dt, datetime.time(8, 0, 0))
            check_out = datetime.datetime.combine(dt, datetime.time(15, 0, 0))
            total_undertime_expected += 2.0
        else:
            check_in = datetime.datetime.combine(dt, datetime.time(8, 0, 0))
            check_out = datetime.datetime.combine(dt, datetime.time(17, 0, 0))

        Attendance.create({
            'employee_id': employee.id,
            'check_in': check_in,
            'check_out': check_out,
        })
        created_count += 1

    env.cr.commit()
    print(f"Successfully created {created_count} attendance records for {employee.name} ({year}-{month:02d}).")
    print(f"Expected Monthly Overtime: {total_ot_expected} hrs")
    print(f"Expected Monthly Undertime: {total_undertime_expected} hrs")
    print(f"Expected Net Variance: {total_ot_expected - total_undertime_expected} hrs")
