# -*- coding: utf-8 -*-
import base64

from odoo import _, http
from odoo.exceptions import ValidationError
from odoo.http import request


class PosCustomCakeUploadController(http.Controller):

    def _get_session(self, token):
        return request.env["pos.cake.upload.session"].get_by_token(token)

    def _page_values(self, session, error=None, success=None):
        accept = (request.httprequest.headers.get("Accept-Language") or "").lower()
        is_rtl = accept.startswith("ar")
        lang = "ar_001" if is_rtl else "en_US"
        _lt = request.env(context={**request.env.context, "lang": lang})._
        labels = {
            "title": _lt("Upload Cake Photos"),
            "subtitle": _lt("Add photos of the cake design from your phone."),
            "add_photos": _lt("Add photos"),
            "upload": _lt("Upload"),
            "delete": _lt("Delete"),
            "no_photos": _lt("No photos uploaded yet."),
            "expired": _lt("This upload link has expired."),
            "expired_help": _lt("Ask the cashier to open the cake form again and scan a new QR code."),
            "formats": _lt("JPG, PNG, WEBP or GIF. Maximum 8 MB per photo."),
            "count": _lt("Photos"),
        }
        return {
            "request": request,
            "session": session,
            "images": session.image_ids.sorted("id") if session else request.env["pos.cake.image"],
            "is_valid": bool(session and session.is_valid),
            "error": error,
            "success": success,
            "labels": labels,
            "lang": "ar" if is_rtl else "en",
            "direction": "rtl" if is_rtl else "ltr",
            "token": session.token if session else "",
            "image_count": len(session.image_ids) if session else 0,
        }

    def _render_page(self, session, error=None, success=None):
        html = request.env["ir.ui.view"].sudo()._render_template(
            "pos_custom_cake.cake_upload_page",
            self._page_values(session, error=error, success=success),
        )
        return request.make_response(
            html,
            headers=[("Content-Type", "text/html; charset=utf-8")],
        )

    @http.route(
        "/pos/custom_cake/upload/<string:token>",
        type="http",
        auth="public",
        methods=["GET", "POST"],
        csrf=True,
        website=False,
    )
    def upload_page(self, token, **post):
        session = self._get_session(token)
        if not session:
            return self._render_page(session, error=_("This upload link is invalid."))
        if request.httprequest.method == "POST":
            if not session.is_valid:
                return request.redirect(f"/pos/custom_cake/upload/{token}")
            files = request.httprequest.files.getlist("images")
            if not files or all(not f.filename for f in files):
                return self._render_page(session, error=_("Please select at least one photo."))
            try:
                for uploaded in files:
                    if uploaded and uploaded.filename:
                        session.add_uploaded_file(uploaded)
            except ValidationError as err:
                return self._render_page(session, error=err.args[0] if err.args else str(err))
            return request.redirect(f"/pos/custom_cake/upload/{token}")
        return self._render_page(session)

    @http.route(
        "/pos/custom_cake/upload/<string:token>/delete/<int:image_id>",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=True,
        website=False,
    )
    def delete_upload_image(self, token, image_id, **post):
        session = self._get_session(token)
        if not session:
            return request.not_found()
        try:
            session.remove_image(image_id)
        except ValidationError:
            pass
        return request.redirect(f"/pos/custom_cake/upload/{token}")

    @http.route(
        "/pos/custom_cake/upload/<string:token>/image/<int:image_id>",
        type="http",
        auth="public",
        methods=["GET"],
        csrf=False,
        website=False,
    )
    def upload_image_content(self, token, image_id, **kwargs):
        session = self._get_session(token)
        if not session:
            return request.not_found()
        image = session.image_ids.filtered(lambda img: img.id == image_id)[:1]
        if not image or not image.image:
            return request.not_found()
        data = image.image
        if isinstance(data, str):
            data = base64.b64decode(data)
        elif isinstance(data, bytes):
            # stored as base64 bytes
            try:
                data = base64.b64decode(data)
            except Exception:
                pass
        return request.make_response(
            data,
            headers=[
                ("Content-Type", "image/jpeg"),
                ("Cache-Control", "private, max-age=300"),
            ],
        )

    @http.route("/pos/custom_cake/create_upload_session", type="jsonrpc", auth="user")
    def create_upload_session(self, data=None, **kwargs):
        payload = data if isinstance(data, dict) else kwargs
        return request.env["pos.cake.upload.session"].create_for_pos(
            pos_config_id=payload.get("pos_config_id"),
            pos_session_id=payload.get("pos_session_id"),
        )

    @http.route("/pos/custom_cake/get_upload_session", type="jsonrpc", auth="user")
    def get_upload_session(self, data=None, **kwargs):
        payload = data if isinstance(data, dict) else kwargs
        token = payload.get("token") or ""
        session = request.env["pos.cake.upload.session"].get_by_token(token)
        if not session:
            raise ValidationError(_("Upload session not found."))
        return session._prepare_pos_data()

    @http.route("/pos/custom_cake/delete_upload_image", type="jsonrpc", auth="user")
    def delete_upload_image_pos(self, data=None, **kwargs):
        payload = data if isinstance(data, dict) else kwargs
        token = payload.get("token") or ""
        image_id = int(payload.get("image_id") or 0)
        session = request.env["pos.cake.upload.session"].get_by_token(token)
        if not session:
            raise ValidationError(_("Upload session not found."))
        session.remove_image(image_id)
        return session._prepare_pos_data()
