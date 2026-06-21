# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SalesVisitAuditLog(models.Model):
    _name = 'sales.visit.audit.log'
    _description = 'Immutable Sales Visit Audit Log'
    _order = 'timestamp desc, id desc'

    name = fields.Char(string='Action', required=True, readonly=True)
    user_id = fields.Many2one('res.users', string='User', required=True, readonly=True, default=lambda self: self.env.user)
    timestamp = fields.Datetime(string='Timestamp', required=True, readonly=True, default=fields.Datetime.now)
    event_type = fields.Selection([
        ('assignment_change', 'Assignment Change'),
        ('gps_capture', 'GPS Capture'),
        ('location_change', 'Location Change'),
        ('check_in', 'Check-In'),
        ('check_out', 'Check-Out'),
        ('visit_result', 'Visit Result'),
        ('conversion', 'Customer Conversion'),
        ('blocked_check_in', 'Blocked Check-In Attempt'),
        ('system', 'System Action')
    ], string='Event Type', required=True, readonly=True)
    description = fields.Text(string='Details', readonly=True)
    latitude = fields.Float(string='Latitude', digits=(10, 7), readonly=True)
    longitude = fields.Float(string='Longitude', digits=(10, 7), readonly=True)

    def write(self, vals):
        raise UserError(_("Audit logs are immutable and cannot be modified."))

    def unlink(self):
        raise UserError(_("Audit logs are immutable and cannot be deleted."))
