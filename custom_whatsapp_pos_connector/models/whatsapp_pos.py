import json
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class WhatsappPosConversation(models.Model):
    _name = "whatsapp.pos.conversation"
    _description = "WhatsApp POS Conversation"

    phone_number = fields.Char(required=True, index=True)
    partner_id = fields.Many2one("res.partner", ondelete="set null")
    state = fields.Selection(
        [
            ("idle", "Idle"),
            ("awaiting_product", "Awaiting Product"),
            ("awaiting_quantity", "Awaiting Quantity"),
            ("awaiting_next_action", "Awaiting Next Action"),
        ],
        default="idle",
        required=True,
    )
    selected_product_id = fields.Many2one("product.product", ondelete="set null")
    cart_json = fields.Text(default="[]")
    last_message_at = fields.Datetime()

    _sql_constraints = [
        ("phone_unique", "unique(phone_number)", "Phone conversation already exists."),
    ]

    def get_cart_lines(self):
        self.ensure_one()
        try:
            data = json.loads(self.cart_json or "[]")
        except Exception:
            data = []
        return data if isinstance(data, list) else []

    def set_cart_lines(self, lines):
        self.ensure_one()
        self.cart_json = json.dumps(lines or [])


class WhatsappPosMessageLog(models.Model):
    _name = "whatsapp.pos.message.log"
    _description = "WhatsApp Incoming Message Log"
    _order = "id desc"

    meta_message_id = fields.Char(required=True, index=True)
    phone_number = fields.Char(required=True)
    payload = fields.Text()

    _sql_constraints = [
        ("meta_message_id_unique", "unique(meta_message_id)", "Message already processed."),
    ]


class WhatsappPosOrder(models.Model):
    _name = "whatsapp.pos.order"
    _description = "WhatsApp POS Order"
    _inherit = ["mail.thread"]
    _order = "id desc"

    name = fields.Char(default="New", readonly=True, copy=False)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    partner_id = fields.Many2one("res.partner", required=True, tracking=True)
    phone_number = fields.Char(required=True, tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("ready_for_pos", "Ready For POS"),
            ("loaded", "Loaded in POS"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    line_ids = fields.One2many("whatsapp.pos.order.line", "order_id", copy=True)
    pos_config_id = fields.Many2one("pos.config", tracking=True)
    pos_session_id = fields.Many2one("pos.session", tracking=True)
    total_amount = fields.Float(compute="_compute_total_amount", store=True)
    source_channel = fields.Selection(
        [("whatsapp", "WhatsApp")], default="whatsapp", required=True
    )
    note = fields.Text()

    @api.depends("line_ids.subtotal")
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = sum(rec.line_ids.mapped("subtotal"))

    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = seq.next_by_code("whatsapp.pos.order") or "WA-ORDER"
        return super().create(vals_list)

    def action_mark_loaded(self, pos_session_id=False):
        for rec in self:
            values = {"state": "loaded"}
            if pos_session_id:
                values["pos_session_id"] = pos_session_id
            rec.write(values)
        return True

    @api.model
    def mark_order_loaded(self, order_id, pos_session_id=False):
        order = self.browse(int(order_id))
        if not order.exists():
            return False
        order.action_mark_loaded(pos_session_id=pos_session_id or False)
        return True

    @api.model
    def fetch_pending_for_pos(self, pos_config_id=False, limit=10):
        domain = [("state", "=", "ready_for_pos"), ("company_id", "=", self.env.company.id)]
        if pos_config_id:
            domain += [("pos_config_id", "in", [False, int(pos_config_id)])]
        orders = self.search(domain, order="id asc", limit=limit)
        return [order._serialize_for_pos() for order in orders]

    def _serialize_for_pos(self):
        self.ensure_one()
        return {
            "id": self.id,
            "name": self.name,
            "phone_number": self.phone_number,
            "partner_id": self.partner_id.id,
            "partner_name": self.partner_id.name,
            "total_amount": self.total_amount,
            "pos_config_id": self.pos_config_id.id if self.pos_config_id else False,
            "line_ids": [
                {
                    "id": line.id,
                    "product_id": line.product_id.id,
                    "product_name": line.product_id.display_name,
                    "qty": line.qty,
                    "price_unit": line.price_unit,
                }
                for line in self.line_ids
            ],
        }

    @api.model
    def receive_meta_webhook_payload(self, payload):
        if not self._is_webhook_enabled():
            return {"status": "disabled"}

        entries = payload.get("entry", []) if isinstance(payload, dict) else []
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                for message in messages:
                    self._process_single_incoming_message(message)
        return {"status": "ok"}

    @api.model
    def receive_twilio_webhook_payload(self, payload):
        if not self._is_webhook_enabled():
            return {"status": "disabled"}
        message_sid = payload.get("MessageSid") or payload.get("SmsSid")
        incoming_phone = payload.get("From")
        body = payload.get("Body", "")
        if not message_sid or not incoming_phone:
            return {"status": "ignored"}
        phone = self._normalize_twilio_phone(incoming_phone)
        pseudo_message = {
            "id": message_sid,
            "from": phone,
            "type": "text",
            "text": {"body": body},
        }
        self._process_single_incoming_message(pseudo_message)
        return {"status": "ok"}

    @api.model
    def _process_single_incoming_message(self, message):
        phone = message.get("from")
        msg_id = message.get("id")
        if not phone or not msg_id:
            return

        if self.env["whatsapp.pos.message.log"].sudo().search_count(
            [("meta_message_id", "=", msg_id)]
        ):
            return

        self.env["whatsapp.pos.message.log"].sudo().create(
            {
                "meta_message_id": msg_id,
                "phone_number": phone,
                "payload": json.dumps(message),
            }
        )

        conversation = self._get_or_create_conversation(phone)
        conversation.last_message_at = fields.Datetime.now()

        text_value = self._extract_text_message(message)
        action_id = self._extract_action_id(message)
        try:
            self._route_conversation_input(conversation, text_value, action_id)
        except Exception as error:
            _logger.exception("Failed to route incoming WhatsApp message: %s", error)
            self._send_text(
                conversation.phone_number,
                _("Sorry, we could not process your request now. Please send 'menu' again."),
            )

    @api.model
    def _route_conversation_input(self, conversation, text_value, action_id):
        lowered = (text_value or "").strip().lower()
        if not action_id and lowered:
            # Twilio usually delivers only plain text replies.
            if lowered.startswith("prod_"):
                action_id = lowered
            elif lowered.startswith("qty_"):
                action_id = lowered
            elif lowered in {"add_more", "submit_order", "cancel_order"}:
                action_id = lowered

        if lowered in {"menu", "start", "hi", "hello", "منيو", "ابدأ"}:
            self._send_product_menu(conversation)
            return

        if action_id and action_id.startswith("prod_"):
            try:
                product_id = int(action_id.split("_")[1])
            except Exception:
                self._send_text(conversation.phone_number, _("Invalid product selection."))
                return
            product = self.env["product.product"].browse(product_id)
            if not product.exists():
                self._send_text(conversation.phone_number, _("Selected product not found."))
                return
            conversation.write(
                {"selected_product_id": product.id, "state": "awaiting_quantity"}
            )
            self._send_quantity_prompt(conversation, product)
            return

        if action_id and action_id.startswith("qty_"):
            qty_token = action_id.split("_")[1]
            if qty_token == "other":
                self._send_text(
                    conversation.phone_number,
                    _("Please send quantity as a number, for example: 2"),
                )
                return
            quantity = int(qty_token)
            self._add_current_selection_to_cart(conversation, quantity)
            return

        if action_id == "add_more":
            self._send_product_menu(conversation)
            return

        if action_id == "submit_order":
            self._finalize_whatsapp_order(conversation)
            return

        if action_id == "cancel_order":
            conversation.write({"state": "idle", "selected_product_id": False, "cart_json": "[]"})
            self._send_text(conversation.phone_number, _("Order cancelled. Send 'menu' to start again."))
            return

        if conversation.state == "awaiting_quantity" and lowered.isdigit():
            qty_value = int(lowered)
            if qty_value <= 0:
                self._send_text(conversation.phone_number, _("Quantity must be greater than zero."))
                return
            self._add_current_selection_to_cart(conversation, qty_value)
            return

        self._send_text(
            conversation.phone_number,
            _("Send 'menu' to browse products and place your order."),
        )

    @api.model
    def _add_current_selection_to_cart(self, conversation, qty):
        product = conversation.selected_product_id
        if not product:
            self._send_text(conversation.phone_number, _("Please pick a product first."))
            self._send_product_menu(conversation)
            return

        cart = conversation.get_cart_lines()
        existing = next((line for line in cart if line["product_id"] == product.id), None)
        if existing:
            existing["qty"] += qty
        else:
            cart.append(
                {
                    "product_id": product.id,
                    "name": product.display_name,
                    "qty": qty,
                    "price_unit": product.lst_price,
                }
            )
        conversation.set_cart_lines(cart)
        conversation.state = "awaiting_next_action"
        conversation.selected_product_id = False
        self._send_next_action_buttons(conversation)

    @api.model
    def _finalize_whatsapp_order(self, conversation):
        cart = conversation.get_cart_lines()
        if not cart:
            self._send_text(
                conversation.phone_number,
                _("Your cart is empty. Send 'menu' to choose products."),
            )
            return

        partner = conversation.partner_id or self._get_or_create_partner(conversation.phone_number)
        pos_config = self._find_target_pos_config()
        order_vals = {
            "partner_id": partner.id,
            "phone_number": conversation.phone_number,
            "state": "ready_for_pos",
            "pos_config_id": pos_config.id if pos_config else False,
            "line_ids": [
                (
                    0,
                    0,
                    {
                        "product_id": line["product_id"],
                        "qty": line["qty"],
                        "price_unit": line["price_unit"],
                    },
                )
                for line in cart
            ],
        }
        order = self.create(order_vals)
        self._notify_pos_new_order(order)

        conversation.write({"state": "idle", "selected_product_id": False, "cart_json": "[]"})
        self._send_text(
            conversation.phone_number,
            _("Order received. It has been sent to the POS session."),
        )

    @api.model
    def _get_or_create_conversation(self, phone):
        conv = self.env["whatsapp.pos.conversation"].sudo().search(
            [("phone_number", "=", phone)], limit=1
        )
        if conv:
            if not conv.partner_id:
                conv.partner_id = self._get_or_create_partner(phone).id
            return conv
        partner = self._get_or_create_partner(phone)
        return self.env["whatsapp.pos.conversation"].sudo().create(
            {
                "phone_number": phone,
                "partner_id": partner.id,
            }
        )

    @api.model
    def _get_or_create_partner(self, phone):
        partner = self.env["res.partner"].sudo().search(
            ["|", ("mobile", "=", phone), ("phone", "=", phone)],
            limit=1,
        )
        if partner:
            return partner
        return self.env["res.partner"].sudo().create(
            {"name": f"WhatsApp {phone}", "mobile": phone}
        )

    @api.model
    def _find_target_pos_config(self):
        icp = self.env["ir.config_parameter"].sudo()
        default_config_id = icp.get_param("custom_whatsapp_pos_connector.default_pos_config_id")
        pos_config = False
        if default_config_id:
            pos_config = self.env["pos.config"].browse(int(default_config_id)).exists()
        if not pos_config:
            opened_session = self.env["pos.session"].search(
                [("state", "=", "opened"), ("company_id", "=", self.env.company.id)],
                order="id desc",
                limit=1,
            )
            pos_config = opened_session.config_id if opened_session else False
        return pos_config

    @api.model
    def _notify_pos_new_order(self, order):
        payload = order._serialize_for_pos()
        self.env["bus.bus"]._sendone(
            "custom_whatsapp_pos_orders",
            "custom_whatsapp_pos_new_order",
            payload,
        )

    @api.model
    def _send_product_menu(self, conversation):
        products = self.env["product.product"]
        try:
            products = self.env["product.product"].search(
                [("available_in_pos", "=", True), ("sale_ok", "=", True), ("active", "=", True)],
                limit=3,
            )
        except Exception:
            # Fallback for databases where POS availability lives only on templates/custom schema.
            templates = self.env["product.template"].search(
                [("available_in_pos", "=", True), ("sale_ok", "=", True), ("active", "=", True)],
                limit=3,
            )
            products = templates.mapped("product_variant_id")
        if not products:
            self._send_text(
                conversation.phone_number,
                _("No POS products available now. Please try later."),
            )
            return
        buttons = []
        for product in products:
            buttons.append({"id": f"prod_{product.id}", "title": product.display_name[:20]})
        conversation.state = "awaiting_product"
        self._send_buttons(
            conversation.phone_number,
            _("Please choose a product from the menu:"),
            buttons,
        )

    @api.model
    def _send_quantity_prompt(self, conversation, product):
        self._send_buttons(
            conversation.phone_number,
            _("Select quantity for %s") % product.display_name,
            [
                {"id": "qty_1", "title": "1"},
                {"id": "qty_2", "title": "2"},
                {"id": "qty_other", "title": _("Other")},
            ],
        )

    @api.model
    def _send_next_action_buttons(self, conversation):
        cart = conversation.get_cart_lines()
        lines_text = "\n".join([f"- {line['name']} x {line['qty']}" for line in cart])
        message = _("Cart updated:\n%s\n\nChoose next action:") % lines_text
        self._send_buttons(
            conversation.phone_number,
            message[:1024],
            [
                {"id": "add_more", "title": _("Add More")},
                {"id": "submit_order", "title": _("Submit")},
                {"id": "cancel_order", "title": _("Cancel")},
            ],
        )

    @api.model
    def _send_text(self, phone_number, body):
        provider = self._get_provider()
        if provider == "twilio":
            self._send_twilio_text(phone_number, body)
            return
        self._send_meta_message(
            {
                "messaging_product": "whatsapp",
                "to": phone_number,
                "type": "text",
                "text": {"body": body},
            }
        )

    @api.model
    def _send_buttons(self, phone_number, body, buttons):
        provider = self._get_provider()
        if provider == "twilio":
            instruction = body
            for button in buttons[:3]:
                instruction += f"\n- {button['title']}: {button['id']}"
            self._send_twilio_text(phone_number, instruction)
            return
        payload_buttons = []
        for item in buttons[:3]:
            payload_buttons.append(
                {"type": "reply", "reply": {"id": item["id"], "title": item["title"][:20]}}
            )
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body[:1024]},
                "action": {"buttons": payload_buttons},
            },
        }
        self._send_meta_message(payload)

    @api.model
    def _send_meta_message(self, payload):
        phone_number_id = self._get_param("custom_whatsapp_pos_connector.meta_phone_number_id")
        access_token = self._get_param("custom_whatsapp_pos_connector.meta_access_token")
        if not phone_number_id or not access_token:
            _logger.warning("WhatsApp Meta settings are incomplete, outgoing message skipped.")
            return False
        url = f"https://graph.facebook.com/v22.0/{phone_number_id}/messages"
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=20)
            if response.status_code >= 400:
                _logger.warning("Meta message send failed: %s", response.text)
                return False
            return True
        except Exception as error:
            _logger.exception("Meta message send exception: %s", error)
            return False

    @api.model
    def _send_twilio_text(self, phone_number, body):
        account_sid = self._get_param("custom_whatsapp_pos_connector.twilio_account_sid")
        auth_token = self._get_param("custom_whatsapp_pos_connector.twilio_auth_token")
        sender = self._get_param("custom_whatsapp_pos_connector.twilio_whatsapp_from")
        if not account_sid or not auth_token or not sender:
            _logger.warning("Twilio settings are incomplete, outgoing message skipped.")
            return False
        if not str(sender).strip().startswith("whatsapp:"):
            sender = f"whatsapp:{str(sender).strip()}"

        to_phone = self._ensure_twilio_whatsapp_to(phone_number)
        if not to_phone:
            return False

        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        data = {"From": sender, "To": to_phone, "Body": body}
        try:
            response = requests.post(url, data=data, auth=(account_sid, auth_token), timeout=20)
            if response.status_code >= 400:
                _logger.warning("Twilio message send failed: %s", response.text)
                return False
            return True
        except Exception as error:
            _logger.exception("Twilio message send exception: %s", error)
            return False

    @api.model
    def _extract_text_message(self, message):
        if message.get("type") == "text":
            return (message.get("text") or {}).get("body") or ""
        return ""

    @api.model
    def _extract_action_id(self, message):
        if message.get("type") == "interactive":
            interactive = message.get("interactive", {})
            if interactive.get("type") == "button_reply":
                return (interactive.get("button_reply") or {}).get("id")
            if interactive.get("type") == "list_reply":
                return (interactive.get("list_reply") or {}).get("id")
        if message.get("type") == "button":
            return (message.get("button") or {}).get("payload")
        return False

    @api.model
    def _get_param(self, key):
        return self.env["ir.config_parameter"].sudo().get_param(key)

    @api.model
    def _get_provider(self):
        return self._get_param("custom_whatsapp_pos_connector.provider") or "meta"

    @api.model
    def _is_webhook_enabled(self):
        return self._get_param("custom_whatsapp_pos_connector.webhook_enabled") != "False"

    @api.model
    def _normalize_twilio_phone(self, from_value):
        if not from_value:
            return ""
        value = from_value.strip()
        if value.startswith("whatsapp:"):
            value = value.split("whatsapp:", 1)[1]
        return value

    @api.model
    def _ensure_twilio_whatsapp_to(self, phone_number):
        if not phone_number:
            return False
        normalized = str(phone_number).strip()
        if normalized.startswith("whatsapp:"):
            return normalized
        return f"whatsapp:{normalized}"

    @api.model
    def action_send_test_menu(self, phone_number):
        if not phone_number:
            raise UserError(_("Phone number is required."))
        conv = self._get_or_create_conversation(phone_number)
        self._send_product_menu(conv)
        return True


class WhatsappPosOrderLine(models.Model):
    _name = "whatsapp.pos.order.line"
    _description = "WhatsApp POS Order Line"

    order_id = fields.Many2one("whatsapp.pos.order", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", required=True, ondelete="restrict")
    qty = fields.Float(default=1.0, required=True)
    price_unit = fields.Float(required=True)
    subtotal = fields.Float(compute="_compute_subtotal", store=True)

    @api.depends("qty", "price_unit")
    def _compute_subtotal(self):
        for rec in self:
            rec.subtotal = (rec.qty or 0.0) * (rec.price_unit or 0.0)
