def migrate(cr, version):
    """Rename is_employee_discount -> allowed_for_employee if the old column exists."""
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'pos_predefined_discount'
           AND column_name = 'is_employee_discount'
        """
    )
    if not cr.fetchone():
        return

    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'pos_predefined_discount'
           AND column_name = 'allowed_for_employee'
        """
    )
    if cr.fetchone():
        cr.execute(
            """
            UPDATE pos_predefined_discount
               SET allowed_for_employee = COALESCE(allowed_for_employee, False)
                  OR COALESCE(is_employee_discount, False)
            """
        )
        cr.execute("ALTER TABLE pos_predefined_discount DROP COLUMN is_employee_discount")
    else:
        cr.execute(
            """
            ALTER TABLE pos_predefined_discount
            RENAME COLUMN is_employee_discount TO allowed_for_employee
            """
        )
