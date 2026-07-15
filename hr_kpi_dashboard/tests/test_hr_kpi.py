from datetime import date
from odoo.tests.common import TransactionCase
from odoo.fields import Date


class TestHrKpi(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Clean up any existing categories/definitions created during data load
        # to ensure a pristine test sandbox, or just use what exists.
        cls.category = cls.env['anabtawi.hr.kpi.category'].create({
            'name': 'Test Category',
            'code': 'TEST_CAT',
            'sequence': 1,
        })
        
        cls.def_headcount = cls.env['anabtawi.hr.kpi.definition'].create({
            'name': 'Employee Count',
            'code': 'WORKFORCE_HEADCOUNT',
            'category_id': cls.category.id,
            'unit': 'number',
        })
        
        cls.def_mobility = cls.env['anabtawi.hr.kpi.definition'].create({
            'name': 'Internal Mobility Rate',
            'code': 'INTERNAL_MOBILITY_RATE',
            'category_id': cls.category.id,
            'unit': 'percent',
        })

        # Create test company
        cls.company = cls.env['res.company'].create({'name': 'Test Company'})

        # Create employees
        cls.employee_1 = cls.env['hr.employee'].create({
            'name': 'Employee One',
            'company_id': cls.company.id,
            'active': True,
        })
        cls.employee_2 = cls.env['hr.employee'].create({
            'name': 'Employee Two',
            'company_id': cls.company.id,
            'active': True,
            'parent_id': cls.employee_1.id, # 1 report for employee_1
        })

    def test_kpi_computation(self):
        # Create reporting period
        period = self.env['anabtawi.hr.kpi.period'].create({
            'name': 'Q1 2026',
            'date_from': date(2026, 1, 1),
            'date_to': date(2026, 3, 31),
            'company_id': self.company.id,
        })

        # Calculate KPIs
        period.action_compute()

        # Verify headcount snapshot
        snapshot_headcount = self.env['anabtawi.hr.kpi.snapshot'].search([
            ('period_id', '=', period.id),
            ('definition_id', '=', self.def_headcount.id),
        ])
        self.assertTrue(snapshot_headcount, "Headcount snapshot should be created")
        self.assertEqual(snapshot_headcount.value, 2.0, "Headcount should equal active employees (2)")

    def test_internal_mobility_with_contracts(self):
        if 'hr.contract' not in self.env:
            # Skip if contract module is not installed
            return

        # Create active contracts
        # Contract 1 (Old)
        contract_old = self.env['hr.contract'].create({
            'name': 'Old Contract Emp 2',
            'employee_id': self.employee_2.id,
            'date_start': date(2025, 1, 1),
            'date_end': date(2025, 12, 31),
            'wage': 2000,
            'company_id': self.company.id,
        })
        # Contract 2 (New, starting in period - simulates promotion/mobility)
        contract_new = self.env['hr.contract'].create({
            'name': 'New Contract Emp 2',
            'employee_id': self.employee_2.id,
            'date_start': date(2026, 2, 1),
            'wage': 2500,
            'company_id': self.company.id,
        })

        # Create reporting period
        period = self.env['anabtawi.hr.kpi.period'].create({
            'name': 'Q1 2026',
            'date_from': date(2026, 1, 1),
            'date_to': date(2026, 3, 31),
            'company_id': self.company.id,
        })

        # Calculate KPIs
        period.action_compute()

        # Verify internal mobility rate: 1 moved / 2 headcount = 50.0%
        snapshot_mobility = self.env['anabtawi.hr.kpi.snapshot'].search([
            ('period_id', '=', period.id),
            ('definition_id', '=', self.def_mobility.id),
        ])
        self.assertTrue(snapshot_mobility, "Mobility snapshot should be created")
        self.assertEqual(snapshot_mobility.value, 50.0, "Mobility rate should be 50.0%")
