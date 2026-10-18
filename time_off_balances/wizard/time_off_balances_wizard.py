# -*- coding: utf-8 -*-
from datetime import datetime, date
import io
import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class TimeOffBalancesWizard(models.TransientModel):
    _name = 'time.off.balances.wizard'
    _description = 'Time Off Balances Report Wizard'

    def _default_employee_id(self):
        return self.env.user.employee_id.id or False

    def _default_leave_type_ids(self):
        # Prefer Annual Leave by default
        annual_type = self.env['hr.leave.type'].search([
            '|',
            ('name', 'ilike', 'Annual'),
            ('name', 'ilike', 'سنوية')
        ], limit=1)
        if annual_type:
            return annual_type.ids
        first_types = self.env['hr.leave.type'].search([], limit=1)
        return first_types.ids if first_types else []

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        default=_default_employee_id,
    )
    holiday_status_ids = fields.Many2many(
        'hr.leave.type',
        string='Leave Types',
        required=True,
        default=_default_leave_type_ids,
    )
    date_from = fields.Date(
        string='Date From',
        help='Leave empty to start from the earliest movement.',
    )
    date_to = fields.Date(
        string='Date To',
        default=fields.Date.context_today,
        help='Leave empty to calculate up to today.',
    )
    sort_order = fields.Selection(
        [
            ('desc', 'Newest First'),
            ('asc', 'Oldest First'),
        ],
        string='Sort Order',
        default='desc',
        required=True,
    )
    include_unposted = fields.Selection(
        [
            ('all', 'All Records (Validated & Unposted)'),
            ('posted_only', 'Posted (Validated) Only'),
        ],
        string='Status Filter',
        default='all',
        required=True,
    )

    def _is_recon_record(self, record, name_field='name'):
        """Detect whether a leave or allocation was created by the payroll reconciliation module."""
        name_val = getattr(record, name_field, '') or ''
        priv_val = getattr(record, 'private_name', '') or ''
        note_val = getattr(record, 'notes', '') or ''
        combined = f"{name_val} {priv_val} {note_val}".lower()
        return any(k in combined for k in ['settlement', 'reconciliation', 'reconcil', 'balance sync'])

    def _get_added_by(self, record):
        """Return dynamic 'Added by <User>' string based on who created the record."""
        creator = record.create_uid
        if not creator or creator.id == 1 or creator.name == 'OdooBot':
            return 'Added by System'
        user_name = creator.name or creator.login or 'User'
        return f"Added by {user_name}"

    def _get_balance_report_data(self):
        self.ensure_one()
        employee = self.employee_id
        leave_types = self.holiday_status_ids

        # Status filter
        if self.include_unposted == 'posted_only':
            states = ['validate']
        else:
            states = ['confirm', 'validate', 'validate1']

        sections = []

        for leave_type in leave_types:
            # 1. Fetch Allocations and Leaves for this specific leave type
            alloc_records = self.env['hr.leave.allocation'].search([
                ('employee_id', '=', employee.id),
                ('holiday_status_id', '=', leave_type.id),
                ('state', 'in', states),
            ])

            leave_records = self.env['hr.leave'].search([
                ('employee_id', '=', employee.id),
                ('holiday_status_id', '=', leave_type.id),
                ('state', 'in', states),
            ])

            # 2. Overall Current Balance (all validated allocations - all validated leaves)
            total_posted_alloc = sum(self.env['hr.leave.allocation'].search([
                ('employee_id', '=', employee.id),
                ('holiday_status_id', '=', leave_type.id),
                ('state', '=', 'validate'),
            ]).mapped('number_of_days'))

            total_posted_leaves = sum(self.env['hr.leave'].search([
                ('employee_id', '=', employee.id),
                ('holiday_status_id', '=', leave_type.id),
                ('state', '=', 'validate'),
            ]).mapped('number_of_days'))

            current_balance = round(total_posted_alloc - total_posted_leaves, 2)

            # 3. Initial Balance (Prior to date_from)
            initial_balance = 0.0
            if self.date_from:
                alloc_prior = self.env['hr.leave.allocation'].search([
                    ('employee_id', '=', employee.id),
                    ('holiday_status_id', '=', leave_type.id),
                    ('state', '=', 'validate'),
                    ('date_from', '<', self.date_from),
                ])
                leave_prior = self.env['hr.leave'].search([
                    ('employee_id', '=', employee.id),
                    ('holiday_status_id', '=', leave_type.id),
                    ('state', '=', 'validate'),
                    ('request_date_from', '<', self.date_from),
                ])
                initial_balance = round(
                    sum(alloc_prior.mapped('number_of_days')) - sum(leave_prior.mapped('number_of_days')), 2
                )

            # 4. Build Event Timeline
            events = []

            # Allocations
            for a in alloc_records:
                a_start = a.date_from or (a.create_date.date() if a.create_date else False)
                if not a_start:
                    continue

                if self.date_from and a_start < self.date_from:
                    continue
                if self.date_to and a_start > self.date_to:
                    continue

                # Check if generated by payroll reconciliation
                if self._is_recon_record(a, name_field='name'):
                    desc = 'reconciled from system'
                elif a.accrual_plan_id:
                    desc = 'Monthly Auto Credit'
                elif a.notes and a.notes.strip() and 'added by tk' not in a.notes.lower():
                    desc = f"{a.notes.strip()} ({self._get_added_by(a)})"
                elif a.name and not a.name.startswith(f"{leave_type.name} (") and 'added by tk' not in a.name.lower():
                    desc = f"{a.name} ({self._get_added_by(a)})"
                else:
                    desc = self._get_added_by(a)

                is_system = bool(a.accrual_plan_id or (a.create_uid and a.create_uid.id == 1))
                is_tk = not is_system
                is_posted = a.state == 'validate'

                events.append({
                    'start_date_obj': a_start,
                    'start_date': a_start.strftime('%d/%m/%Y'),
                    'end_date': a.date_to.strftime('%d/%m/%Y') if a.date_to else '',
                    'days': round(a.number_of_days, 2),
                    'credit': 'Checked',
                    'description': desc,
                    'added_by_system': 'Checked' if is_system else 'Unchecked',
                    'added_by_tk': 'Checked' if is_tk else 'Unchecked',
                    'posted': 'Checked' if is_posted else 'Unchecked',
                    'is_credit': True,
                    'id': a.id,
                })

            # Leaves
            for l in leave_records:
                l_start = l.request_date_from or (l.date_from.date() if l.date_from else False)
                if not l_start:
                    continue

                if self.date_from and l_start < self.date_from:
                    continue
                if self.date_to and l_start > self.date_to:
                    continue

                l_end = l.request_date_to or (l.date_to.date() if l.date_to else l_start)

                # Check if generated by payroll reconciliation
                if self._is_recon_record(l, name_field='private_name'):
                    desc = 'reconciled from system'
                elif getattr(l, 'request_unit_hours', False) or (l.number_of_days < 1.0 and l_start == l_end):
                    desc = 'Subtractive Hours'
                elif l.private_name and l.private_name.strip() and 'added by tk' not in l.private_name.lower():
                    desc = f"{l.private_name.strip()} ({self._get_added_by(l)})"
                elif l.notes and l.notes.strip() and 'added by tk' not in l.notes.lower():
                    desc = f"{l.notes.strip()} ({self._get_added_by(l)})"
                else:
                    desc = self._get_added_by(l)

                is_subtractive = (desc == 'Subtractive Hours')
                is_system = is_subtractive
                is_tk = not is_subtractive
                is_posted = l.state == 'validate'

                events.append({
                    'start_date_obj': l_start,
                    'start_date': l_start.strftime('%d/%m/%Y'),
                    'end_date': l_end.strftime('%d/%m/%Y') if l_end else '',
                    'days': -round(l.number_of_days, 2),
                    'credit': 'Unchecked',
                    'description': desc,
                    'added_by_system': 'Checked' if is_system else 'Unchecked',
                    'added_by_tk': 'Checked' if is_tk else 'Unchecked',
                    'posted': 'Checked' if is_posted else 'Unchecked',
                    'is_credit': False,
                    'id': l.id,
                })

            # Chronological Sorting to compute running balance accurately
            events.sort(key=lambda x: (x['start_date_obj'], 0 if x['is_credit'] else 1, x['id']))

            running_balance = initial_balance
            for ev in events:
                ev['before_balance'] = running_balance
                ev['after_balance'] = round(running_balance + ev['days'], 2)
                running_balance = ev['after_balance']

            total_days = round(sum(ev['days'] for ev in events), 2)
            sum_days = total_days

            # Always sort newest first (desc) as requested
            if self.sort_order == 'desc':
                display_lines = list(reversed(events))
            else:
                display_lines = list(events)

            sections.append({
                'leave_type_id': leave_type.id,
                'leave_type_name': leave_type.name,
                'current_balance': current_balance,
                'initial_balance': initial_balance,
                'lines': display_lines,
                'total_days': total_days,
                'sum_days': sum_days,
            })

        # Backward compatibility for single section callers
        first_sec = sections[0] if sections else {}
        return {
            'company': self.env.company,
            'employee_name': employee.name,
            'employee_code': getattr(employee, 'identification_id', '') or getattr(employee, 'barcode', '') or '',
            'date_from_str': self.date_from.strftime('%d/%m/%Y') if self.date_from else '',
            'date_to_str': self.date_to.strftime('%d/%m/%Y') if self.date_to else '',
            'sections': sections,
            # Single section aliases for templates
            'leave_type_name': first_sec.get('leave_type_name', ''),
            'current_balance': first_sec.get('current_balance', 0.0),
            'initial_balance': first_sec.get('initial_balance', 0.0),
            'lines': first_sec.get('lines', []),
            'total_days': first_sec.get('total_days', 0.0),
            'sum_days': first_sec.get('sum_days', 0.0),
            'sort_order': self.sort_order,
        }

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('time_off_balances.action_report_time_off_balances').report_action(self)

    def action_export_excel(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/time_off_balances/export_xlsx/{self.id}',
            'target': 'self',
        }

    def _generate_xlsx_content(self):
        data = self._get_balance_report_data()

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Sheet')

        # Formats
        title_format = workbook.add_format({
            'font_name': 'Times New Roman',
            'font_size': 14,
            'bold': True,
            'align': 'left',
            'valign': 'vcenter',
        })

        header_format = workbook.add_format({
            'font_name': 'Times New Roman',
            'font_size': 11,
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#D9D9D9',
            'top': 1,
            'bottom': 1,
            'left': 1,
            'right': 1,
        })

        sub_header_format = workbook.add_format({
            'font_name': 'Times New Roman',
            'font_size': 11,
            'bold': True,
            'align': 'left',
            'valign': 'vcenter',
        })

        cell_text_format = workbook.add_format({
            'font_name': 'Times New Roman',
            'font_size': 10,
            'align': 'left',
            'valign': 'vcenter',
            'top': 1,
            'bottom': 1,
            'left': 1,
            'right': 1,
        })

        cell_center_format = workbook.add_format({
            'font_name': 'Times New Roman',
            'font_size': 10,
            'align': 'center',
            'valign': 'vcenter',
            'top': 1,
            'bottom': 1,
            'left': 1,
            'right': 1,
        })

        cell_number_format = workbook.add_format({
            'font_name': 'Times New Roman',
            'font_size': 10,
            'align': 'right',
            'valign': 'vcenter',
            'num_format': '0.00',
            'top': 1,
            'bottom': 1,
            'left': 1,
            'right': 1,
        })

        total_format = workbook.add_format({
            'font_name': 'Times New Roman',
            'font_size': 11,
            'bold': True,
            'align': 'left',
            'valign': 'vcenter',
        })

        # Columns: Start date, End date, Before Balance, Days, After Balance, Description
        sheet.set_column(0, 0, 14)  # Start date
        sheet.set_column(1, 1, 14)  # End date
        sheet.set_column(2, 2, 16)  # Before Balance
        sheet.set_column(3, 3, 14)  # Days
        sheet.set_column(4, 4, 16)  # After Balance
        sheet.set_column(5, 5, 42)  # Description

        # Row 0: Vacations Title
        emp_display = f" - {data['employee_name']}" if data.get('employee_name') else ""
        sheet.write(0, 0, f"Vacations{emp_display}", title_format)

        headers = [
            'Start date',
            'End date',
            'Before Balance',
            'Days',
            'After Balance',
            'Description',
        ]

        current_row = 2

        for sec in data['sections']:
            # Headers row
            for col_idx, h in enumerate(headers):
                sheet.write(current_row, col_idx, h, header_format)
            current_row += 1

            # Type: {name} (Current Balance: {balance})
            type_str = f"Type: {sec['leave_type_name']}  (Current Balance: {sec['current_balance']:.2f})"
            sheet.write(current_row, 0, type_str, sub_header_format)
            current_row += 1

            # Movement lines
            for line in sec['lines']:
                sheet.write(current_row, 0, line['start_date'], cell_center_format)
                sheet.write(current_row, 1, line['end_date'], cell_center_format)
                sheet.write_number(current_row, 2, line['before_balance'], cell_number_format)
                sheet.write_number(current_row, 3, line['days'], cell_number_format)
                sheet.write_number(current_row, 4, line['after_balance'], cell_number_format)
                sheet.write(current_row, 5, line['description'], cell_text_format)
                current_row += 1

            # Footers
            sheet.write(current_row, 3, f"Total Days: {sec['total_days']:.2f}", total_format)
            current_row += 1
            sheet.write(current_row, 3, f"Sum:{sec['sum_days']:.2f}", total_format)
            current_row += 2  # Separator for next section

        workbook.close()
        return output.getvalue()
