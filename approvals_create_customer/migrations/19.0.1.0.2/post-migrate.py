# -*- coding: utf-8 -*-
def migrate(cr, version):
    # Turn off approval_contact rules on the portal Create Customer category.
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'approval_category'
           AND column_name = 'x_create_contact_on_approve'
        """
    )
    if not cr.fetchone():
        return
    cr.execute(
        """
        UPDATE approval_category AS c
           SET x_create_contact_on_approve = FALSE
          FROM ir_model_data AS d
         WHERE d.model = 'approval.category'
           AND d.module = 'approvals_create_customer'
           AND d.name = 'approval_category_data_create_customer'
           AND d.res_id = c.id
        """
    )
