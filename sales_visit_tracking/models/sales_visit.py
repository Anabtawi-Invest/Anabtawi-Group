# -*- coding: utf-8 -*-

import logging
import math
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class SalesVisit(models.Model):
    _name = 'sales.visit'
    _description = 'Salesperson Customer Visit'
    _order = 'check_in_time desc, id desc'

    name = fields.Char(
        string='Visit Reference',
        required=True,
        copy=False,
        readonly=True,
        default='/'
    )
    lead_id = fields.Many2one(
        'sales.visit.lead',
        string='Lead',
        required=True,
        ondelete='cascade',
        index=True
    )
    user_id = fields.Many2one(
        'res.users',
        string='Salesperson',
        required=True,
        default=lambda self: self.env.user,
        index=True
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Salesperson Employee',
        compute='_compute_employee_id',
        store=True,
        index=True
    )
    check_in_time = fields.Datetime(
        string='Arrival Time',
        readonly=True
    )
    check_in_latitude = fields.Float(
        string='Check-In Latitude',
        digits=(10, 7),
        readonly=True
    )
    check_in_longitude = fields.Float(
        string='Check-In Longitude',
        digits=(10, 7),
        readonly=True
    )
    check_out_time = fields.Datetime(
        string='Departure Time',
        readonly=True
    )
    check_out_latitude = fields.Float(
        string='Check-Out Latitude',
        digits=(10, 7),
        readonly=True
    )
    check_out_longitude = fields.Float(
        string='Check-Out Longitude',
        digits=(10, 7),
        readonly=True
    )
    distance_from_customer = fields.Float(
        string='Distance (m)',
        readonly=True
    )
    verification_status = fields.Selection([
        ('valid', 'Valid Visit (0-100m)'),
        ('warning', 'Warning (101-300m)'),
        ('invalid', 'Invalid Visit (>300m)')
    ], string='GPS Validation', readonly=True)

    duration = fields.Float(
        string='Duration (Hours)',
        compute='_compute_duration',
        store=True,
        readonly=True
    )
    result = fields.Selection([
        ('revisit', 'Revisit'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
    ], string='Outcome', readonly=True)

    rejection_reason = fields.Selection([
        ('price', 'Price'),
        ('competitor', 'Competitor'),
        ('not_interested', 'Not Interested'),
        ('no_budget', 'No Budget'),
        ('other', 'Other')
    ], string='Rejection Reason', readonly=True)

    next_visit_date = fields.Date(
        string='Next Visit Date',
        readonly=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )

    @api.depends('user_id')
    def _compute_employee_id(self):
        for visit in self:
            if visit.user_id:
                visit.employee_id = self.env['hr.employee'].search([('user_id', '=', visit.user_id.id)], limit=1)
            else:
                visit.employee_id = False

    @api.depends('check_in_time', 'check_out_time')
    def _compute_duration(self):
        for visit in self:
            if visit.check_in_time and visit.check_out_time:
                delta = visit.check_out_time - visit.check_in_time
                visit.duration = delta.total_seconds() / 3600.0
            else:
                visit.duration = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('sales.visit') or '/'
        return super().create(vals_list)

    @staticmethod
    def haversine_distance(lat1, lon1, lat2, lon2):
        R = 6371000.0  # Earth radius in meters
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lambda = math.radians(lon2 - lon1)
        a = math.sin(d_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0)**2
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return R * c

    @api.model
    def action_start_visit(self, lead_id, latitude, longitude):
        """Starts a visit, computes GPS verification, and creates a visit log."""
        lead = self.env['sales.visit.lead'].browse(lead_id)
        if not lead.exists():
            raise UserError(_("Lead record does not exist."))

        distance = self.haversine_distance(latitude, longitude, lead.latitude, lead.longitude)
        allowed_radius_param = self.env['ir.config_parameter'].sudo().get_param('sales_visit_tracking.allowed_radius')
        allowed_radius = float(allowed_radius_param) if allowed_radius_param else 100.0

        if distance <= allowed_radius:
            verif_status = 'valid'
        elif distance <= 300.0:
            verif_status = 'warning'
        else:
            verif_status = 'invalid'

        visit = self.create({
            'lead_id': lead.id,
            'user_id': self.env.user.id,
            'check_in_time': fields.Datetime.now(),
            'check_in_latitude': latitude,
            'check_in_longitude': longitude,
            'distance_from_customer': distance,
            'verification_status': verif_status,
        })

        # Automatically log background route point
        if visit.employee_id:
            self.env['sales.route.point'].create({
                'employee_id': visit.employee_id.id,
                'visit_id': visit.id,
                'timestamp': fields.Datetime.now(),
                'latitude': latitude,
                'longitude': longitude,
                'speed': 0.0,
                'heading': 0.0
            })

        return visit.id

    def action_end_visit(self, latitude, longitude, result, next_visit_date=None, rejection_reason=None):
        """Ends a visit, updates lead status, and converts/stores final outcome choices."""
        self.ensure_one()
        if self.check_out_time:
            raise UserError(_("Visit has already been completed."))

        if result == 'revisit' and not next_visit_date:
            raise ValidationError(_("Next visit date is required for a Revisit."))
        if result == 'rejected' and not rejection_reason:
            raise ValidationError(_("Rejection reason is required for a Rejection."))

        check_out_time = fields.Datetime.now()
        self.write({
            'check_out_time': check_out_time,
            'check_out_latitude': latitude,
            'check_out_longitude': longitude,
            'result': result,
            'next_visit_date': next_visit_date,
            'rejection_reason': rejection_reason,
        })

        # Process outcome workflows
        if result == 'revisit':
            self.lead_id.write({
                'status': 'revisit',
                'next_visit_date': next_visit_date
            })
        elif result == 'approved':
            self.lead_id.action_convert_to_customer()
        elif result == 'rejected':
            self.lead_id.write({
                'status': 'rejected',
                'rejection_reason': rejection_reason
            })

        # Automatically log final background route point
        if self.employee_id:
            self.env['sales.route.point'].create({
                'employee_id': self.employee_id.id,
                'visit_id': self.id,
                'timestamp': check_out_time,
                'latitude': latitude,
                'longitude': longitude,
                'speed': 0.0,
                'heading': 0.0
            })

        return True

    @api.model
    def get_dashboard_data(self):
        """Returns KPIs statistics for the Manager Dashboard."""
        today = fields.Date.context_today(self)
        
        visits_today = self.search([
            ('check_in_time', '>=', today.strftime('%Y-%m-%d 00:00:00')),
            ('check_in_time', '<=', today.strftime('%Y-%m-%d 23:59:59'))
        ])
        
        completed = visits_today.filtered(lambda v: v.check_out_time is not None)
        
        # Leads categories count today
        revisits = visits_today.filtered(lambda v: v.result == 'revisit')
        approved = visits_today.filtered(lambda v: v.result == 'approved')
        rejected = visits_today.filtered(lambda v: v.result == 'rejected')
        
        total_visits_count = len(visits_today)
        completed_count = len(completed)
        missed_count = len(visits_today.filtered(lambda v: v.check_out_time is None and v.check_in_time is not None))
        
        # GPS Compliance Rate
        valid_gps = len(visits_today.filtered(lambda v: v.verification_status == 'valid'))
        gps_compliance = (valid_gps / total_visits_count * 100.0) if total_visits_count > 0 else 100.0

        # Build list of active reps
        active_reps = len(visits_today.mapped('user_id'))
        
        return {
            'today_visits': total_visits_count,
            'completed_visits': completed_count,
            'missed_visits': missed_count,
            'revisit_count': len(revisits),
            'approved_count': len(approved),
            'rejected_count': len(rejected),
            'gps_compliance': round(gps_compliance, 1),
            'active_reps': active_reps,
        }

    @api.model
    def get_map_data(self, employee_id=None, date_str=None):
        """Compiles customer locations and route tracks for route map visualization."""
        from odoo.fields import Date
        
        date_filter = Date.from_string(date_str) if date_str else Date.context_today(self)
        start_dt = date_filter.strftime('%Y-%m-%d 00:00:00')
        end_dt = date_filter.strftime('%Y-%m-%d 23:59:59')

        lead_domain = []
        if employee_id:
            lead_domain.append(('user_id.employee_id', '=', int(employee_id)))

        leads = self.env['sales.visit.lead'].search(lead_domain)
        
        customers_data = []
        for l in leads:
            customers_data.append({
                'name': l.name,
                'lat': l.latitude,
                'lon': l.longitude,
                'status': l.status.upper(),
            })

        visit_domain = [('check_in_time', '>=', start_dt), ('check_in_time', '<=', end_dt)]
        if employee_id:
            visit_domain.append(('employee_id', '=', int(employee_id)))
            
        visits = self.search(visit_domain)
        visits_data = []
        for v in visits:
            visits_data.append({
                'id': v.id,
                'name': v.lead_id.name,
                'salesperson': v.user_id.name,
                'lat': v.check_in_latitude,
                'lon': v.check_in_longitude,
                'status': v.verification_status,
                'outcome': v.result or 'IN PROGRESS',
            })

        route_domain = [('timestamp', '>=', start_dt), ('timestamp', '<=', end_dt)]
        if employee_id:
            route_domain.append(('employee_id', '=', int(employee_id)))
            
        routes = self.env['sales.route.point'].search(route_domain, order='timestamp asc')
        routes_data = []
        for r in routes:
            routes_data.append({
                'lat': r.latitude,
                'lon': r.longitude,
                'time': fields.Datetime.to_string(r.timestamp),
                'employee': r.employee_id.name,
            })

        employees = self.env['hr.employee'].search([])
        employees_list = [{'id': e.id, 'name': e.name} for e in employees]

        return {
            'customers': customers_data,
            'visits': visits_data,
            'routes': routes_data,
            'employees': employees_list,
        }
