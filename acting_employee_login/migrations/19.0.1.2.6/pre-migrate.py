def migrate(cr, version):
    cr.execute("""
        ALTER TABLE acting_branch_access
        ADD COLUMN IF NOT EXISTS branch_password varchar
    """)
    cr.execute("""
        ALTER TABLE acting_branch_access
        DROP COLUMN IF EXISTS branch_password_hash
    """)
