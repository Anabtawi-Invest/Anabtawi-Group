# -*- coding: utf-8 -*-
from odoo import fields, models

# date.weekday(): Monday is 0, Sunday is 6.
BLOCKED_WEEKDAY_FIELDS = (
    'check_blocked_monday',
    'check_blocked_tuesday',
    'check_blocked_wednesday',
    'check_blocked_thursday',
    'check_blocked_friday',
    'check_blocked_saturday',
    'check_blocked_sunday',
)


class ResCompany(models.Model):
    _inherit = 'res.company'

    check_blocked_saturday = fields.Boolean(string='Saturday')
    check_blocked_sunday = fields.Boolean(string='Sunday')
    check_blocked_monday = fields.Boolean(string='Monday')
    check_blocked_tuesday = fields.Boolean(string='Tuesday')
    check_blocked_wednesday = fields.Boolean(string='Wednesday')
    check_blocked_thursday = fields.Boolean(string='Thursday')
    check_blocked_friday = fields.Boolean(string='Friday')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    check_blocked_saturday = fields.Boolean(related='company_id.check_blocked_saturday', readonly=False)
    check_blocked_sunday = fields.Boolean(related='company_id.check_blocked_sunday', readonly=False)
    check_blocked_monday = fields.Boolean(related='company_id.check_blocked_monday', readonly=False)
    check_blocked_tuesday = fields.Boolean(related='company_id.check_blocked_tuesday', readonly=False)
    check_blocked_wednesday = fields.Boolean(related='company_id.check_blocked_wednesday', readonly=False)
    check_blocked_thursday = fields.Boolean(related='company_id.check_blocked_thursday', readonly=False)
    check_blocked_friday = fields.Boolean(related='company_id.check_blocked_friday', readonly=False)
