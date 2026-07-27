# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def _convert_name_columns_to_jsonb(env):
    """Convert res_partner.name and res_company.name columns from varchar to jsonb
    in PostgreSQL before or after module loading.
    
    This avoids the PostgreSQL error:
      psycopg2.errors.UndefinedFunction: operator does not exist: character varying ->> unknown
    when Odoo ORM queries res_company or res_partner during module installation.
    """
    cr = env.cr

    # Detect installed & active languages
    cr.execute("SELECT code FROM res_lang WHERE active = true")
    lang_codes = [r[0] for r in cr.fetchall()]
    if not lang_codes:
        lang_codes = ['en_US']

    _logger.info("[contact_name] Active languages for jsonb conversion: %s", lang_codes)

    # Build SQL jsonb_build_object expression
    json_parts = ", ".join("'{lang}', name".format(lang=lang) for lang in lang_codes)
    build_json = "jsonb_build_object({parts})".format(parts=json_parts)

    # Both res_partner and res_company store `name` columns that Odoo links
    for table in ['res_partner', 'res_company']:
        cr.execute("""
            SELECT data_type
              FROM information_schema.columns
             WHERE table_name = %s
               AND column_name = 'name'
        """, (table,))
        row = cr.fetchone()

        if not row:
            continue

        col_type = row[0]
        if col_type == 'jsonb':
            _logger.info("[contact_name] Table %s.name is already jsonb.", table)
            continue

        _logger.info("[contact_name] Converting %s.name from %s to jsonb...", table, col_type)
        try:
            cr.execute(f"ALTER TABLE {table} ADD COLUMN name_tmp jsonb")
            cr.execute(f"UPDATE {table} SET name_tmp = {build_json} WHERE name IS NOT NULL")
            cr.execute(f"ALTER TABLE {table} DROP COLUMN name")
            cr.execute(f"ALTER TABLE {table} RENAME COLUMN name_tmp TO name")
            _logger.info("[contact_name] ✅ Converted %s.name to jsonb successfully.", table)
        except Exception as e:
            _logger.error("[contact_name] Error converting %s.name to jsonb: %s", table, e)


def pre_init_hook(env):
    """Executes BEFORE module graph loading to convert DB columns prior to ORM queries."""
    _logger.info("[contact_name] Running pre_init_hook...")
    _convert_name_columns_to_jsonb(env)


def post_init_hook(env):
    """Executes AFTER module graph loading as a safety net."""
    _logger.info("[contact_name] Running post_init_hook...")
    _convert_name_columns_to_jsonb(env)
