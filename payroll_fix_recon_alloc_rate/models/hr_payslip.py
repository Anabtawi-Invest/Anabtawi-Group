# -*- coding: utf-8 -*-
"""Multiply remaining balances before Time Off allocation.

    Remaining Extra Hours Balance  -> x 1.25 (OT_RATE)
    Remaining Paid Time Off Available -> x 1.5 (PH_RATE)

Does not change payslip compute / draft / cancel. Only the hours passed into
`_pfr_force_leave_balance` on confirm (and the in-place bulk repair).
"""
import logging

from odoo import models

from odoo.addons.payroll_fix_recon.models import pfr_utils as U
from odoo.addons.payroll_fix_recon.models.pfr_settlement import (
    leave_hours,
    pto_recon_alloc_name,
    recon_alloc_name,
)

_logger = logging.getLogger(__name__)

ALLOC_CTX = dict(
    mail_create_nolog=True, mail_notrack=True, tracking_disable=True,
    leave_fast_create=True, mail_activity_automation_skip=True,
)


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _pfr_alloc_rate_extra_hours(self):
        """Weighted Extra Hours target from the stored real remaining balance."""
        self.ensure_one()
        return round((self.remaining_extra_hours_balance or 0.0) * U.OT_RATE, 2)

    def _pfr_alloc_rate_pto_hours(self):
        """Weighted PTO target from the stored real remaining balance."""
        self.ensure_one()
        return round((self.remaining_pto_balance or 0.0) * U.PH_RATE, 2)

    def _pfr_force_extra_hours(self, extra_type):
        """Allocate Extra Hours at Remaining Extra Hours Balance x 1.25."""
        self.ensure_one()
        self._pfr_force_leave_balance(
            extra_type, self._pfr_alloc_rate_extra_hours(), recon_alloc_name(self),
            'extra_hours_allocated_days', 'Extra Hours')

    def _pfr_force_pto(self, pto_type):
        """Allocate PTO at Remaining Paid Time Off Available x 1.5."""
        self.ensure_one()
        self._pfr_force_leave_balance(
            pto_type, self._pfr_alloc_rate_pto_hours(), pto_recon_alloc_name(self),
            'pto_allocated_days', 'Paid Time Off')

    def _pfr_alloc_rate_repair_allocations(self):
        """Update Extra Hours / PTO recon allocations in place (no cancel / draft / recompute)."""
        self.ensure_one()
        if not self.employee_id or not self.date_to:
            return 'skipped', 'Missing employee or period.'
        if 'hr.leave.allocation' not in self.env:
            return 'skipped', 'Leave allocations are not available.'

        types = self.env['pfr.settlement'].leave_types(self.company_id)
        notes = []
        if types['extra']:
            notes.append(self._pfr_alloc_rate_set_allocation(
                types['extra'][:1], self._pfr_alloc_rate_extra_hours(),
                recon_alloc_name(self), 'extra_hours_allocated_days'))
        if types['pto']:
            notes.append(self._pfr_alloc_rate_set_allocation(
                types['pto'][:1], self._pfr_alloc_rate_pto_hours(),
                pto_recon_alloc_name(self), 'pto_allocated_days'))
        if not notes:
            return 'skipped', 'No Extra Hours / Paid Time Off leave types found.'
        return 'done', '; '.join(n for n in notes if n)

    def _pfr_alloc_rate_set_allocation(self, leave_type, target_hours, alloc_name, allocated_field):
        """Set one recon allocation to `target_hours` without changing payslip state."""
        self.ensure_one()
        Alloc = self.env['hr.leave.allocation'].sudo()
        target = round(target_hours or 0.0, 2)
        days = round(target / U.DAILY_HOURS, 4) if target > 0.01 else 0.0

        domain = [
            ('employee_id', '=', self.employee_id.id),
            ('name', '=', alloc_name),
        ]
        if 'holiday_status_id' in Alloc._fields:
            domain.append(('holiday_status_id', '=', leave_type.id))
        elif 'work_entry_type_id' in Alloc._fields and leave_type._name == 'hr.work.entry.type':
            domain.append(('work_entry_type_id', '=', leave_type.id))

        allocs = Alloc.search(domain)
        if days <= 0.01:
            if allocs:
                allocs.with_context(
                    allocation_skip_state_check=True, tracking_disable=True, mail_notrack=True,
                ).write({'state': 'confirm'})
                allocs.with_context(allocation_skip_state_check=True).unlink()
                self._pfr_set({allocated_field: 0.0})
                return '%s cleared' % alloc_name
            self._pfr_set({allocated_field: 0.0})
            return '%s already empty' % alloc_name

        alloc = allocs[:1]
        if alloc:
            current = round(leave_hours(alloc), 2)
            if abs(current - target) <= 0.01:
                self._pfr_set({allocated_field: days})
                return '%s already weighted (%sh)' % (alloc_name, target)
            vals = {'number_of_days': days}
            # hour-based types keep duration via the stored hours display field
            if alloc.type_request_unit == 'hour' and 'number_of_hours_display' in alloc._fields:
                vals['number_of_hours_display'] = target
            alloc.with_context(
                tracking_disable=True, mail_notrack=True, mail_activity_automation_skip=True,
            ).write(vals)
            if alloc.state != 'validate':
                self._pfr_validate_allocation(alloc)
            self._pfr_set({allocated_field: days})
            return '%s updated %sh -> %sh' % (alloc_name, current, target)

        vals = {
            'name': alloc_name,
            'employee_id': self.employee_id.id,
            'number_of_days': days,
            'date_from': self.date_from,
        }
        if 'holiday_status_id' in Alloc._fields:
            vals['holiday_status_id'] = leave_type.id
        elif 'work_entry_type_id' in Alloc._fields:
            vals['work_entry_type_id'] = leave_type.id
        for fname, val in (('holiday_type', 'employee'), ('allocation_type', 'regular')):
            if fname in Alloc._fields:
                vals[fname] = val
        alloc = Alloc.with_context(employee_id=self.employee_id.id, **ALLOC_CTX).create(vals)
        self._pfr_validate_allocation(alloc)
        self._pfr_set({allocated_field: days})
        return '%s created %sh' % (alloc_name, target)
