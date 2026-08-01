def migrate(cr, version):
    cr.execute("""
        ALTER TABLE hr_employee
        ADD COLUMN IF NOT EXISTS acting_login_user_id integer
    """)
    cr.execute("""
        CREATE INDEX IF NOT EXISTS hr_employee_acting_login_user_id_index
        ON hr_employee (acting_login_user_id)
        WHERE acting_login_user_id IS NOT NULL
    """)
