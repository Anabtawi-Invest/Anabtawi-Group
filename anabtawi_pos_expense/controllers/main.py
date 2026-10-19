from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request


class PosExpenseUploadController(http.Controller):

    def _labels(self):
        accept = (request.httprequest.headers.get("Accept-Language") or "").lower()
        is_rtl = accept.startswith("ar")
        lang = "ar_001" if is_rtl else "en_US"
        _lt = request.env(context={**request.env.context, "lang": lang})._
        labels = {
            "title": _lt("Expense Receipt Photo"),
            "subtitle": _lt("Take a photo of the expense receipt and upload it. It will appear on the cashier screen."),
            "choose": _lt("Take / choose photo"),
            "upload": _lt("Upload"),
            "replace_hint": _lt("Uploading again replaces the current photo."),
            "uploaded": _lt("Photo uploaded. You can go back to the cashier screen."),
            "expired": _lt("This upload link has expired or is not valid. Open the Expense popup again on the POS."),
            "formats": _lt("JPG, PNG, WEBP or GIF. Maximum 8 MB."),
            "no_file": _lt("Please select a photo."),
        }
        return labels, ("ar" if is_rtl else "en"), ("rtl" if is_rtl else "ltr")

    def _render(self, upload, error=None, success=None):
        labels, lang, direction = self._labels()
        html = request.env["ir.ui.view"].sudo()._render_template(
            "anabtawi_pos_expense.pos_expense_upload_page",
            {
                "request": request,
                "upload": upload,
                "is_valid": bool(upload and upload.is_valid),
                "thumbnail": upload._prepare_status_data()["image_thumbnail"] if upload else False,
                "error": error,
                "success": success,
                "labels": labels,
                "lang": lang,
                "direction": direction,
            },
        )
        return request.make_response(html, headers=[("Content-Type", "text/html; charset=utf-8")])

    @http.route(
        "/pos/expense/upload/<string:token>",
        type="http",
        auth="public",
        methods=["GET", "POST"],
        csrf=True,
        website=False,
    )
    def upload_page(self, token, **post):
        upload = request.env["pos.expense.upload"].get_by_token(token)
        if request.httprequest.method != "POST" or not upload or not upload.is_valid:
            return self._render(upload)
        uploaded = request.httprequest.files.get("image")
        if not uploaded or not uploaded.filename:
            return self._render(upload, error=self._labels()[0]["no_file"])
        try:
            upload.set_uploaded_file(uploaded)
        except ValidationError as err:
            return self._render(upload, error=err.args[0] if err.args else str(err))
        return self._render(upload, success=self._labels()[0]["uploaded"])
