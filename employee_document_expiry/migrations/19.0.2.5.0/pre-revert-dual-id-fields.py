"""Undo 19.0.2.4.0: restore single national_number column, drop national_id."""


def migrate(cr, version):
    cr.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'employee_jo_dependant_line'
        """
    )
    cols = {row[0] for row in cr.fetchall()}
    if not cols:
        return
    if "national_id" in cols:
        cr.execute("ALTER TABLE employee_jo_dependant_line DROP COLUMN national_id")
    if "identification_number" in cols and "national_number" not in cols:
        cr.execute(
            """
            ALTER TABLE employee_jo_dependant_line
            RENAME COLUMN identification_number TO national_number
            """
        )
