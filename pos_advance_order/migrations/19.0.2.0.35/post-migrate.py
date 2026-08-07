# -*- coding: utf-8 -*-


def migrate(cr, version):
    cr.execute(
        """
        UPDATE pos_advance_order ao
           SET deposit_pos_session_id = matched.session_id
          FROM (
                SELECT ao2.id AS advance_id,
                       (
                           SELECT ps.id
                             FROM pos_session ps
                             JOIN account_move am ON am.id = ao2.advance_deposit_move_id
                            WHERE ps.config_id = COALESCE(ao2.from_pos_config_id, ao2.pos_config_id)
                              AND ps.company_id = ao2.company_id
                              AND ps.rescue IS FALSE
                              AND ps.start_at IS NOT NULL
                              AND am.create_date >= ps.start_at
                              AND am.create_date <= COALESCE(ps.stop_at, NOW() AT TIME ZONE 'UTC')
                            ORDER BY ps.id DESC
                            LIMIT 1
                       ) AS session_id
                  FROM pos_advance_order ao2
                 WHERE ao2.deposit_pos_session_id IS NULL
                   AND ao2.advance_deposit_move_id IS NOT NULL
                   AND ao2.state NOT IN ('draft', 'cancel')
               ) matched
         WHERE ao.id = matched.advance_id
           AND matched.session_id IS NOT NULL
        """
    )
