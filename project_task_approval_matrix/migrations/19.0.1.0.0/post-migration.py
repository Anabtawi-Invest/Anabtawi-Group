def migrate(cr, version):
    """Initialize allocation display fields for databases upgrading the add-on."""
    cr.execute(
        """
        UPDATE project_task
           SET allocation_unit = 'hours',
               allocation_value = allocated_hours
         WHERE allocation_unit IS NULL
            OR allocation_value IS NULL
        """
    )
