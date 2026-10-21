# -*- coding: utf-8 -*-
import base64
import io
from collections import defaultdict
from datetime import datetime, time

from odoo import _, api, fields, models
from odoo.exceptions import UserError

try:
    import xlsxwriter
except ImportError:  # pragma: no cover
    xlsxwriter = None


class FactoryBranchTransferWizard(models.TransientModel):
    _name = 'factory.branch.transfer.wizard'
    _description = 'Factory to Branch Transfer Excel Report'

    date_from = fields.Date(
        string='From Date',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1),
    )
    date_to = fields.Date(
        string='To Date',
        required=True,
        default=fields.Date.today,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    only_done = fields.Boolean(
        string='Only Done Transfers',
        default=True,
        help='If checked, only completed (done) stock moves are included. '
             'Draft, waiting, and cancelled transfers are excluded.',
    )
    file_data = fields.Binary(string='File', readonly=True)
    filename = fields.Char(string='Filename', readonly=True)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wiz in self:
            if wiz.date_from and wiz.date_to and wiz.date_from > wiz.date_to:
                raise UserError(_('From Date must be before or equal to To Date.'))

    def _get_datetime_bounds(self):
        self.ensure_one()
        start = datetime.combine(fields.Date.to_date(self.date_from), time.min)
        # exclusive end: day after date_to at 00:00
        end_day = fields.Date.to_date(self.date_to)
        end = datetime.combine(end_day, time.max)
        return start, end

    def _get_factory_warehouse(self):
        Wh = self.env['stock.warehouse'].sudo()
        factory = Wh.search([
            ('company_id', '=', self.company_id.id),
            ('code', '=', 'NAJ'),
        ], limit=1)
        if not factory:
            factory = Wh.search([
                ('company_id', '=', self.company_id.id),
                '|',
                ('name', 'ilike', 'Factory'),
                ('name', 'ilike', 'مصنع'),
            ], limit=1)
        if not factory:
            raise UserError(_('Factory warehouse (code NAJ) was not found.'))
        return factory

    def _get_branch_warehouses(self, factory):
        Wh = self.env['stock.warehouse'].sudo()
        # All company warehouses except Factory and main "Anabtawi invest" (WH)
        return Wh.search([
            ('company_id', '=', self.company_id.id),
            ('id', '!=', factory.id),
            ('code', '!=', 'WH'),
        ])

    def _get_corridor_locations(self):
        """Internal locations used as factory↔branch transfer corridors."""
        Loc = self.env['stock.location'].sudo()
        loc_factory_side = Loc.search([
            ('usage', '=', 'internal'),
            ('name', 'ilike', 'المصنع -'),
        ])
        loc_branch_side = Loc.search([
            ('usage', '=', 'internal'),
            ('name', 'ilike', '- المصنع'),
        ])
        loc_extra = Loc.search([
            ('usage', '=', 'internal'),
            ('complete_name', 'ilike', 'المصنع'),
            ('complete_name', 'ilike', 'فرع'),
        ])
        corridors = loc_factory_side | loc_branch_side | loc_extra
        if not corridors:
            raise UserError(_(
                'No factory↔branch corridor locations found '
                '(names like "المصنع - فرع …" / "فرع … - المصنع").'
            ))
        return corridors

    def _move_state_domain(self):
        if self.only_done:
            return [('state', '=', 'done')]
        return [('state', 'not in', ['cancel', 'draft'])]

    def _search_moves(self):
        self.ensure_one()
        factory = self._get_factory_warehouse()
        branches = self._get_branch_warehouses(factory)
        if not branches:
            raise UserError(_('No branch warehouses found.'))
        corridors = self._get_corridor_locations()
        date_from, date_to = self._get_datetime_bounds()

        Move = self.env['stock.move'].sudo()
        state_domain = self._move_state_domain()

        out_moves = Move.search(
            state_domain + [
                ('date', '>=', date_from),
                ('date', '<=', date_to),
                ('company_id', '=', self.company_id.id),
                ('location_id.warehouse_id', '=', factory.id),
                ('location_dest_id', 'in', corridors.ids),
            ],
            order='date, id',
        )
        in_moves = Move.search(
            state_domain + [
                ('date', '>=', date_from),
                ('date', '<=', date_to),
                ('company_id', '=', self.company_id.id),
                ('location_id', 'in', corridors.ids),
                ('location_dest_id.warehouse_id', 'in', branches.ids),
            ],
            order='date, id',
        )
        return out_moves, in_moves

    def action_export_xlsx(self):
        self.ensure_one()
        if xlsxwriter is None:
            raise UserError(_("The Python library 'xlsxwriter' is required to export Excel files."))

        out_moves, in_moves = self._search_moves()
        if not out_moves and not in_moves:
            raise UserError(_('No transfers found for the selected date range.'))

        xlsx_bytes = self._build_xlsx(out_moves, in_moves)
        fname = (
            f"Factory_to_Branches_"
            f"{self.date_from}_{self.date_to}.xlsx"
        )
        self.write({
            'file_data': base64.b64encode(xlsx_bytes),
            'filename': fname,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': (
                f'/web/content/?model={self._name}'
                f'&id={self.id}&field=file_data&filename={fname}&download=true'
            ),
            'target': 'self',
        }

    def _move_row_values(self, move):
        to_wh = move.location_dest_id.warehouse_id.name or move.location_dest_id.name or ''
        return {
            'date': move.date,
            'transfer': move.picking_id.name or '',
            'from_loc': move.location_id.complete_name or '',
            'to_loc': move.location_dest_id.complete_name or '',
            'to_branch': to_wh,
            'product': move.product_id.display_name or '',
            'default_code': move.product_id.default_code or '',
            'qty': move.quantity if self.only_done else (move.quantity or move.product_uom_qty),
            'uom': move.product_uom.name or '',
            'picking_type': move.picking_type_id.display_name or '',
            'state': move.state,
        }

    def _write_moves_sheet(self, workbook, styles, sheet_name, moves):
        ws = workbook.add_worksheet(sheet_name[:31])
        ws.freeze_panes(1, 0)
        headers = [
            _('Date'),
            _('Transfer'),
            _('From Location'),
            _('To Location'),
            _('To Branch WH'),
            _('Product'),
            _('Internal Ref'),
            _('Qty Done'),
            _('UoM'),
            _('Picking Type'),
            _('State'),
        ]
        for col, header in enumerate(headers):
            ws.write(0, col, header, styles['header'])

        if not moves:
            ws.write(1, 0, _('No data for selected filters.'), styles['text'])
        else:
            for row, move in enumerate(moves, start=1):
                data = self._move_row_values(move)
                if data['date']:
                    ws.write_datetime(row, 0, fields.Datetime.to_datetime(data['date']), styles['datetime'])
                else:
                    ws.write(row, 0, '', styles['text'])
                ws.write(row, 1, data['transfer'], styles['text'])
                ws.write(row, 2, data['from_loc'], styles['text'])
                ws.write(row, 3, data['to_loc'], styles['text'])
                ws.write(row, 4, data['to_branch'], styles['text'])
                ws.write(row, 5, data['product'], styles['text'])
                ws.write(row, 6, data['default_code'], styles['text'])
                ws.write_number(row, 7, data['qty'] or 0.0, styles['number'])
                ws.write(row, 8, data['uom'], styles['text'])
                ws.write(row, 9, data['picking_type'], styles['text'])
                ws.write(row, 10, data['state'], styles['text'])

        ws.set_column(0, 0, 20)
        ws.set_column(1, 1, 18)
        ws.set_column(2, 3, 35)
        ws.set_column(4, 4, 22)
        ws.set_column(5, 5, 40)
        ws.set_column(6, 6, 16)
        ws.set_column(7, 7, 12)
        ws.set_column(8, 8, 10)
        ws.set_column(9, 9, 22)
        ws.set_column(10, 10, 12)
        return ws

    def _write_summary_sheet(self, workbook, styles, in_moves):
        ws = workbook.add_worksheet(_('Summary by branch')[:31])
        ws.freeze_panes(1, 0)
        headers = [
            _('Branch'),
            _('Product'),
            _('Internal Ref'),
            _('Total Qty'),
            _('UoM'),
        ]
        for col, header in enumerate(headers):
            ws.write(0, col, header, styles['header'])

        agg = defaultdict(float)
        meta = {}
        for move in in_moves:
            branch = move.location_dest_id.warehouse_id.name or move.location_dest_id.name or '?'
            key = (branch, move.product_id.id)
            agg[key] += move.quantity if self.only_done else (move.quantity or move.product_uom_qty)
            meta[key] = (
                move.product_id.display_name or '',
                move.product_id.default_code or '',
                move.product_uom.name or '',
            )

        if not agg:
            ws.write(1, 0, _('No data for selected filters.'), styles['text'])
        else:
            row = 1
            for (branch, _pid), qty in sorted(agg.items(), key=lambda item: (item[0][0], meta[item[0]][0])):
                pname, code, uom = meta[(branch, _pid)]
                ws.write(row, 0, branch, styles['text'])
                ws.write(row, 1, pname, styles['text'])
                ws.write(row, 2, code, styles['text'])
                ws.write_number(row, 3, qty or 0.0, styles['number'])
                ws.write(row, 4, uom, styles['text'])
                row += 1

        ws.set_column(0, 0, 24)
        ws.set_column(1, 1, 40)
        ws.set_column(2, 2, 16)
        ws.set_column(3, 3, 12)
        ws.set_column(4, 4, 10)
        return ws

    def _build_xlsx(self, out_moves, in_moves):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        styles = {
            'header': workbook.add_format({
                'bold': True,
                'bg_color': '#D9E1F2',
                'border': 1,
                'align': 'center',
            }),
            'text': workbook.add_format({'border': 1}),
            'number': workbook.add_format({'border': 1, 'num_format': '#,##0.00'}),
            'datetime': workbook.add_format({'border': 1, 'num_format': 'yyyy-mm-dd hh:mm:ss'}),
        }

        self._write_moves_sheet(workbook, styles, _('Received at branches'), in_moves)
        self._write_moves_sheet(workbook, styles, _('Left Factory'), out_moves)
        self._write_summary_sheet(workbook, styles, in_moves)

        workbook.close()
        return output.getvalue()
