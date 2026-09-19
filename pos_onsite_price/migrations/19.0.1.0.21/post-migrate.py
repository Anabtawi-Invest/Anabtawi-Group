# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Convert boolean is_on_site → selection service_type on quantity ranges."""
    cr.execute(
        """
        SELECT 1
          FROM information_schema.tables
         WHERE table_name = 'pos_onsite_price_range'
         LIMIT 1
        """
    )
    if not cr.fetchone():
        return

    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'pos_onsite_price_range'
           AND column_name = 'service_type'
         LIMIT 1
        """
    )
    has_service_type = bool(cr.fetchone())
    if not has_service_type:
        cr.execute(
            "ALTER TABLE pos_onsite_price_range ADD COLUMN service_type VARCHAR"
        )

    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'pos_onsite_price_range'
           AND column_name = 'is_on_site'
         LIMIT 1
        """
    )
    if cr.fetchone():
        cr.execute(
            """
            UPDATE pos_onsite_price_range
               SET service_type = CASE
                    WHEN COALESCE(is_on_site, FALSE) IS TRUE THEN 'on_site'
                    ELSE 'none'
               END
             WHERE service_type IS NULL
                OR service_type = ''
            """
        )
        updated = cr.rowcount
        _logger.info(
            "[ONSITE] Migrated is_on_site → service_type on %s range row(s).",
            updated,
        )
    else:
        cr.execute(
            """
            UPDATE pos_onsite_price_range
               SET service_type = 'on_site'
             WHERE service_type IS NULL OR service_type = ''
            """
        )

    # Ensure new price columns exist (ORM usually creates them; keep defensive).
    for col in ("service_price", "cutting_service_price"):
        cr.execute(
            """
            SELECT 1
              FROM information_schema.columns
             WHERE table_name = 'pos_onsite_price_range'
               AND column_name = %s
             LIMIT 1
            """,
            (col,),
        )
        if not cr.fetchone():
            cr.execute(
                f"ALTER TABLE pos_onsite_price_range ADD COLUMN {col} DOUBLE PRECISION DEFAULT 0"
            )
