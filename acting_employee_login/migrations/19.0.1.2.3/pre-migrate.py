def migrate(cr, version):
    cr.execute("""
        ALTER TABLE stock_picking
        ADD COLUMN IF NOT EXISTS acting_employee_id integer
    """)
    cr.execute("""
        ALTER TABLE stock_picking
        ADD COLUMN IF NOT EXISTS acting_employee_name varchar
    """)
    cr.execute("""
        ALTER TABLE stock_picking
        ADD COLUMN IF NOT EXISTS acting_branch_access_id integer
    """)
    cr.execute("""
        ALTER TABLE stock_picking
        ADD COLUMN IF NOT EXISTS acting_branch_name varchar
    """)
