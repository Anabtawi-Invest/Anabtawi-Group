# -*- coding: utf-8 -*-
from odoo import fields, models


class CheckPaymentBlockedDate(models.Model):
    _name = 'check.payment.blocked.date'
    _description = 'Blocked Check Date'
    _order = 'date, id'

    date = fields.Date(required=True)
    company_id = fields.Many2one(
        'res.company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    _date_company_uniq = models.Constraint(
        'unique (date, company_id)',
        'This date is already blocked for check payments.',
    )


class ResCompany(models.Model):
    _inherit = 'res.company'

    check_payment_blocked_date_ids = fields.One2many(
        'check.payment.blocked.date',
        'company_id',
        string='Blocked Check Dates',
    )


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    check_payment_blocked_date_ids = fields.One2many(
        related='company_id.check_payment_blocked_date_ids',
        readonly=False,
    )
