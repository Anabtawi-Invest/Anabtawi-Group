# -*- coding: utf-8 -*-
def migrate(cr, version):
    cr.execute(
        """
        UPDATE approval_category AS c
           SET x_create_contact_on_approve = TRUE
          FROM ir_model_data AS d
         WHERE d.model = 'approval.category'
           AND d.module = 'approvals_create_customer'
           AND d.name = 'approval_category_data_create_customer'
           AND d.res_id = c.id
           AND COALESCE(c.x_create_contact_on_approve, FALSE) = FALSE
        """
    )
