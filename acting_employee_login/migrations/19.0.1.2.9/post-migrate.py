# -*- coding: utf-8 -*-

ACTING_THREAD_COLUMNS = (
    ('acting_employee_id', 'integer'),
    ('acting_employee_name', 'varchar'),
    ('acting_branch_access_id', 'integer'),
    ('acting_branch_name', 'varchar'),
)


def migrate(cr, version):
    """Add acting identity columns to every mail.thread table.

    Fields are defined on mail.thread by acting_employee_login, but tables
    created before that module was upgraded (e.g. pos_advance_order) may miss
    the corresponding columns and crash on read.
    """
    cr.execute("""
        SELECT model
        FROM ir_model
        WHERE is_mail_thread = TRUE
          AND model != 'mail.thread'
    """)
    for (model,) in cr.fetchall():
        table = model.replace('.', '_')
        cr.execute("""
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name = %s
        """, (table,))
        if not cr.fetchone():
            continue
        for column, col_type in ACTING_THREAD_COLUMNS:
            cr.execute(
                f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{column}" {col_type}'
            )
        cr.execute(f"""
            CREATE INDEX IF NOT EXISTS {table}_acting_employee_id_index
            ON "{table}" (acting_employee_id)
            WHERE acting_employee_id IS NOT NULL
        """)
        cr.execute(f"""
            CREATE INDEX IF NOT EXISTS {table}_acting_branch_access_id_index
            ON "{table}" (acting_branch_access_id)
            WHERE acting_branch_access_id IS NOT NULL
        """)
