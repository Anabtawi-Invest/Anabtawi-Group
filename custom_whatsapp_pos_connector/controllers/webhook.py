import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class WhatsAppWebhookController(http.Controller):
    @http.route(
        "/custom_whatsapp_pos/webhook",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
    )
    def verify_webhook(self, **kwargs):
        provider = request.env["ir.config_parameter"].sudo().get_param(
            "custom_whatsapp_pos_connector.provider", "meta"
        )
        if provider == "twilio":
            return request.make_response("OK")
        mode = kwargs.get("hub.mode")
        token = kwargs.get("hub.verify_token")
        challenge = kwargs.get("hub.challenge")
        verify_token = request.env["ir.config_parameter"].sudo().get_param(
            "custom_whatsapp_pos_connector.meta_verify_token"
        )
        if mode == "subscribe" and token and verify_token and token == verify_token:
            return request.make_response(challenge or "")
        return request.make_response("Verification failed", status=403)

    @http.route(
        "/custom_whatsapp_pos/webhook",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def receive_webhook(self, **kwargs):
        try:
            icp = request.env["ir.config_parameter"].sudo()
            provider = icp.get_param("custom_whatsapp_pos_connector.provider", "meta")
            whatsapp_model = request.env["whatsapp.pos.order"].sudo()
            form_payload = dict(request.params or {})

            # Auto-detect Twilio payload to avoid relying only on settings value.
            is_twilio_payload = bool(
                (form_payload.get("MessageSid") or form_payload.get("SmsSid"))
                and form_payload.get("From")
            )

            if provider == "twilio" or is_twilio_payload:
                whatsapp_model._log_debug(
                    "twilio.webhook.controller",
                    "info",
                    "Webhook request received",
                    {
                        "provider_setting": provider,
                        "is_twilio_payload": is_twilio_payload,
                        "from": form_payload.get("From"),
                        "sid": form_payload.get("MessageSid") or form_payload.get("SmsSid"),
                        "body": form_payload.get("Body"),
                    },
                )
                _logger.info(
                    "Twilio webhook received: keys=%s from=%s sid=%s",
                    list(form_payload.keys()),
                    form_payload.get("From"),
                    form_payload.get("MessageSid") or form_payload.get("SmsSid"),
                )
                whatsapp_model.receive_twilio_webhook_payload(form_payload)
                return request.make_response(
                    "<?xml version='1.0' encoding='UTF-8'?><Response></Response>",
                    headers=[("Content-Type", "text/xml; charset=utf-8")],
                    status=200,
                )

            raw_data = request.httprequest.data.decode("utf-8") if request.httprequest.data else "{}"
            try:
                payload = json.loads(raw_data or "{}")
            except Exception:
                payload = {}
            whatsapp_model._log_debug(
                "meta.webhook.controller",
                "info",
                "Webhook request received",
                payload,
            )
            whatsapp_model.receive_meta_webhook_payload(payload)
            return request.make_response("EVENT_RECEIVED", status=200)
        except Exception as error:
            _logger.exception("Webhook processing failed: %s", error)
            request.env["whatsapp.pos.order"].sudo()._log_debug(
                "webhook.controller",
                "error",
                f"Webhook processing failed: {error}",
                {"params": dict(request.params or {})},
            )
            # Keep Twilio delivery stable while logging real error server-side.
            return request.make_response(
                "<?xml version='1.0' encoding='UTF-8'?><Response></Response>",
                headers=[("Content-Type", "text/xml; charset=utf-8")],
                status=200,
            )
