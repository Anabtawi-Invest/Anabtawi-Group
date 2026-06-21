# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class SalesVisitLead(models.Model):
    _name = 'sales.visit.lead'
    _description = 'Simplified Sales Lead'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string='Customer Name',
        required=True,
        tracking=True
    )
    mobile = fields.Char(
        string='Mobile Number',
        required=True,
        tracking=True
    )
    latitude = fields.Float(
        string='Latitude',
        digits=(10, 7),
        required=True,
        tracking=True,
        help="GPS Latitude of the customer location."
    )
    longitude = fields.Float(
        string='Longitude',
        digits=(10, 7),
        required=True,
        tracking=True,
        help="GPS Longitude of the customer location."
    )
    user_id = fields.Many2one(
        'res.users',
        string='Assigned Salesperson',
        required=True,
        default=lambda self: self.env.user,
        tracking=True
    )
    status = fields.Selection([
        ('lead', 'Lead'),
        ('revisit', 'Revisit'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
    ], string='Status', default='lead', required=True, tracking=True)

    notes = fields.Text(
        string='Notes'
    )
    next_visit_date = fields.Date(
        string='Next Visit Date',
        tracking=True
    )
    rejection_reason = fields.Selection([
        ('price', 'Price'),
        ('competitor', 'Competitor'),
        ('not_interested', 'Not Interested'),
        ('no_budget', 'No Budget'),
        ('other', 'Other')
    ], string='Rejection Reason', tracking=True)

    partner_id = fields.Many2one(
        'res.partner',
        string='Converted Customer',
        readonly=True,
        copy=False
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )

    def action_convert_to_customer(self):
        """Converts Lead to standard Odoo Contact (res.partner) and sets status to Approved."""
        self.ensure_one()
        if self.partner_id:
            return self.partner_id

        partner_vals = {
            'name': self.name,
            'mobile': self.mobile,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'geo_verified': True,
            'geolocation_date': fields.Datetime.now(),
            'user_id': self.user_id.id,
            'lead_id': self.id,
            'company_id': self.company_id.id,
        }
        partner = self.env['res.partner'].create(partner_vals)
        self.write({
            'partner_id': partner.id,
            'status': 'approved'
        })
        return partner
