# -*- coding: utf-8 -*-
import logging
import secrets

_logger = logging.getLogger(__name__)

CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CODE_LENGTH = 4


def migrate(cr, version):
    cr.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'pos_cake_upload_session'
          AND column_name = 'code'
        """
    )
    if not cr.fetchone():
        return

    cr.execute(
        """
        SELECT id
        FROM pos_cake_upload_session
        WHERE code IS NULL OR code = ''
        """
    )
    rows = cr.fetchall()
    if not rows:
        return

    used = set()
    cr.execute("SELECT code FROM pos_cake_upload_session WHERE code IS NOT NULL AND code != ''")
    used.update(code for (code,) in cr.fetchall())

    for (session_id,) in rows:
        code = None
        for _attempt in range(50):
            candidate = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if candidate not in used:
                code = candidate
                used.add(candidate)
                break
        if not code:
            _logger.warning("Could not generate upload code for session %s", session_id)
            continue
        cr.execute(
            "UPDATE pos_cake_upload_session SET code = %s WHERE id = %s",
            (code, session_id),
        )
        _logger.info("Assigned upload code %s to session %s", code, session_id)
