# -*- coding: utf-8 -*-


def post_init_hook(env):
    # Use SQL to avoid pos_hr/pos_restaurant write() hooks that require a
    # single company when multiple POS configs exist across companies.
    env.cr.execute(
        """
        UPDATE pos_config
        SET enable_custom_cake = TRUE
        WHERE enable_custom_cake IS NOT TRUE
        """
    )
