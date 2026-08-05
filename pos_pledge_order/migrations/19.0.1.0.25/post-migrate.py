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
    """Migrate legacy site-service data stored on pos.config / config_id lines."""
    _logger.info("[SITE_SERVICE] Running post-migrate for pos_pledge_order version %s", version)

    line_cols = _table_columns(cr, "pos_site_service_product_line")
    if not line_cols:
        _logger.info("[SITE_SERVICE] Table pos_site_service_product_line not found; nothing to migrate.")
        return

    menu_cols = _table_columns(cr, "pos_site_service_menu")
    config_cols = _table_columns(cr, "pos_config")

    if menu_cols and "enable_site_service" in config_cols:
        cr.execute(
            """
            INSERT INTO pos_site_service_menu (
                name, active, enable_site_service, pos_config_id,
                threshold, service_product_id, service_price,
                create_uid, write_uid, create_date, write_date
            )
            SELECT
                COALESCE(pc.name, 'Site Service'),
                true,
                COALESCE(pc.enable_site_service, false),
                pc.id,
                COALESCE(pc.site_service_threshold, 31.0),
                pc.site_service_product_id,
                COALESCE(pc.site_service_price, 0.0),
                1, 1, NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC'
            FROM pos_config pc
            WHERE COALESCE(pc.enable_site_service, false) = true
              AND NOT EXISTS (
                    SELECT 1
                      FROM pos_site_service_menu m
                     WHERE m.pos_config_id = pc.id
              )
            """
        )
        _logger.info("[SITE_SERVICE] Migrated pos.config site-service settings into pos.site.service.menu.")

    if "config_id" in line_cols:
        if "menu_id" not in line_cols:
            cr.execute(
                """
                ALTER TABLE pos_site_service_product_line
                ADD COLUMN menu_id INTEGER
                """
            )
            line_cols = _table_columns(cr, "pos_site_service_product_line")

        menu_table_cols = _table_columns(cr, "pos_site_service_menu")
        if "menu_id" in line_cols and menu_table_cols:
            cr.execute(
                """
                UPDATE pos_site_service_product_line pl
                   SET menu_id = m.id
                  FROM pos_site_service_menu m
                 WHERE pl.config_id = m.pos_config_id
                   AND pl.menu_id IS NULL
                """
            )
            cr.execute(
                """
                DELETE FROM pos_site_service_product_line
                 WHERE menu_id IS NULL
                """
            )
            _logger.info("[SITE_SERVICE] Linked product lines from config_id to menu_id.")

        cr.execute(
            """
            ALTER TABLE pos_site_service_product_line
            DROP COLUMN IF EXISTS config_id
            """
        )
        _logger.info("[SITE_SERVICE] Dropped legacy config_id column on product lines.")

    _logger.info("[SITE_SERVICE] Post-migrate completed.")
