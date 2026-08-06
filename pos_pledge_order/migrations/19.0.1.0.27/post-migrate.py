# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def _table_columns(cr, table_name):
    cr.execute(
        """
        SELECT column_name
          FROM information_schema.columns
         WHERE table_name = %s
        """,
        [table_name],
    )
    return {row[0] for row in cr.fetchall()}


def migrate(cr, version):
    """Keep one global site service configuration for all companies."""
    _logger.info("[SITE_SERVICE] Running post-migrate to global settings (version %s)", version)

    menu_cols = _table_columns(cr, "pos_site_service_menu")
    if not menu_cols:
        _logger.info("[SITE_SERVICE] Table pos_site_service_menu not found; nothing to migrate.")
        return

    cr.execute(
        """
        SELECT id
          FROM pos_site_service_menu
         ORDER BY enable_site_service DESC, id
        """
    )
    menu_ids = [row[0] for row in cr.fetchall()]
    if len(menu_ids) > 1:
        keep_id = menu_ids[0]
        drop_ids = menu_ids[1:]
        cr.execute(
            """
            UPDATE pos_site_service_product_line
               SET menu_id = %s
             WHERE menu_id = ANY(%s)
            """,
            [keep_id, drop_ids],
        )
        cr.execute(
            """
            DELETE FROM pos_site_service_menu
             WHERE id = ANY(%s)
            """,
            [drop_ids],
        )
        _logger.info(
            "[SITE_SERVICE] Merged %s site service menus into global menu id=%s.",
            len(drop_ids) + 1,
            keep_id,
        )

    if "company_id" in menu_cols:
        cr.execute(
            """
            ALTER TABLE pos_site_service_menu
            DROP COLUMN IF EXISTS company_id
            """
        )
        _logger.info("[SITE_SERVICE] Dropped company_id column.")

    _logger.info("[SITE_SERVICE] Global site service migration completed.")
