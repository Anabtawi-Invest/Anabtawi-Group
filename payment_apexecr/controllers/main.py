# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request


class ApexEcrController(http.Controller):
    @http.route("/pos_apexecr/financial", type="json", auth="user")
    def pos_apexecr_financial(
        self,
        payment_method_id,
        amount,
        transaction_type,
        reference_number,
        invoice_number,
        orig_rrn=None,
        orig_auth_code=None,
    ):
        payment_method = request.env["pos.payment.method"].browse(int(payment_method_id)).exists()
        if not payment_method:
            return {"ok": False, "error": "Invalid payment method."}
        try:
            result = request.env["apexecr.client"].sudo().perform_financial(
                payment_method=payment_method,
                transaction_type=transaction_type,
                amount=amount,
                reference_number=reference_number,
                invoice_number=invoice_number,
                orig_rrn=orig_rrn,
                orig_auth_code=orig_auth_code,
            )
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "result": result}

    @http.route("/pos_apexecr/enquiry_by_ref", type="json", auth="user")
    def pos_apexecr_enquiry_by_ref(self, payment_method_id, reference_number):
        payment_method = request.env["pos.payment.method"].browse(int(payment_method_id)).exists()
        if not payment_method:
            return {"ok": False, "error": "Invalid payment method."}
        try:
            result = request.env["apexecr.client"].sudo().enquiry_by_ref(
                payment_method=payment_method,
                reference_number=reference_number,
            )
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "result": result}

