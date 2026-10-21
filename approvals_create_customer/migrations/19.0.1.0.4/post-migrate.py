# -*- coding: utf-8 -*-
def migrate(cr, version):
    # Commercial Register is mandatory for Create Customer portal requests.
    cr.execute(
        """
        UPDATE approval_category AS c
           SET requirer_document = 'required'
          FROM ir_model_data AS d
         WHERE d.model = 'approval.category'
           AND d.module = 'approvals_create_customer'
           AND d.name = 'approval_category_data_create_customer'
           AND d.res_id = c.id
        """
    )
    cr.execute(
        """
        UPDATE approval_category
           SET requirer_document = 'required'
         WHERE approval_type = 'create_customer'
           AND active IS TRUE
        """
    )
