def migrate(cr, version):
    cr.execute("""
        ALTER TABLE res_users
        ADD COLUMN IF NOT EXISTS is_branch_user boolean DEFAULT false
    """)
