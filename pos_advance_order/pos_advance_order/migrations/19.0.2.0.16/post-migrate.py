# -*- coding: utf-8 -*-


def migrate(cr, version):
    cr.execute(
        """
        UPDATE pos_advance_order
        SET amount_tendered = advance_amount
        WHERE COALESCE(amount_tendered, 0) = 0
          AND COALESCE(advance_amount, 0) > 0
        """
    )
