# -*- coding: utf-8 -*-


def migrate(cr, version):
    cr.execute(
        """
        ALTER TABLE pos_advance_order
        ADD COLUMN IF NOT EXISTS deposit_pos_session_id INTEGER
        """
    )
    cr.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                  FROM pg_constraint
                 WHERE conname = 'pos_advance_order_deposit_pos_session_id_fkey'
            ) THEN
                ALTER TABLE pos_advance_order
                ADD CONSTRAINT pos_advance_order_deposit_pos_session_id_fkey
                FOREIGN KEY (deposit_pos_session_id)
                REFERENCES pos_session(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )
    cr.execute(
        """
        CREATE INDEX IF NOT EXISTS pos_advance_order_deposit_pos_session_id_index
        ON pos_advance_order (deposit_pos_session_id)
        """
    )
