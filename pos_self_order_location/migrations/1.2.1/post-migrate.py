# -*- coding: utf-8 -*-

def migrate(cr, version):
    cr.execute("""
        UPDATE pos_config
           SET self_order_require_phone_otp = FALSE
         WHERE self_order_require_phone_otp = TRUE
    """)
