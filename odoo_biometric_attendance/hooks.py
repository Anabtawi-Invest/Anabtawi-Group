# -*- coding: utf-8 -*-


def post_init_hook(env):
    env.cr.execute(
        """
        UPDATE hr_employee
           SET biometric_user_id = ''
         WHERE biometric_user_id IS NULL
        """
    )
