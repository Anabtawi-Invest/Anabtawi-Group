# -*- coding: utf-8 -*-

from odoo.tests import common, tagged
from odoo.exceptions import UserError, ValidationError
from odoo import fields


@tagged('post_install', '-at_install', 'sales_visit')
class TestSalesVisitWorkflow(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestSalesVisitWorkflow, cls).setUpClass()
        
        # Create Sales Representative User
        cls.rep_user = cls.env['res.users'].create({
            'name': 'Rep Bob',
            'login': 'bob1',
            'email': 'bob@test.com',
            'groups_id': [(6, 0, [cls.env.ref('sales_visit_tracking.group_sales_representative').id])]
        })
        
        # Create Supervisor User
        cls.supervisor_user = cls.env['res.users'].create({
            'name': 'Sup Alice',
            'login': 'alice1',
            'email': 'alice@test.com',
            'groups_id': [(6, 0, [cls.env.ref('sales_visit_tracking.group_sales_supervisor').id])]
        })
        
        # Create Manager User (to test override of locked coordinates)
        cls.manager_user = cls.env['res.users'].create({
            'name': 'Mgr Charlie',
            'login': 'charlie1',
            'email': 'charlie@test.com',
            'groups_id': [(6, 0, [cls.env.ref('sales_visit_tracking.group_sales_manager').id])]
        })

        # Create Employees and establish hierarchy
        cls.rep_employee = cls.env['hr.employee'].create({
            'name': 'Rep Bob',
            'user_id': cls.rep_user.id
        })
        cls.supervisor_employee = cls.env['hr.employee'].create({
            'name': 'Sup Alice',
            'user_id': cls.supervisor_user.id
        })
        cls.rep_employee.write({'parent_id': cls.supervisor_employee.id})

        # HQ/Target Coordinates: Amman Sweet Shop (31.9522, 35.9106)
        cls.dest_lat = 31.9522
        cls.dest_lon = 35.9106

    def test_01_new_lead_location_capture_and_locking(self):
        """Test that the first check-in saves and locks lead coordinates."""
        # 1. Register a new lead with unknown location (coordinates default to 0.0)
        lead = self.env['sales.visit.lead'].create({
            'name': 'New Sweethaven Bakery',
            'mobile': '0791234567',
            'user_id': self.rep_user.id,
        })
        self.assertEqual(lead.latitude, 0.0)
        self.assertEqual(lead.longitude, 0.0)
        self.assertFalse(lead.is_location_locked)

        # 2. Create visit assignment
        visit = self.env['sales.visit'].create({
            'lead_id': lead.id,
            'user_id': self.rep_user.id,
            'visit_date': fields.Date.today(),
            'state': 'assigned',
        })

        # 3. Check-in (saves current location and locks it)
        visit.action_save_lead_location_and_check_in(self.dest_lat, self.dest_lon)
        self.assertEqual(lead.latitude, self.dest_lat)
        self.assertEqual(lead.longitude, self.dest_lon)
        self.assertTrue(lead.is_location_locked)
        self.assertEqual(visit.state, 'in_progress')
        self.assertEqual(visit.verification_status, 'valid')

        # 4. Attempt to modify locked coordinates by representative (should fail)
        with self.assertRaises(ValidationError):
            lead.with_user(self.rep_user).write({'latitude': 32.0})

        # 5. Modify coordinates by Manager (should succeed)
        lead.with_user(self.manager_user).write({'latitude': 32.0})
        self.assertEqual(lead.latitude, 32.0)

    def test_02_strict_50m_geofencing_rule(self):
        """Test that check-in is strictly validated and blocked if > 50 meters away."""
        # 1. Lead has pre-existing coordinates
        lead = self.env['sales.visit.lead'].create({
            'name': 'Existing Customer',
            'mobile': '0797777777',
            'latitude': self.dest_lat,
            'longitude': self.dest_lon,
            'is_location_locked': True,
            'user_id': self.rep_user.id,
        })

        # 2. Create assignment
        visit = self.env['sales.visit'].create({
            'lead_id': lead.id,
            'user_id': self.rep_user.id,
            'visit_date': fields.Date.today(),
            'state': 'assigned',
        })

        # 3. Check-in 100 meters away (31.9531, 35.9106 -> ~100m) should fail/be blocked
        # 31.9531, 35.9106 is ~100m away from 31.9522, 35.9106
        with self.assertRaises(ValidationError):
            visit.action_check_in(31.9531, 35.9106)

        # Confirm that a blocked check-in audit log was generated
        blocked_log = self.env['sales.visit.audit.log'].search([('event_type', '=', 'blocked_check_in')], limit=1)
        self.assertTrue(blocked_log)
        self.assertIn("attempted to check in", blocked_log.description)

        # 4. Check-in 20 meters away (31.95238, 35.9106 -> ~20m) should succeed
        visit.action_check_in(31.95238, 35.9106)
        self.assertEqual(visit.state, 'in_progress')
        self.assertEqual(visit.verification_status, 'valid')

    def test_03_revisit_scheduling_and_approval_conversion(self):
        """Test lead conversion on approval and automatic visit scheduling on revisit."""
        lead1 = self.env['sales.visit.lead'].create({
            'name': 'Convert Shop',
            'mobile': '0791111111',
            'latitude': self.dest_lat,
            'longitude': self.dest_lon,
            'is_location_locked': True,
            'user_id': self.rep_user.id,
        })
        visit1 = self.env['sales.visit'].create({
            'lead_id': lead1.id,
            'user_id': self.rep_user.id,
            'visit_date': fields.Date.today(),
            'state': 'assigned',
        })
        visit1.action_check_in(self.dest_lat, self.dest_lon)

        # Approve and convert
        visit1.action_end_visit(self.dest_lat, self.dest_lon, 'approved')
        self.assertEqual(visit1.state, 'completed')
        self.assertEqual(lead1.status, 'approved')
        self.assertTrue(lead1.partner_id)
        self.assertEqual(lead1.partner_id.name, 'Convert Shop')

        # Test Revisit outcome schedules new visit
        partner = lead1.partner_id
        visit2 = self.env['sales.visit'].create({
            'partner_id': partner.id,
            'user_id': self.rep_user.id,
            'visit_date': fields.Date.today(),
            'state': 'assigned',
        })
        visit2.action_check_in(self.dest_lat, self.dest_lon)

        next_date = fields.Date.from_string('2026-06-30')
        visit2.action_end_visit(self.dest_lat, self.dest_lon, 'revisit', next_visit_date=next_date)
        
        # A new visit should have been automatically created for that date
        new_visit = self.env['sales.visit'].search([
            ('partner_id', '=', partner.id),
            ('visit_date', '=', next_date),
            ('state', '=', 'assigned')
        ])
        self.assertTrue(new_visit)

    def test_04_audit_log_immutability(self):
        """Test that audit log records are immutable and cannot be updated or deleted."""
        log = self.env['sales.visit.audit.log'].create({
            'name': 'Test Event',
            'event_type': 'system',
            'description': 'Test Description',
        })

        # Try to modify (should throw UserError)
        with self.assertRaises(UserError):
            log.write({'description': 'New Description'})

        # Try to delete (should throw UserError)
        with self.assertRaises(UserError):
            log.unlink()

    def test_05_manager_dashboard_and_coverage(self):
        """Test manager KPI calculations and coverage lists."""
        lead = self.env['sales.visit.lead'].create({
            'name': 'Bakery Test',
            'mobile': '0798888888',
            'latitude': self.dest_lat,
            'longitude': self.dest_lon,
            'is_location_locked': True,
            'user_id': self.rep_user.id,
        })
        visit = self.env['sales.visit'].create({
            'lead_id': lead.id,
            'user_id': self.rep_user.id,
            'visit_date': fields.Date.today(),
            'state': 'assigned',
        })
        
        # Test GPS Compliance calculations: 1 blocked, 1 successful
        with self.assertRaises(ValidationError):
            visit.action_check_in(32.1, 35.9) # blocked

        visit.action_check_in(self.dest_lat, self.dest_lon) # successful
        visit.action_end_visit(self.dest_lat, self.dest_lon, 'approved')

        data = self.env['sales.visit'].get_dashboard_data()
        self.assertEqual(data['assignments']['completed'], 1)
        self.assertEqual(data['performance']['approved_leads'], 1)
        self.assertEqual(data['performance']['gps_compliance'], 50.0)

    def test_06_assignment_type_inference(self):
        """Test that assignment_type is correctly inferred on creation."""
        lead = self.env['sales.visit.lead'].create({
            'name': 'Test Lead Inf',
            'mobile': '0790000000',
            'user_id': self.rep_user.id,
        })
        
        # Create with lead
        visit_lead = self.env['sales.visit'].create({
            'lead_id': lead.id,
            'user_id': self.rep_user.id,
            'visit_date': fields.Date.today(),
        })
        self.assertEqual(visit_lead.assignment_type, 'lead')

        # Create with partner
        partner = self.env['res.partner'].create({
            'name': 'Test Partner Inf',
            'user_id': self.rep_user.id,
        })
        visit_customer = self.env['sales.visit'].create({
            'partner_id': partner.id,
            'user_id': self.rep_user.id,
            'visit_date': fields.Date.today(),
        })
        self.assertEqual(visit_customer.assignment_type, 'customer')

