# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import timedelta
import logging
from lxml import etree

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

OT_PRIORITY_CODES = ['OTR', 'PHO', 'OTW']  # Weekend, Public Holiday, Weekday
LATENESS_CODES_DEFAULT = ('LAT', 'LATE', 'Lateness', 'L')


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    lateness_hours = fields.Float(string='Lateness (hrs)', compute='_compute_lateness_and_ot', store=False)
    overtime_hours = fields.Float(string='Overtime (hrs)', compute='_compute_lateness_and_ot', store=False)
    remaining_lateness_hours = fields.Float(string='Remaining Lateness (hrs)', compute='_compute_remaining_lateness', store=False)

    def _get_configured_annual_leave_type_id(self) -> int:
        """Prefer mass_reconciliation key, fallback to legacy key."""
        ICP = self.env['ir.config_parameter'].sudo()
        val = ICP.get_param('mass_reconciliation.annual_leave_type_id') or ICP.get_param('lateness_coverage.annual_leave_type_id') or 0
        try:
            return int(val)
        except Exception:
            return 0

    def _get_worked_day_hours_by_code(self):
        self.ensure_one()
        buckets = {code: 0.0 for code in OT_PRIORITY_CODES}
        lateness = 0.0
        for line in self.worked_days_line_ids:
            code = (line.work_entry_type_id.code or '').strip()
            if code in buckets:
                buckets[code] += line.number_of_hours or 0.0
            if code in LATENESS_CODES_DEFAULT:
                lateness += line.number_of_hours or 0.0
        return lateness, buckets

    @api.depends('worked_days_line_ids.number_of_hours', 'worked_days_line_ids.work_entry_type_id.code')
    def _compute_lateness_and_ot(self):
        for slip in self:
            lateness, buckets = slip._get_worked_day_hours_by_code()
            slip.lateness_hours = lateness
            slip.overtime_hours = sum(buckets.values())

    @api.depends('input_line_ids.amount', 'input_line_ids.code',
                 'worked_days_line_ids.number_of_hours', 'worked_days_line_ids.work_entry_type_id.code')
    def _compute_remaining_lateness(self):
        for slip in self:
            inp = slip.input_line_ids.filtered(lambda l: (l.code or '').strip() == 'REMLATE')
            if inp:
                slip.remaining_lateness_hours = sum(inp.mapped('amount'))
            else:
                slip.remaining_lateness_hours = slip.lateness_hours

    # ---------------- UI injection (no fragile inherit_id XML) ----------------
    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        res = super().fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        if view_type != 'list':
            return res

        try:
            arch = etree.fromstring(res['arch'])
        except Exception:
            return res

        root = arch
        if root.tag not in ('list', 'tree'):
            return res

        # Remove OT Bank column completely if present
        for fname in ('ot_bank', 'ot_bank_hours', 'ot_bank_balance', 'dashboard_ot_bank_hours'):
            for node in root.xpath(f".//field[@name='{fname}']"):
                node.getparent().remove(node)

        existing = {n.get('name') for n in root.xpath(".//field") if n.get('name')}

        for fname in ('lateness_hours', 'overtime_hours', 'remaining_lateness_hours'):
            if fname not in existing and fname in self._fields:
                node = etree.Element('field', name=fname)
                node.set('optional', 'show')
                root.append(node)

        res['arch'] = etree.tostring(arch, encoding='unicode')
        return res

    # ---------------- Core reconciliation ----------------
    def action_reconcile_lateness_no_ot_bank(self):
        """
        Covers lateness by:
          1) Deducting from OT buckets in order OTR -> PHO -> OTW by reducing worked days hours.
          2) If still remaining, deducting from Annual Leave (hours) by creating validated Time Off.
             If validation fails (e.g., not enough balance), leave remaining for salary deduction.
          3) Store remaining hours in payslip input REMLATE for salary rule deduction.
        """
        Leave = self.env['hr.leave'].sudo()
        LeaveType = self.env['hr.leave.type'].sudo()

        for slip in self:
            lateness, buckets = slip._get_worked_day_hours_by_code()
            remaining = float(lateness or 0.0)

            # 1) Consume OT buckets
            for code in OT_PRIORITY_CODES:
                if remaining <= 0:
                    break
                available = float(buckets.get(code, 0.0) or 0.0)
                if available <= 0:
                    continue

                consume = min(available, remaining)

                lines = slip.worked_days_line_ids.filtered(
                    lambda l: (l.work_entry_type_id.code or '').strip() == code
                ).sorted('id')

                to_consume = consume
                for line in lines:
                    if to_consume <= 0:
                        break
                    h = float(line.number_of_hours or 0.0)
                    if h <= 0:
                        continue
                    cut = min(h, to_consume)
                    line.number_of_hours = h - cut
                    to_consume -= cut

                remaining -= consume

            # 2) Annual Leave deduction (hours)
            if remaining > 0:
                leave_type_id = slip._get_configured_annual_leave_type_id()
                if not leave_type_id:
                    raise UserError(_(
                        "Annual Leave Type for lateness coverage is not configured.\n"
                        "Set System Parameter: mass_reconciliation.annual_leave_type_id = <Annual Leave Type ID (Hours)>"
                    ))

                leave_type = LeaveType.browse(leave_type_id).exists()
                if not leave_type:
                    raise UserError(_("Configured Annual Leave Type not found. Please reconfigure."))

                dt_from = fields.Datetime.to_datetime(slip.date_from)
                dt_to = dt_from + timedelta(hours=float(remaining))

                leave_vals = {
                    'name': _('Lateness Coverage (%s)') % (getattr(slip, 'number', False) or slip.name),
                    'employee_id': slip.employee_id.id,
                    'holiday_status_id': leave_type.id,
                }

                if 'date_from' in Leave._fields:
                    leave_vals['date_from'] = dt_from
                if 'date_to' in Leave._fields:
                    leave_vals['date_to'] = dt_to

                # Optional request_* fields
                if 'request_unit_hours' in Leave._fields:
                    leave_vals['request_unit_hours'] = True
                if 'request_date_from' in Leave._fields:
                    leave_vals['request_date_from'] = slip.date_from
                if 'request_date_to' in Leave._fields:
                    leave_vals['request_date_to'] = slip.date_from
                if 'request_hour_from' in Leave._fields:
                    leave_vals['request_hour_from'] = 0.0
                if 'request_hour_to' in Leave._fields:
                    leave_vals['request_hour_to'] = float(remaining)

                # Guard: strip unsupported fields
                for k in list(leave_vals.keys()):
                    if k not in Leave._fields:
                        leave_vals.pop(k, None)

                try:
                    leave = Leave.create(leave_vals)
                    leave_sudo = leave.sudo()

                    # Method-safe workflow
                    if hasattr(leave_sudo, 'action_confirm'):
                        leave_sudo.action_confirm()
                    elif hasattr(leave_sudo, 'action_submit'):
                        leave_sudo.action_submit()

                    if hasattr(leave_sudo, 'action_validate'):
                        leave_sudo.action_validate()
                    elif hasattr(leave_sudo, 'action_approve'):
                        leave_sudo.action_approve()
                    elif 'state' in leave_sudo._fields:
                        leave_sudo.write({'state': 'validate'})

                    remaining = 0.0
                except Exception as e:
                    # Don't block payroll; keep remaining for salary deduction
                    _logger.exception("Annual leave deduction failed for payslip %s: %s", slip.id, e)

            # 3) Store remaining lateness in payslip input (REMLATE)
            inp = slip.input_line_ids.filtered(lambda l: (l.code or '').strip() == 'REMLATE')
            if inp:
                inp.write({'amount': remaining})
            else:
                input_type = self.env['hr.payslip.input.type'].sudo().search([('code', '=', 'REMLATE')], limit=1)
                if not input_type:
                    input_type = self.env['hr.payslip.input.type'].sudo().create({'name': 'Remaining Lateness (hrs)', 'code': 'REMLATE'})
                self.env['hr.payslip.input'].sudo().create({
                    'payslip_id': slip.id,
                    'input_type_id': input_type.id,
                    'name': 'Remaining Lateness (hrs)',
                    'code': 'REMLATE',
                    'amount': remaining,
                })

        return {'type': 'ir.actions.client', 'tag': 'reload'}
