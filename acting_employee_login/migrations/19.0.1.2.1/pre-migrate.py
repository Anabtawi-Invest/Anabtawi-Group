def migrate(cr, version):
    cr.execute("""
        ALTER TABLE mail_message
        ADD COLUMN IF NOT EXISTS acting_branch_access_id integer
    """)
    cr.execute("""
        ALTER TABLE mail_message
        ADD COLUMN IF NOT EXISTS acting_branch_name varchar
    """)
