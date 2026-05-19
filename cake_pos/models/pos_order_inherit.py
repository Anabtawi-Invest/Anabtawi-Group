import json
from odoo import api, models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    @api.model
    def _process_order(self, order, draft, existing_order):
        """
        After the standard POS order is processed, scan every orderline for the
        CAKE_CFG:: prefix in the customer note and create cake.order + MO records.
        """
        pos_order = super()._process_order(order, draft, existing_order)

        cfg = self.env['cake.config'].search([], limit=1)

        for line in pos_order.lines:
            note = (line.note or '').strip()
            if not note.startswith('CAKE_CFG::'):
                continue
            try:
                data = json.loads(note[len('CAKE_CFG::'):])
            except Exception:
                continue

            # Build extra_features_json
            extra_json = json.dumps(data.get('extra_features', []))

            cake_vals = {
                'pos_order_id':       pos_order.id,
                'persons':            str(data.get('persons', 10)),
                'sponge_id':          data.get('sponge_id') or False,
                'cream_id':           data.get('cream_id') or False,
                'filling_id':         data.get('filling_id') or False,
                'decoration_id':      data.get('decoration_id') or False,
                'disk_id':            data.get('disk_id') or False,
                'use_sugar_paste':    bool(data.get('use_sugar_paste', False)),
                'sugar_paste_id':     data.get('sugar_paste_id') or False,
                'extra_features_json': extra_json,
                'customer_name':      data.get('customer_name', ''),
                'notes':              data.get('notes', ''),
                'total_cost':         data.get('total_cost', 0.0),
                'selling_price':      data.get('selling_price', 0.0),
            }

            cake_order = self.env['cake.order'].sudo().create(cake_vals)
            cake_order.action_create_mo()

            if cfg and cfg.auto_send_email:
                try:
                    cake_order._auto_send_email()
                except Exception:
                    pass

        return pos_order
