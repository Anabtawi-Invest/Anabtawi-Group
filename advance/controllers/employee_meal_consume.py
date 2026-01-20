from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class EmployeeFreeConsume(http.Controller):


    @http.route('/pos/employee_free/consume', type='jsonrpc', auth='user')
    def consume_employee_free(self, **kwargs):
        try:
            employee_id = kwargs.get('employee_id')
            product_ids = kwargs.get('product_ids') or []

            # ---------------- Validation ----------------
            if not employee_id or not product_ids:
                return {'error': 'Missing employee or products'}

            employee = request.env['hr.employee'].sudo().browse(int(employee_id))
            if not employee.exists():
                return {'error': 'Invalid employee'}

            products = request.env['product.product'].sudo().browse([int(pid) for pid in product_ids]).exists()
            if not products:
                return {'error': 'Invalid products'}

            # POS session
            session = request.env['pos.session'].sudo().search([
                ('user_id', '=', request.env.user.id),
                ('state', '=', 'opened'),
            ], limit=1)

            if not session:
                return {'error': 'No open POS session found'}

            # Always use the REAL company from the POS session
            company = session.company_id
            print("COMPANY:", company.name)
            pos_config = session.config_id
            picking_type = pos_config.drink_operation_type_id
            # --- Company Safety Check ---
            print(111,picking_type.company_id.name)
            print(222,session.company_id.name)

            if picking_type.company_id.id != session.company_id.id:
                return {'error': 'Invalid POS configuration: picking type belongs to another company.'}

            src_location = picking_type.default_location_src_id
            dest_location = picking_type.default_location_dest_id

            if not src_location or not dest_location:
                return {'error': 'Picking type is missing source or destination locations'}


            # ---------------- Get Products ----------------
            products = request.env['product.product'].sudo().browse([int(pid) for pid in product_ids]).exists()
            if not products:
                return {'error': 'Invalid products'}

            # ---------------- Prepare Move Lines ----------------
            move_lines = []
            for prod in products:
                move_lines.append((0, 0, {
                    'description_picking': prod.display_name,
                    'product_id': prod.id,
                    'product_uom_qty': 1,
                    'product_uom': prod.uom_id.id,
                    'location_id': src_location.id,
                    'location_dest_id': dest_location.id,
                }))


            # ---------------- Create Picking ----------------
            PickingEnv = request.env['stock.picking'].sudo().with_company(company.id)

            picking = PickingEnv.create({
                'picking_type_id': picking_type.id,
                'location_id': src_location.id,
                'location_dest_id': dest_location.id,
                'origin': f"POS Free Items for {employee.name}",
                'reason': 'employee_free',
                'consuming_employee_id': employee.id,
                'move_ids': move_lines,
            })


            # ---------------- Confirm + set done qty ----------------
            picking.button_validate()
            print(8585,picking.id)

            # ---------------- Validate movement ----------------


            return {'status': 'ok', 'picking_id': picking.id}

        except Exception as e:
            _logger.exception("❌ Failed to create hospitality picking")
            return {'error': str(e)}

