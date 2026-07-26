# -*- coding: utf-8 -*-


def post_init_hook(env):
    env["pos.config"].search([]).write({"enable_custom_cake": True})
