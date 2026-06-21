# -*- coding: utf-8 -*-

import logging
import math
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class SalesVisit(models.Model):
    _name = 'sales.visit'
    _description = 'Salesperson Customer Visit'
    _order = 'visit_date desc, check_in_time desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

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
        ondelete='cascade',
        index=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        ondelete='cascade',
        index=True
    )
    user_id = fields.Many2one(
        'res.users',
        string='Salesperson',
        required=True,
        default=lambda self: self.env.user,
        index=True,
        tracking=True
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Salesperson Employee',
        compute='_compute_employee_id',
        store=True,
        index=True
    )
    visit_date = fields.Date(
        string='Visit Date',
        required=True,
        default=fields.Date.today,
        tracking=True
    )
    state = fields.Selection([
        ('assigned', 'Assigned'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('missed', 'Missed')
    ], string='Status', default='assigned', required=True, tracking=True)

    customer_type = fields.Selection([
        ('lead', 'New Lead'),
        ('revisit', 'Revisit Lead'),
        ('customer', 'Customer')
    ], string='Customer Type', compute='_compute_customer_type', store=True)

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
        string='Distance from Customer (m)',
        readonly=True
    )
    verification_status = fields.Selection([
        ('valid', 'Valid Visit (<= 50m)'),
        ('invalid', 'Invalid Visit (> 50m)'),
    ], string='GPS Validation', readonly=True)

    duration = fields.Float(
        string='Duration (Hours)',
        compute='_compute_duration',
        store=True,
        readonly=True
    )
    result = fields.Selection([
        ('approved', 'Approved / Converted'),
        ('revisit', 'Revisit Scheduled'),
        ('rejected', 'Rejected'),
        ('order', 'Order Generated'),
        ('issue', 'Issue Reported')
    ], string='Outcome', readonly=True)

    rejection_reason = fields.Selection([
        ('price', 'Price'),
        ('competitor', 'Competitor'),
        ('not_interested', 'Not Interested'),
        ('no_budget', 'No Budget'),
        ('other', 'Other'),
    ], string='Rejection Reason', readonly=True)

    next_visit_date = fields.Date(
        string='Next Visit Date',
        readonly=True
    )
    customer_issue = fields.Text(
        string='Customer Issue Description',
        readonly=True
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Generated Sales Order',
        compute='_compute_sale_order_id',
        store=True,
        readonly=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )

    @api.depends('partner_id')
    def _compute_sale_order_id(self):
        for visit in self:
            order = self.env['sale.order'].search([('visit_id', '=', visit.id)], limit=1)
            visit.sale_order_id = order.id if order else False


    @api.depends('user_id')
    def _compute_employee_id(self):
        for visit in self:
            if visit.user_id:
                visit.employee_id = self.env['hr.employee'].search(
                    [('user_id', '=', visit.user_id.id)], limit=1
                )
            else:
                visit.employee_id = False

    @api.depends('lead_id', 'lead_id.status', 'partner_id')
    def _compute_customer_type(self):
        for visit in self:
            if visit.lead_id:
                if visit.lead_id.status == 'revisit':
                    visit.customer_type = 'revisit'
                else:
                    visit.customer_type = 'lead'
            elif visit.partner_id:
                visit.customer_type = 'customer'
            else:
                visit.customer_type = 'lead'

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
        return super(SalesVisit, self).create(vals_list)

    def write(self, vals):
        if 'user_id' in vals or 'visit_date' in vals:
            for record in self:
                old_user = record.user_id.name or _("Unassigned")
                new_user = self.env['res.users'].browse(vals['user_id']).name if 'user_id' in vals else old_user
                old_date = record.visit_date
                new_date = vals.get('visit_date', old_date)
                target_name = record.lead_id.name if record.lead_id else (record.partner_id.name or record.name)
                
                self.env['sales.visit.audit.log'].create({
                    'name': _("Visit Assignment Modified"),
                    'event_type': 'assignment_change',
                    'description': _("Visit assignment for customer '%s' was updated by %s.\nUser: %s -> %s\nDate: %s -> %s") % (
                        target_name, self.env.user.name, old_user, new_user, old_date, new_date
                    )
                })
        return super(SalesVisit, self).write(vals)

    @staticmethod
    def haversine_distance(lat1, lon1, lat2, lon2):
        R = 6371000.0
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lambda = math.radians(lon2 - lon1)
        a = (
            math.sin(d_phi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return R * c

    def action_save_lead_location_and_check_in(self, latitude, longitude):
        self.ensure_one()
        if self.state != 'assigned':
            raise UserError(_("Visit is not in Assigned state."))
        if not self.lead_id:
            raise UserError(_("No lead associated with this visit."))
        
        # Save and lock coordinates on lead
        self.lead_id.write({
            'latitude': latitude,
            'longitude': longitude,
            'is_location_locked': True
        })

        # Set check-in details
        check_in_time = fields.Datetime.now()
        self.write({
            'check_in_time': check_in_time,
            'check_in_latitude': latitude,
            'check_in_longitude': longitude,
            'distance_from_customer': 0.0,
            'verification_status': 'valid',
            'state': 'in_progress'
        })

        # Log audit log
        self.env['sales.visit.audit.log'].create({
            'name': _("Lead Location Saved & Checked In"),
            'event_type': 'check_in',
            'latitude': latitude,
            'longitude': longitude,
            'description': _("Representative %s saved location for Lead '%s' at (%s, %s) and automatically checked in.") % (
                self.user_id.name, self.lead_id.name, latitude, longitude
            )
        })

        # Create route point
        if self.employee_id:
            self.env['sales.route.point'].create({
                'employee_id': self.employee_id.id,
                'visit_id': self.id,
                'timestamp': check_in_time,
                'latitude': latitude,
                'longitude': longitude,
                'speed': 0.0,
                'heading': 0.0,
            })
        return True

    def action_check_in(self, latitude, longitude):
        self.ensure_one()
        if self.state != 'assigned':
            raise UserError(_("Visit is not in Assigned state."))
        
        # Get target coordinates
        target_lat = 0.0
        target_lon = 0.0
        target_name = ""
        if self.lead_id:
            target_lat = self.lead_id.latitude
            target_lon = self.lead_id.longitude
            target_name = self.lead_id.name
        elif self.partner_id:
            target_lat = self.partner_id.latitude
            target_lon = self.partner_id.longitude
            target_name = self.partner_id.name
        else:
            raise UserError(_("No customer or lead associated with this visit."))

        # Compute distance
        distance = self.haversine_distance(latitude, longitude, target_lat, target_lon)

        # 50 meter check-in validation
        if distance > 50.0:
            # Log blocked check-in attempt
            self.env['sales.visit.audit.log'].create({
                'name': _("Check-In Blocked (Out of Bounds)"),
                'event_type': 'blocked_check_in',
                'latitude': latitude,
                'longitude': longitude,
                'description': _("Representative %s attempted to check in for '%s' from %s meters away (limit: 50m). Check-in was blocked.") % (
                    self.user_id.name, target_name, round(distance, 1)
                )
            })
            raise ValidationError(_("Check-in blocked. You must be within 50 meters of the customer location (current distance: %sm).") % round(distance, 1))

        # Check-in succeeds
        check_in_time = fields.Datetime.now()
        self.write({
            'check_in_time': check_in_time,
            'check_in_latitude': latitude,
            'check_in_longitude': longitude,
            'distance_from_customer': distance,
            'verification_status': 'valid',
            'state': 'in_progress'
        })

        # Log audit log
        self.env['sales.visit.audit.log'].create({
            'name': _("Check-In Successful"),
            'event_type': 'check_in',
            'latitude': latitude,
            'longitude': longitude,
            'description': _("Representative %s checked in for '%s' at (%s, %s) (distance: %sm).") % (
                self.user_id.name, target_name, latitude, longitude, round(distance, 1)
            )
        })

        # Create route point
        if self.employee_id:
            self.env['sales.route.point'].create({
                'employee_id': self.employee_id.id,
                'visit_id': self.id,
                'timestamp': check_in_time,
                'latitude': latitude,
                'longitude': longitude,
                'speed': 0.0,
                'heading': 0.0,
            })
        return True

    def action_end_visit(self, latitude, longitude, result,
                          next_visit_date=None, rejection_reason=None, customer_issue=None, sale_order_id=None):
        self.ensure_one()
        if self.state != 'in_progress':
            raise UserError(_("Visit is not in Progress."))
        
        if result == 'revisit' and not next_visit_date:
            raise ValidationError(_("Next visit date is required for a Revisit."))
        if result == 'rejected' and not rejection_reason:
            raise ValidationError(_("Rejection reason is required for a Rejection."))
        if result == 'issue' and not customer_issue:
            raise ValidationError(_("Issue description is required for an Issue outcome."))

        check_out_time = fields.Datetime.now()
        self.write({
            'check_out_time': check_out_time,
            'check_out_latitude': latitude,
            'check_out_longitude': longitude,
            'result': result,
            'next_visit_date': next_visit_date,
            'rejection_reason': rejection_reason,
            'customer_issue': customer_issue,
            'sale_order_id': sale_order_id,
            'state': 'completed'
        })

        # Log audit log
        target_name = self.lead_id.name if self.lead_id else (self.partner_id.name or self.name)
        self.env['sales.visit.audit.log'].create({
            'name': _("Check-Out Successful"),
            'event_type': 'check_out',
            'latitude': latitude,
            'longitude': longitude,
            'description': _("Representative %s checked out for '%s' with result '%s'.") % (
                self.user_id.name, target_name, result
            )
        })

        # Log visit result audit log
        self.env['sales.visit.audit.log'].create({
            'name': _("Visit Outcome Logged"),
            'event_type': 'visit_result',
            'description': _("Outcome logged for '%s': Result=%s, Next Visit Date=%s, Rejection Reason=%s, Issue=%s") % (
                target_name, result, next_visit_date, rejection_reason, customer_issue
            )
        })

        # Handle outcomes:
        if self.customer_type in ['lead', 'revisit']:
            # New Lead options: revisit, approved, rejected
            if result == 'revisit':
                self.lead_id.write({'status': 'revisit', 'next_visit_date': next_visit_date})
            elif result == 'approved':
                partner = self.lead_id.action_convert_to_customer()
                if partner:
                    self.write({'partner_id': partner.id})
            elif result == 'rejected':
                self.lead_id.write({'status': 'rejected', 'rejection_reason': rejection_reason})
        else:
            # Customer options: order, revisit, issue
            if result == 'revisit':
                # Create a new scheduled visit automatically for the next_visit_date
                self.create({
                    'partner_id': self.partner_id.id,
                    'user_id': self.user_id.id,
                    'visit_date': next_visit_date,
                    'state': 'assigned'
                })
            elif result == 'issue':
                # Post message in chatter to alert managers
                manager_group = self.env.ref('sales_visit_tracking.group_sales_manager')
                manager_users = manager_group.users if manager_group else []
                body = _("<h3>Customer Issue Reported</h3><p><b>Customer:</b> %s</p><p><b>Salesperson:</b> %s</p><p><b>Details:</b> %s</p>") % (
                    self.partner_id.name, self.user_id.name, customer_issue
                )
                self.message_post(body=body, partner_ids=manager_users.mapped('partner_id.id'))

        # Create route point
        if self.employee_id:
            self.env['sales.route.point'].create({
                'employee_id': self.employee_id.id,
                'visit_id': self.id,
                'timestamp': check_out_time,
                'latitude': latitude,
                'longitude': longitude,
                'speed': 0.0,
                'heading': 0.0,
            })

        return True

    @api.model
    def cron_mark_missed_visits(self):
        """Marks past visits as missed if they were not completed."""
        today = fields.Date.today()
        missed_visits = self.search([
            ('visit_date', '<', today),
            ('state', 'in', ['assigned', 'in_progress'])
        ])
        if missed_visits:
            missed_visits.write({'state': 'missed'})
            for visit in missed_visits:
                self.env['sales.visit.audit.log'].create({
                    'name': _("Visit Marked Missed Automatically"),
                    'event_type': 'system',
                    'description': _("Visit for '%s' scheduled on %s was automatically marked Missed by the system.") % (
                        visit.lead_id.name if visit.lead_id else (visit.partner_id.name or visit.name),
                        visit.visit_date
                    )
                })

    @api.model
    def get_my_visits_for_mobile(self):
        """Returns simplified list of today's assigned/in-progress visits for mobile app."""
        today = fields.Date.today()
        visits = self.search([
            ('user_id', '=', self.env.user.id),
            ('visit_date', '=', today),
            ('state', 'in', ['assigned', 'in_progress'])
        ])
        
        result = []
        for v in visits:
            name = ""
            mobile = ""
            lat = 0.0
            lon = 0.0
            
            if v.customer_type == 'customer' and v.partner_id:
                name = v.partner_id.name
                mobile = v.partner_id.mobile or v.partner_id.phone or ""
                lat = v.partner_id.latitude
                lon = v.partner_id.longitude
            elif v.lead_id:
                name = v.lead_id.name
                mobile = v.lead_id.mobile or ""
                lat = v.lead_id.latitude
                lon = v.lead_id.longitude
                
            result.append({
                'id': v.id,
                'name': name,
                'customer_type': v.customer_type,
                'mobile': mobile,
                'lat': lat,
                'lon': lon,
                'visit_date': fields.Date.to_string(v.visit_date),
                'state': v.state,
                'partner_id': v.partner_id.id if v.partner_id else False,
                'lead_id': v.lead_id.id if v.lead_id else False,
            })
        return result


    @api.model
    def get_dashboard_data(self):
        today = fields.Date.context_today(self)
        
        # 1. Assignments count
        assigned = self.search_count([('state', '=', 'assigned'), ('visit_date', '=', today)])
        pending = self.search_count([('state', '=', 'in_progress'), ('visit_date', '=', today)])
        completed = self.search_count([('state', '=', 'completed'), ('visit_date', '=', today)])
        missed = self.search_count([('state', '=', 'missed')])
        
        # 2. Performance KPIs
        total_assigned = self.search_count([])
        total_completed = self.search_count([('state', '=', 'completed')])
        
        new_leads_visited = self.search_count([('customer_type', '=', 'lead'), ('state', '=', 'completed')])
        approved_leads = self.search_count([('customer_type', '=', 'lead'), ('result', '=', 'approved')])
        rejected_leads = self.search_count([('customer_type', '=', 'lead'), ('result', '=', 'rejected')])
        revisit_leads = self.search_count([('customer_type', '=', 'revisit'), ('state', '=', 'completed')])
        customer_visits = self.search_count([('customer_type', '=', 'customer'), ('state', '=', 'completed')])
        
        orders_count = self.search_count([('sale_order_id', '!=', False)])
        revenue = sum(self.search([('sale_order_id', '!=', False)]).mapped('sale_order_id.amount_total'))
        
        conversion_rate = (approved_leads / new_leads_visited * 100.0) if new_leads_visited else 0.0
        
        # GPS Compliance
        successful_checkins = self.env['sales.visit.audit.log'].search_count([('event_type', '=', 'check_in')])
        blocked_attempts = self.env['sales.visit.audit.log'].search_count([('event_type', '=', 'blocked_check_in')])
        total_attempts = successful_checkins + blocked_attempts
        gps_compliance = (successful_checkins / total_attempts * 100.0) if total_attempts else 100.0
        
        # 3. Customer Coverage
        # Query active standard Odoo Contacts (excluding companies)
        partners = self.env['res.partner'].search([('active', '=', True), ('is_company', '=', False)])
        
        cov_30 = []
        cov_60 = []
        cov_90 = []
        
        for partner in partners:
            last_visit = self.search([('partner_id', '=', partner.id), ('state', '=', 'completed')], order='check_in_time desc', limit=1)
            if last_visit and last_visit.check_in_time:
                days_since = (fields.Date.today() - last_visit.check_in_time.date()).days
                last_visit_date = fields.Date.to_string(last_visit.check_in_time.date())
            else:
                days_since = 999
                last_visit_date = _("Never")
                
            partner_info = {
                'id': partner.id,
                'name': partner.name,
                'salesperson': partner.user_id.name or _("Unassigned"),
                'last_visit_date': last_visit_date,
                'days_since': days_since
            }
            
            if days_since >= 90:
                cov_90.append(partner_info)
            elif days_since >= 60:
                cov_60.append(partner_info)
            elif days_since >= 30:
                cov_30.append(partner_info)
                
        # 4. Revisit Schedule
        revisits = self.search([('state', '=', 'assigned'), ('visit_date', '>=', today)], order='visit_date asc')
        revisit_schedule = [
            {
                'id': r.id,
                'customer': r.lead_id.name if r.lead_id else (r.partner_id.name or r.name),
                'salesperson': r.user_id.name,
                'date': fields.Date.to_string(r.visit_date),
            }
            for r in revisits
        ]

        return {
            'assignments': {
                'assigned': assigned,
                'pending': pending,
                'completed': completed,
                'missed': missed,
                'revisit_schedule': revisit_schedule,
            },
            'performance': {
                'assigned_visits': total_assigned,
                'completed_visits': total_completed,
                'new_leads_visited': new_leads_visited,
                'approved_leads': approved_leads,
                'rejected_leads': rejected_leads,
                'revisit_leads': revisit_leads,
                'customer_visits': customer_visits,
                'orders_generated': orders_count,
                'revenue_generated': round(revenue, 2),
                'conversion_rate': round(conversion_rate, 1),
                'gps_compliance': round(gps_compliance, 1),
                'active_reps': len(self.search([('visit_date', '=', today)]).mapped('user_id')),
            },
            'coverage': {
                'not_visited_30': cov_30,
                'not_visited_60': cov_60,
                'not_visited_90': cov_90,
            }
        }

    @api.model
    def get_map_data(self, employee_id=None, date_str=None):
        from odoo.fields import Date

        date_filter = Date.from_string(date_str) if date_str else Date.context_today(self)
        start_dt = date_filter.strftime('%Y-%m-%d 00:00:00')
        end_dt = date_filter.strftime('%Y-%m-%d 23:59:59')

        partners = self.env['res.partner'].search([('latitude', '!=', 0.0), ('longitude', '!=', 0.0)])
        customers_data = [
            {
                'name': p.name,
                'lat': p.latitude,
                'lon': p.longitude,
                'status': 'CUSTOMER',
            }
            for p in partners
        ]

        leads = self.env['sales.visit.lead'].search([('status', 'in', ['lead', 'revisit']), ('latitude', '!=', 0.0), ('longitude', '!=', 0.0)])
        leads_data = [
            {
                'name': l.name,
                'lat': l.latitude,
                'lon': l.longitude,
                'status': l.status.upper(),
            }
            for l in leads
        ]

        visit_domain = [
            ('check_in_time', '>=', start_dt),
            ('check_in_time', '<=', end_dt),
        ]
        if employee_id:
            visit_domain.append(('employee_id', '=', int(employee_id)))

        visits = self.search(visit_domain)
        visits_data = [
            {
                'id': v.id,
                'name': v.lead_id.name if v.lead_id else (v.partner_id.name or v.name),
                'customer': v.lead_id.name if v.lead_id else (v.partner_id.name or v.name),
                'salesperson': v.user_id.name,
                'lat': v.check_in_latitude,
                'lon': v.check_in_longitude,
                'status': v.verification_status,
                'outcome': v.result or 'IN PROGRESS',
            }
            for v in visits
        ]

        route_domain = [
            ('timestamp', '>=', start_dt),
            ('timestamp', '<=', end_dt),
        ]
        if employee_id:
            route_domain.append(('employee_id', '=', int(employee_id)))

        routes = self.env['sales.route.point'].search(route_domain, order='timestamp asc')
        routes_data = [
            {
                'lat': r.latitude,
                'lon': r.longitude,
                'time': fields.Datetime.to_string(r.timestamp),
                'employee': r.employee_id.name,
                'speed': r.speed,
            }
            for r in routes
        ]

        employees = self.env['hr.employee'].search([])
        rep_locations = []
        for emp in employees:
            latest_point = self.env['sales.route.point'].search([
                ('employee_id', '=', emp.id),
                ('timestamp', '>=', start_dt),
                ('timestamp', '<=', end_dt),
            ], order='timestamp desc', limit=1)
            if latest_point:
                rep_locations.append({
                    'name': emp.name,
                    'lat': latest_point.latitude,
                    'lon': latest_point.longitude,
                    'time': fields.Datetime.to_string(latest_point.timestamp),
                })

        return {
            'customers': customers_data + leads_data,
            'visits': visits_data,
            'routes': routes_data,
            'reps': rep_locations,
            'employees': [{'id': e.id, 'name': e.name} for e in employees],
        }
