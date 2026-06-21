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
        tracking=True,
        help="GPS Latitude of the customer location."
    )
    longitude = fields.Float(
        string='Longitude',
        digits=(10, 7),
        tracking=True,
        help="GPS Longitude of the customer location."
    )
    is_location_locked = fields.Boolean(
        string='Location Locked',
        default=False,
        tracking=True,
        help="Locks coordinate updates for salespeople once location is saved."
    )
    user_id = fields.Many2one(
        'res.users',
        string='Assigned Salesperson',
        required=True,
        default=lambda self: self.env.user,
        tracking=True
    )
    status = fields.Selection([
        ('lead', 'New Lead'),
        ('revisit', 'Revisit Lead'),
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

    def write(self, vals):
        if 'latitude' in vals or 'longitude' in vals:
            for record in self:
                if record.is_location_locked:
                    is_manager = self.env.user.has_group('sales_visit_tracking.group_sales_manager') or self.env.is_admin()
                    if not is_manager:
                        raise ValidationError(_("Customer location is locked. Only a Sales Manager or Administrator can modify it."))
                    
                    self.env['sales.visit.audit.log'].create({
                        'name': _("Lead Location Modified"),
                        'event_type': 'location_change',
                        'latitude': vals.get('latitude', record.latitude),
                        'longitude': vals.get('longitude', record.longitude),
                        'description': _("Location for Lead '%s' was updated by Manager '%s'.\nOld location: (%s, %s)\nNew location: (%s, %s)") % (
                            record.name, self.env.user.name, record.latitude, record.longitude, vals.get('latitude', record.latitude), vals.get('longitude', record.longitude)
                        )
                    })

        if 'user_id' in vals:
            for record in self:
                old_user_name = record.user_id.name or _("None")
                new_user_name = self.env['res.users'].browse(vals['user_id']).name or _("Unknown")
                self.env['sales.visit.audit.log'].create({
                    'name': _("Lead Reassigned"),
                    'event_type': 'assignment_change',
                    'description': _("Lead '%s' was reassigned from %s to %s by %s.") % (
                        record.name, old_user_name, new_user_name, self.env.user.name
                    )
                })

        return super(SalesVisitLead, self).write(vals)

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

        self.env['sales.visit.audit.log'].create({
            'name': _("Lead Converted to Customer"),
            'event_type': 'conversion',
            'latitude': self.latitude,
            'longitude': self.longitude,
            'description': _("Lead '%s' was successfully approved and converted to Customer Contact '%s' (Partner ID: %d)") % (
                self.name, partner.name, partner.id
            )
        })
        return partner
