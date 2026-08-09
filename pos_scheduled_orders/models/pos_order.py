# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PosOrder(models.Model):
    _inherit = "pos.order"

    fulfillment_type = fields.Selection(
        selection=[
            ("pickup", "Store Pickup - استلام من الفرع"),
            ("delivery", "Home Delivery - توصيل منزلي"),
        ],
        string="Fulfillment Type (نوع الطلب)",
        copy=False,
    )
    scheduled_datetime = fields.Char(
        string="Scheduled Date & Time (موعد التسليم والملاحظات)",
        copy=False,
    )
    is_advance_deposit = fields.Boolean(
        string="Is Advance Deposit (طلب تواصي بعربون)",
        default=False,
        copy=False,
    )
    jofotara_status = fields.Selection(
        selection=[
            ("pending", "Pending Final Settlement - معلق لحين السداد"),
            ("submitted", "Submitted to ISTD - تم الارسال لجوفوتارا"),
        ],
        string="JoFotara Status (حالة جوفوتارا)",
        default="pending",
        copy=False,
    )
    delivery_address_id = fields.Many2one("res.partner", string="Delivery Address", copy=False)
    delivery_address_name = fields.Char(string="Fulfillment Name", copy=False)
    delivery_address_phone = fields.Char(string="Fulfillment Phone", copy=False)
    delivery_street = fields.Char(string="Delivery Street", copy=False)
    delivery_city = fields.Char(string="Delivery City", copy=False)
    delivery_building_apt = fields.Char(string="Delivery Building / Apt", copy=False)
    delivery_zip = fields.Char(string="Delivery Zip", copy=False)
    is_catering = fields.Boolean(string="Is Catering", default=False, copy=False)
    delivery_fee = fields.Float(string="Delivery Fee", digits=0, default=0.0)
    catering_fee = fields.Float(string="Catering Fee", digits=0, default=0.0)

    @api.model
    def _order_fields(self, ui_order):
        order_fields = super()._order_fields(ui_order)
        if "fulfillment_type" in ui_order:
            order_fields["fulfillment_type"] = ui_order.get("fulfillment_type")
        if "scheduled_datetime" in ui_order:
            order_fields["scheduled_datetime"] = ui_order.get("scheduled_datetime")
        if "is_advance_deposit" in ui_order:
            order_fields["is_advance_deposit"] = ui_order.get("is_advance_deposit")
        if "jofotara_status" in ui_order:
            order_fields["jofotara_status"] = ui_order.get("jofotara_status")
        if "delivery_address_id" in ui_order:
            order_fields["delivery_address_id"] = ui_order.get("delivery_address_id")
        if "delivery_address_name" in ui_order:
            order_fields["delivery_address_name"] = ui_order.get("delivery_address_name")
        if "delivery_address_phone" in ui_order:
            order_fields["delivery_address_phone"] = ui_order.get("delivery_address_phone")
        if "delivery_street" in ui_order:
            order_fields["delivery_street"] = ui_order.get("delivery_street")
        if "delivery_city" in ui_order:
            order_fields["delivery_city"] = ui_order.get("delivery_city")
        if "delivery_building_apt" in ui_order:
            order_fields["delivery_building_apt"] = ui_order.get("delivery_building_apt")
        if "delivery_zip" in ui_order:
            order_fields["delivery_zip"] = ui_order.get("delivery_zip")
        if "is_catering" in ui_order:
            order_fields["is_catering"] = ui_order.get("is_catering")
        if "delivery_fee" in ui_order:
            order_fields["delivery_fee"] = ui_order.get("delivery_fee")
        if "catering_fee" in ui_order:
            order_fields["catering_fee"] = ui_order.get("catering_fee")
        return order_fields

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        if not fields_to_load:
            return fields_to_load
        extra_fields = [
            "fulfillment_type", "scheduled_datetime", "is_advance_deposit",
            "jofotara_status", "delivery_address_id", "delivery_address_name",
            "delivery_address_phone", "delivery_street", "delivery_city",
            "delivery_building_apt", "delivery_zip", "is_catering",
            "delivery_fee", "catering_fee",
        ]
        for field in extra_fields:
            if field not in fields_to_load:
                fields_to_load.append(field)
        return fields_to_load

    def _prepare_picking_vals(self, partner_id, picking_type, location_id, location_dest_id):
        vals = super()._prepare_picking_vals(partner_id, picking_type, location_id, location_dest_id)
        if self.fulfillment_type:
            vals["fulfillment_type"] = self.fulfillment_type
            dt_val = False
            if self.scheduled_datetime:
                try:
                    clean_str = str(self.scheduled_datetime).replace("T", " ").strip()
                    if len(clean_str) == 16:
                        clean_str += ":00"
                    dt_val = fields.Datetime.to_datetime(clean_str)
                except Exception:
                    dt_val = False
            vals["pickup_delivery_datetime"] = dt_val
            vals["delivery_address_id"] = self.delivery_address_id.id if self.delivery_address_id else False
            vals["is_catering"] = self.is_catering
            if dt_val:
                vals["scheduled_date"] = dt_val
                vals["date_deadline"] = dt_val
        return vals

    def _create_order_picking(self):
        super()._create_order_picking()
        for order in self:
            if order.is_advance_deposit:
                for picking in order.picking_ids:
                    if picking.state not in ["done", "cancel"]:
                        picking.write({"state": "waiting"})

    def action_finalize_deposit_and_validate_stock(self):
        for order in self:
            for picking in order.picking_ids:
                if picking.state not in ["done", "cancel"]:
                    picking.action_assign()
                    if picking.state == "assigned":
                        picking.button_validate()
            order.write({"is_advance_deposit": False, "jofotara_status": "submitted", "state": "done"})
            if not order.account_move:
                try:
                    order.action_pos_order_invoice()
                except Exception:
                    pass
        return True

    @api.model
    def search_open_scheduled_orders(self, pos_config_id=False, search_query="", partner_id=False):
        try:
            domain = [("state", "not in", ["cancel"])]

            if partner_id:
                try:
                    domain.append(("partner_id", "=", int(partner_id)))
                except Exception:
                    pass

            if search_query and str(search_query).strip():
                q = str(search_query).strip()
                domain.append("|")
                domain.append("|")
                domain.append("|")
                domain.append(("delivery_address_name", "ilike", q))
                domain.append(("delivery_address_phone", "ilike", q))
                domain.append(("name", "ilike", q))
                domain.append(("pos_reference", "ilike", q))

            orders = self.search(domain, order="date_order desc", limit=100)
            res = []
            for o in orders:
                paid = sum(o.payment_ids.mapped("amount"))
                total = o.amount_total
                due = total - paid
                if due > 0.001 or o.is_advance_deposit or o.fulfillment_type:
                    res.append({
                        "id": o.id,
                        "name": o.name or o.pos_reference or f"Order #{o.id}",
                        "pos_reference": o.pos_reference or "",
                        "date_order": str(o.date_order) if o.date_order else "",
                        "scheduled_datetime": o.scheduled_datetime or "",
                        "fulfillment_type": o.fulfillment_type or "pickup",
                        "customer_name": o.delivery_address_name or (o.partner_id.name if o.partner_id else "عميل سفري"),
                        "customer_phone": o.delivery_address_phone or (o.partner_id.mobile if o.partner_id else ""),
                        "partner_id": o.partner_id.id if o.partner_id else False,
                        "street": o.delivery_street or "",
                        "city": o.delivery_city or "",
                        "amount_total": total,
                        "amount_paid": paid,
                        "amount_due": due if due > 0 else 0.0,
                    })
            return res
        except Exception as e:
            return []

    @api.model
    def action_complete_scheduled_order_from_pos(self, order_id, payment_method_id, amount_tendered):
        order = self.browse(order_id)
        if not order.exists():
            raise UserError(_("Scheduled Order not found."))

        paid = sum(order.payment_ids.mapped("amount"))
        due = order.amount_total - paid

        if due > 0:
            pm = self.env["pos.payment.method"].browse(payment_method_id)
            if not pm.exists():
                raise UserError(_("Invalid payment method selected."))

            self.env["pos.payment"].create({
                "pos_order_id": order.id,
                "amount": due,
                "payment_method_id": pm.id,
                "payment_date": fields.Datetime.now(),
            })

        for picking in order.picking_ids:
            if picking.state not in ["done", "cancel"]:
                picking.action_assign()
                if picking.state == "assigned":
                    picking.button_validate()

        order.write({
            "is_advance_deposit": False,
            "jofotara_status": "submitted",
            "state": "done",
        })

        account_move = False
        try:
            res = order.action_pos_order_invoice()
            if isinstance(res, dict) and res.get("res_id"):
                account_move = self.env["account.move"].browse(res["res_id"])
            elif order.account_move:
                account_move = order.account_move
        except Exception:
            pass

        return {
            "success": True,
            "order_id": order.id,
            "name": order.name,
            "amount_total": order.amount_total,
            "amount_paid": order.amount_total,
            "amount_due": 0.0,
            "invoice_id": account_move.id if account_move else False,
            "invoice_name": account_move.name if account_move else "",
        }
