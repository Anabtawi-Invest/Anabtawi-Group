# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


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
    scheduled_datetime = fields.Datetime(
        string="Scheduled Date & Time (موعد التسليم والملاحظات)",
        copy=False,
    )
    is_advance_deposit = fields.Boolean(
        string="Is Advance Deposit (طلب تواصي بعربون)",
        default=False,
        copy=False,
        help="Flagged True if order is partially paid/deposit taken on Day 1.",
    )
    jofotara_status = fields.Selection(
        selection=[
            ("pending", "Pending Final Settlement - معلق لحين السداد"),
            ("submitted", "Submitted to ISTD - تم الارسال لجوفوتارا"),
        ],
        string="JoFotara Status (حالة جوفوتارا)",
        default="pending",
        copy=False,
        help="ISTD Jordan compliance status: Pending deposit vs Final submitted invoice.",
    )
    delivery_address_id = fields.Many2one(
        "res.partner",
        string="Delivery Contact Address (عنوان التوصيل)",
        copy=False,
    )
    delivery_address_name = fields.Char(
        string="Fulfillment Contact Name (اسم العميل)",
        copy=False,
    )
    delivery_address_phone = fields.Char(
        string="Fulfillment Contact Phone (هاتف العميل)",
        copy=False,
    )
    delivery_street = fields.Char(
        string="Delivery Street (الشارع)",
        copy=False,
    )
    delivery_city = fields.Char(
        string="Delivery City (المدينة / المنطقة)",
        copy=False,
    )
    delivery_building_apt = fields.Char(
        string="Delivery Building / Apt (البناية / الشقة)",
        copy=False,
    )
    delivery_zip = fields.Char(
        string="Delivery Zip (الرمز البريدي)",
        copy=False,
    )
    is_catering = fields.Boolean(
        string="Is Catering (طلب ضيافة كترنج)",
        default=False,
        copy=False,
    )
    delivery_fee = fields.Float(
        string="Delivery Fee (رسوم التوصيل)",
        digits=0,
        default=0.0,
    )
    catering_fee = fields.Float(
        string="Catering Fee (رسوم الضيافة)",
        digits=0,
        default=0.0,
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        if not fields_to_load:
            return fields_to_load
        extra_fields = [
            "fulfillment_type",
            "scheduled_datetime",
            "is_advance_deposit",
            "jofotara_status",
            "delivery_address_id",
            "delivery_address_name",
            "delivery_address_phone",
            "delivery_street",
            "delivery_city",
            "delivery_building_apt",
            "delivery_zip",
            "is_catering",
            "delivery_fee",
            "catering_fee",
        ]
        for field in extra_fields:
            if field not in fields_to_load:
                fields_to_load.append(field)
        return fields_to_load

    def _prepare_picking_vals(self, partner_id, picking_type, location_id, location_dest_id):
        vals = super()._prepare_picking_vals(partner_id, picking_type, location_id, location_dest_id)
        if self.fulfillment_type:
            vals["fulfillment_type"] = self.fulfillment_type
            vals["pickup_delivery_datetime"] = self.scheduled_datetime
            vals["delivery_address_id"] = self.delivery_address_id.id if self.delivery_address_id else False
            vals["is_catering"] = self.is_catering
            if self.scheduled_datetime:
                vals["scheduled_date"] = self.scheduled_datetime
                vals["date_deadline"] = self.scheduled_datetime
        return vals

    def _create_order_picking(self):
        """
        Delayed Stock Movement Guard (طلبيات تواصي):
        If order is an advance deposit, keep picking in 'waiting' / 'confirmed' state
        instead of immediately processing or validating stock deductions.
        """
        super()._create_order_picking()
        for order in self:
            if order.is_advance_deposit:
                for picking in order.picking_ids:
                    if picking.state not in ["done", "cancel"]:
                        picking.write({"state": "waiting"})

    def action_finalize_deposit_and_validate_stock(self):
        """
        Triggered when remaining balance is fully settled on Day 2:
        1. Validates stock picking (deducting stock from warehouse on handover day).
        2. Generates tax invoice & updates JoFotara status to 'submitted'.
        """
        for order in self:
            for picking in order.picking_ids:
                if picking.state not in ["done", "cancel"]:
                    picking.action_assign()
                    if picking.state == "assigned":
                        picking.button_validate()

            order.write({
                "is_advance_deposit": False,
                "jofotara_status": "submitted",
            })

            if not order.account_move:
                order.action_pos_order_invoice()

        return True
