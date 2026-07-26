# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'cake_category'
          AND column_name IN ('name_en', 'name_ar', 'name')
        """
    )
    columns = {row[0] for row in cr.fetchall()}
    if "name" in columns or "name_en" not in columns:
        return

    _logger.info("Migrating cake.category from name_en/name_ar to translatable name.")
    cr.execute("ALTER TABLE cake_category ADD COLUMN name varchar")
    cr.execute(
        """
        UPDATE cake_category
        SET name = COALESCE(NULLIF(name_en, ''), NULLIF(name_ar, ''), 'Category')
        """
    )
    cr.execute("ALTER TABLE cake_category ALTER COLUMN name SET NOT NULL")
    cr.execute("ALTER TABLE cake_category DROP COLUMN IF EXISTS name_en")
    cr.execute("ALTER TABLE cake_category DROP COLUMN IF EXISTS name_ar")

    cr.execute(
        """
        DELETE FROM ir_ui_menu
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'pos_custom_cake' AND name = 'menu_custom_cake_root'
        )
        """
    )
    cr.execute(
        """
        DELETE FROM ir_model_data
        WHERE module = 'pos_custom_cake' AND name = 'menu_custom_cake_root'
        """
    )
    cr.execute(
        """
        DELETE FROM ir_model_data
        WHERE module = 'pos_custom_cake' AND name = 'action_custom_cake_settings'
        """
    )
    cr.execute(
        """
        DELETE FROM ir_act_window
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'pos_custom_cake' AND name = 'action_custom_cake_settings'
        )
        """
    )
