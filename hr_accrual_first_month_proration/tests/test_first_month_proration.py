# -*- coding: utf-8 -*-
from datetime import date

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFirstMonthProration(TransactionCase):

    def test_factor(self):
        f = self.env['hr.leave.allocation']._first_month_factor
        self.assertAlmostEqual(round(1.17 * f(date(2026, 8, 18)), 4), 0.5284, places=4)
        # 18-30 Sep = 13 of 30 days (the 0.4550 in the spec is an arithmetic slip)
        self.assertAlmostEqual(round(1.17 * f(date(2026, 9, 18)), 4), 0.5070, places=4)
        self.assertAlmostEqual(f(date(2026, 8, 1)), 1.0)
        self.assertAlmostEqual(f(date(2026, 8, 31)), 1 / 31)
        self.assertAlmostEqual(f(date(2028, 2, 15)), 15 / 29)  # leap year

    def test_due_only_when_enabled_and_once(self):
        plan = self.env['hr.leave.accrual.plan'].create({
            'name': 'Test plan',
            'accrued_gain_time': 'end',
            'level_ids': [(0, 0, {
                'start_count': 0,
                'added_value': 1.17,
                'added_value_type': 'day',
                'frequency': 'monthly',
                'cap_accrued_time_yearly': True,
                'maximum_leave_yearly': 14,
            })],
        })
        level = plan.level_ids[0]
        alloc = self.env['hr.leave.allocation'].new({
            'accrual_plan_id': plan.id,
            'date_from': date(2026, 8, 18),
        })
        start, end = date(2026, 7, 30), date(2026, 8, 30)
        self.assertFalse(alloc._is_first_month_proration_due(level, start, end))  # opt-in off
        plan.prorate_first_month = True
        self.assertTrue(alloc._is_first_month_proration_due(level, start, end))
        alloc.first_month_prorated = True
        self.assertFalse(alloc._is_first_month_proration_due(level, start, end))  # once only

    def test_last_month_factor(self):
        plan = self.env['hr.leave.accrual.plan'].create({
            'name': 'Test plan', 'prorate_last_month': True,
            'level_ids': [(0, 0, {
                'start_count': 0, 'added_value': 1.17,
                'added_value_type': 'day', 'frequency': 'monthly',
            })],
        })
        level = plan.level_ids[0]
        alloc = self.env['hr.leave.allocation'].new({
            'accrual_plan_id': plan.id, 'date_from': date(2025, 1, 1),
        })
        alloc._get_contract_end_date = lambda: date(2026, 8, 18)
        # August (1 Aug -> 1 Sep): 18 of 31 days
        factor, first = alloc._get_accrual_proration(level, date(2026, 8, 1), date(2026, 9, 1))
        self.assertAlmostEqual(round(1.17 * factor, 4), 0.6794, places=4)
        self.assertFalse(first)
        # September: nothing
        factor, _first = alloc._get_accrual_proration(level, date(2026, 9, 1), date(2026, 10, 1))
        self.assertEqual(factor, 0.0)
        # July: standard
        self.assertIsNone(alloc._get_accrual_proration(level, date(2026, 7, 1), date(2026, 8, 1)))
