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

        # Lead destination: Amman Sweet Shop (31.9522, 35.9106)
        cls.dest_lat = 31.9522
        cls.dest_lon = 35.9106

    def test_01_lead_creation_and_geofence(self):
        """Test lead registration, start visit distance and geofence mapping."""
        # 1. Register a simplified lead
        lead = self.env['sales.visit.lead'].create({
            'name': 'Sweethaven Bakery',
            'mobile': '0791234567',
            'latitude': self.dest_lat,
            'longitude': self.dest_lon,
            'user_id': self.rep_user.id,
        })
        self.assertEqual(lead.status, 'lead')
        
        # 2. Check-in exactly at destination (0m distance -> valid)
        visit_id = self.env['sales.visit'].action_start_visit(lead.id, self.dest_lat, self.dest_lon)
        visit = self.env['sales.visit'].browse(visit_id)
        self.assertEqual(visit.verification_status, 'valid')
        self.assertLessEqual(visit.distance_from_customer, 1.0)
        
        # 3. Check-in 150m away (31.9535, 35.9106 -> warning)
        visit2_id = self.env['sales.visit'].action_start_visit(lead.id, 31.9535, 35.9106)
        visit2 = self.env['sales.visit'].browse(visit2_id)
        self.assertEqual(visit2.verification_status, 'warning')
        
        # 4. Check-in 10km away (32.05, 35.91 -> invalid)
        visit3_id = self.env['sales.visit'].action_start_visit(lead.id, 32.05, 35.91)
        visit3 = self.env['sales.visit'].browse(visit3_id)
        self.assertEqual(visit3.verification_status, 'invalid')

    def test_02_revisit_workflow(self):
        """Test transitioning lead to Revisit status."""
        lead = self.env['sales.visit.lead'].create({
            'name': 'Future Sweets',
            'mobile': '0799876543',
            'latitude': self.dest_lat,
            'longitude': self.dest_lon,
            'user_id': self.rep_user.id,
        })
        
        # Start visit
        visit_id = self.env['sales.visit'].action_start_visit(lead.id, self.dest_lat, self.dest_lon)
        visit = self.env['sales.visit'].browse(visit_id)
        
        # End visit as Revisit
        next_date = fields.Date.from_string('2026-06-25')
        visit.action_end_visit(self.dest_lat, self.dest_lon, 'revisit', next_visit_date=next_date)
        
        self.assertEqual(visit.result, 'revisit')
        self.assertEqual(lead.status, 'revisit')
        self.assertEqual(lead.next_visit_date, next_date)

    def test_03_approved_workflow_conversion(self):
        """Test Approved result automatically converting lead to Contact (res.partner)."""
        lead = self.env['sales.visit.lead'].create({
            'name': 'Golden Kunafa',
            'mobile': '0792223334',
            'latitude': self.dest_lat,
            'longitude': self.dest_lon,
            'user_id': self.rep_user.id,
        })
        
        # Start visit
        visit_id = self.env['sales.visit'].action_start_visit(lead.id, self.dest_lat, self.dest_lon)
        visit = self.env['sales.visit'].browse(visit_id)
        
        # End visit as Approved
        visit.action_end_visit(self.dest_lat, self.dest_lon, 'approved')
        
        self.assertEqual(visit.result, 'approved')
        self.assertEqual(lead.status, 'approved')
        self.assertTrue(lead.partner_id, "Standard partner contact should have been created.")
        self.assertEqual(lead.partner_id.name, 'Golden Kunafa')
        self.assertEqual(lead.partner_id.mobile, '0792223334')
        self.assertEqual(lead.partner_id.latitude, self.dest_lat)
        self.assertEqual(lead.partner_id.longitude, self.dest_lon)

    def test_04_rejected_workflow(self):
        """Test Rejected result updates lead status and reasons."""
        lead = self.env['sales.visit.lead'].create({
            'name': 'No sugar Inc',
            'mobile': '0794445556',
            'latitude': self.dest_lat,
            'longitude': self.dest_lon,
            'user_id': self.rep_user.id,
        })
        
        # Start visit
        visit_id = self.env['sales.visit'].action_start_visit(lead.id, self.dest_lat, self.dest_lon)
        visit = self.env['sales.visit'].browse(visit_id)
        
        # End visit as Rejected
        visit.action_end_visit(self.dest_lat, self.dest_lon, 'rejected', rejection_reason='price')
        
        self.assertEqual(visit.result, 'rejected')
        self.assertEqual(visit.rejection_reason, 'price')
        self.assertEqual(lead.status, 'rejected')
        self.assertEqual(lead.rejection_reason, 'price')

    def test_05_record_rules(self):
        """Test record visibility rules between rep and supervisor."""
        # Create lead for Rep Bob
        rep_lead = self.env['sales.visit.lead'].create({
            'name': 'Bobs Lead',
            'mobile': '0795556667',
            'latitude': self.dest_lat,
            'longitude': self.dest_lon,
            'user_id': self.rep_user.id,
        })
        
        # Create lead for Supervisor Alice
        sup_lead = self.env['sales.visit.lead'].create({
            'name': 'Alices Lead',
            'mobile': '0797778889',
            'latitude': self.dest_lat,
            'longitude': self.dest_lon,
            'user_id': self.supervisor_user.id,
        })
        
        # Rep Bob searches leads
        rep_search = self.env['sales.visit.lead'].with_user(self.rep_user).search([])
        self.assertIn(rep_lead, rep_search)
        self.assertNotIn(sup_lead, rep_search)
        
        # Supervisor Alice searches leads (subordinate rules)
        sup_search = self.env['sales.visit.lead'].with_user(self.supervisor_user).search([])
        self.assertIn(sup_lead, sup_search)
        self.assertIn(rep_lead, sup_search)

    def test_06_dashboard_calculations(self):
        """Test managers dashboard KPI statistics generation."""
        lead = self.env['sales.visit.lead'].create({
            'name': 'Dashboard Customer',
            'mobile': '0791112223',
            'latitude': self.dest_lat,
            'longitude': self.dest_lon,
            'user_id': self.rep_user.id,
        })
        
        # Start visit (valid)
        visit_id = self.env['sales.visit'].action_start_visit(lead.id, self.dest_lat, self.dest_lon)
        visit = self.env['sales.visit'].browse(visit_id)
        
        # End visit
        visit.action_end_visit(self.dest_lat, self.dest_lon, 'approved')
        
        # Generate stats
        kpis = self.env['sales.visit'].get_dashboard_data()
        self.assertEqual(kpis['today_visits'], 1)
        self.assertEqual(kpis['completed_visits'], 1)
        self.assertEqual(kpis['approved_count'], 1)
        self.assertEqual(kpis['gps_compliance'], 100.0)
