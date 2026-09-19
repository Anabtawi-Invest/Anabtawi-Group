# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Assign existing purchase templates to the main company and drop global stage code unique."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    main_company = env.ref('base.main_company', raise_if_not_found=False)
    if not main_company:
        main_company = env['res.company'].search([], order='id', limit=1)
    if main_company:
        cr.execute(
            """
            UPDATE tanmya_purchase_stage_type
               SET company_id = %s
             WHERE company_id IS NULL
            """,
            (main_company.id,),
        )

    # Old global unique(code) blocks shared codes across companies.
    cr.execute(
        """
        ALTER TABLE tanmya_purchase_stage
        DROP CONSTRAINT IF EXISTS tanmya_purchase_stage_tanmya_stage_code_unique
        """
    )
