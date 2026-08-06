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
    """Move site service from per-POS to one configuration per company."""
    _logger.info("[SITE_SERVICE] Running post-migrate to company-wide settings (version %s)", version)

    menu_cols = _table_columns(cr, "pos_site_service_menu")
    if not menu_cols:
        _logger.info("[SITE_SERVICE] Table pos_site_service_menu not found; nothing to migrate.")
        return

    if "company_id" not in menu_cols:
        cr.execute(
            """
            ALTER TABLE pos_site_service_menu
            ADD COLUMN company_id INTEGER
            """
        )
        menu_cols = _table_columns(cr, "pos_site_service_menu")

    if "pos_config_id" in menu_cols:
        cr.execute(
            """
            UPDATE pos_site_service_menu m
               SET company_id = pc.company_id
              FROM pos_config pc
             WHERE m.pos_config_id = pc.id
               AND m.company_id IS NULL
            """
        )
        cr.execute(
            """
            UPDATE pos_site_service_menu
               SET company_id = (
                        SELECT id FROM res_company ORDER BY id LIMIT 1
                   )
             WHERE company_id IS NULL
            """
        )

        cr.execute(
            """
            SELECT company_id, array_agg(id ORDER BY enable_site_service DESC, id)
              FROM pos_site_service_menu
             GROUP BY company_id
            HAVING COUNT(*) > 1
            """
        )
        for company_id, menu_ids in cr.fetchall():
            keep_id = menu_ids[0]
            drop_ids = menu_ids[1:]
            if drop_ids:
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
                    "[SITE_SERVICE] Merged duplicate menus for company id=%s into menu id=%s.",
                    company_id,
                    keep_id,
                )

        cr.execute(
            """
            ALTER TABLE pos_site_service_menu
            DROP COLUMN IF EXISTS pos_config_id
            """
        )
        _logger.info("[SITE_SERVICE] Dropped pos_config_id column.")

    _logger.info("[SITE_SERVICE] Company-wide site service migration completed.")
