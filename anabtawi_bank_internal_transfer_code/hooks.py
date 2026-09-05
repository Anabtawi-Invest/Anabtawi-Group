# -*- coding: utf-8 -*-


def post_init_hook(env):
    """Set LBT on existing banks that have no internal transfer value yet."""
    banks = env['res.bank'].search([('internal_transfer', 'in', [False, ''])])
    if banks:
        banks.write({'internal_transfer': 'LBT'})
