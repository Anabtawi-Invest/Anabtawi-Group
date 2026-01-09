from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class ConsumptionMealController(http.Controller):

    @http.route('/pos/consumption/check', type='jsonrpc', auth='user')
    def check_consumption_access(self):

        session = request.env['pos.session'].sudo().search([
            ('user_id', '=', request.env.user.id),
            ('state', '=', 'opened'),
        ], limit=1)

        if not session:
            return {
                'allow_consumption': False,
                'employee_id': False,
                'employee_name': False,
            }

        company = session.company_id

        # 2️⃣ Get employee linked to user AND same company
        employee = request.env['hr.employee'].sudo().search([
            ('user_id', '=', request.env.user.id),
            ('company_id', '=', company.id),
        ], limit=1)

        if not employee:
            return {
                'allow_consumption': False,
                'employee_id': False,
                'employee_name': False,
            }

        # 3️⃣ Check access
        has_access = employee.can_consume_pos_items

        return {
            'allow_consumption': has_access,
            'employee_id': employee.id,
            'employee_name': employee.name,
        }

    @http.route('/pos/consumption/data', type='jsonrpc', auth='user')
    def get_consumption_data(self):
        """Return employees and all stock.picking reasons except 'employee_free'."""
        try:
            # Fetch employees
            employees = request.env['hr.employee'].sudo().search_read(
                fields=['id', 'name'],
                limit=200
            )

            # Read and filter reasons
            reason_field = request.env['stock.picking']._fields.get('reason')
            reasons = [
                (key, label)
                for key, label in (reason_field.selection if reason_field else [])
                if key != 'employee_free'
            ]
            print(reasons,1111)
            owners = request.env['hr.employee'].sudo().search_read(
                [('is_owner', '=', True)],
                ['id', 'name']
            )
            return {
                'employees': employees,
                'reasons': reasons,
                'owners': owners,
            }

        except Exception as e:
            _logger.exception("Failed to load consumption data")
            return {'error': str(e)}

    @http.route('/pos/consumption/confirm', type='jsonrpc', auth='user')
    def confirm_consumption(self, **kwargs):
        try:
            employee_id = kwargs.get('employee_id')
            owner_id = kwargs.get('owner_id')
            reason = kwargs.get('reason')
            order_lines = kwargs.get('order_lines', [])
            note = kwargs.get("note") or ""

            if not reason or not order_lines:
                return {'error': 'Missing reason or products.'}

            # ---------- POS SESSION ----------
            session = request.env['pos.session'].sudo().search([
                ('user_id', '=', request.env.user.id),
                ('state', '=', 'opened'),
            ], limit=1)

            if not session:
                return {'error': 'No open POS session found for current user.'}

            company = session.company_id
            pos_config = session.config_id

            # ---------- USE ONLY SESSION COMPANY ----------
            Product = request.env['product.product'].sudo().with_company(company.id)
            StockPicking = request.env['stock.picking'].sudo().with_company(company.id)
            StockLocation = request.env['stock.location'].sudo().with_company(company.id)

            # ---------- PICKING TYPE SELECTION ----------
            if reason == "damage":
                picking_type = pos_config.scrap_operation_type_id
            else:
                picking_type = pos_config.drink_operation_type_id

            if not picking_type:
                return {'error': 'Picking type not configured.'}

            # 🔥 SOURCE & DESTINATION MUST belong to session company
            src_location = picking_type.default_location_src_id.with_company(company.id)
            dest_location = picking_type.default_location_dest_id.with_company(company.id)

            if not src_location or not dest_location:
                return {'error': 'Source/Destination missing in picking type.'}

            # ---------- BUILD MOVE LINES ----------
            move_lines = []
            for line in order_lines:
                product = Product.browse(int(line['product_id']))
                if not product.exists():
                    continue

                move_lines.append((0, 0, {
                    'description_picking': product.display_name,
                    'product_id': product.id,
                    'product_uom_qty': line.get('qty', 1),
                    'product_uom': product.uom_id.id,
                    'location_id': src_location.id,
                    'location_dest_id': dest_location.id,
                    'company_id': company.id,
                }))

            # ---------- CREATE PICKING ----------
            picking_vals = {
                'picking_type_id': picking_type.id,
                'location_id': src_location.id,
                'location_dest_id': dest_location.id,
                'origin': f"POS Consumption ({reason})",
                'reason': reason,
                'note': note,
                'move_ids': move_lines,
                'company_id': company.id,
            }

            if reason == "owner_free":
                picking_vals.update({
                    'responsible_employee_id': int(employee_id),
                    'owner_employee_id': int(owner_id) if owner_id else False,
                })
            else:
                picking_vals['responsible_employee_id'] = int(employee_id)

            picking = StockPicking.create(picking_vals)

            # ---------- VALIDATE ----------
            picking.button_validate()
            print(picking.id)

            return {'status': 'ok', 'picking_id': picking.id, 'picking_name': picking.name}

        except Exception as e:
            _logger.exception("❌ Failed to create consumption picking")
            return {'error': str(e)}



