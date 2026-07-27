# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def pre_init_hook(env):
    """Emergency hook to convert res_company.name and res_partner.name
    from jsonb back to varchar in PostgreSQL.
    
    This instantly resolves:
      AttributeError: 'dict' object has no attribute 'encode'
    when saving records or sending emails.
    """
    cr = env.cr
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
            
        data_type = row[0]
        _logger.info("[fix_company_name] Table %s.name data_type is: %s", table, data_type)
        
        if data_type == 'jsonb':
            _logger.info("[fix_company_name] Reverting %s.name from jsonb back to varchar...", table)
            try:
                cr.execute(f"ALTER TABLE {table} ADD COLUMN name_plain varchar;")
                cr.execute(f"""
                    UPDATE {table} 
                       SET name_plain = COALESCE(
                           name->>'en_US', 
                           name->>'ar_001', 
                           (SELECT value FROM jsonb_each_text(name) LIMIT 1),
                           name::text
                       ) 
                     WHERE name IS NOT NULL;
                """)
                cr.execute(f"ALTER TABLE {table} DROP COLUMN name;")
                cr.execute(f"ALTER TABLE {table} RENAME COLUMN name_plain TO name;")
                _logger.info("[fix_company_name] ✅ Table %s.name successfully reverted to varchar.", table)
            except Exception as e:
                _logger.error("[fix_company_name] Failed to revert %s.name: %s", table, e)
