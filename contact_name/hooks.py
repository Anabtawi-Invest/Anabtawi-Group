# -*- coding: utf-8 -*-
import json
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Convert the res_partner.name column from varchar to jsonb so
    that Odoo's ORM treats it as a translatable field and shows
    the language badge (EN / AR) in the UI.

    In Odoo 17+, translatable Char/Text fields are stored as JSONB
    columns where each language code maps to its translated value,
    e.g.  {"en_US": "John", "ar_001": "جون"}

    When we add translate=True to an existing non-translatable field
    the ORM *should* handle the conversion during _auto_init(), but
    on Odoo.sh this sometimes doesn't trigger properly.  This hook
    ensures the migration always happens.
    """
    cr = env.cr

    # 1. Check current column type
    cr.execute("""
        SELECT data_type
          FROM information_schema.columns
         WHERE table_name  = 'res_partner'
           AND column_name = 'name'
    """)
    row = cr.fetchone()
    if not row:
        _logger.warning("[contact_name] Column res_partner.name not found – skipping migration.")
        return

    col_type = row[0]
    _logger.info("[contact_name] res_partner.name column type: %s", col_type)

    if col_type == 'jsonb':
        _logger.info("[contact_name] Column is already jsonb – nothing to do.")
        return

    # 2. Detect installed languages
    cr.execute("SELECT code FROM res_lang WHERE active = true")
    lang_codes = [r[0] for r in cr.fetchall()]
    if not lang_codes:
        lang_codes = ['en_US']
    _logger.info("[contact_name] Active languages: %s", lang_codes)

    # 3. Convert varchar → jsonb
    #    Wrap each existing plain-text value into a JSON object that
    #    maps every active language to the same value.  Users can then
    #    edit individual translations via the UI.
    _logger.info("[contact_name] Converting res_partner.name from %s to jsonb ...", col_type)

    # Build a SQL expression that creates {"en_US": name, "ar_001": name, ...}
    json_parts = ", ".join(
        "'{lang}', name".format(lang=lang) for lang in lang_codes
    )
    build_json = "jsonb_build_object({parts})".format(parts=json_parts)

    # Step A – add a temporary column
    cr.execute("ALTER TABLE res_partner ADD COLUMN name_tmp jsonb")

    # Step B – populate it (NULL names stay NULL)
    cr.execute("""
        UPDATE res_partner
           SET name_tmp = {build_json}
         WHERE name IS NOT NULL
    """.format(build_json=build_json))

    # Step C – drop old column, rename new one
    cr.execute("ALTER TABLE res_partner DROP COLUMN name")
    cr.execute("ALTER TABLE res_partner RENAME COLUMN name_tmp TO name")

    _logger.info("[contact_name] ✅ Column res_partner.name converted to jsonb successfully.")
