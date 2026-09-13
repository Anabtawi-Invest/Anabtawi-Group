# -*- coding: utf-8 -*-
import base64
import secrets
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

SESSION_HOURS = 2
MAX_IMAGES = 15
MAX_IMAGE_SIZE = 8 * 1024 * 1024
ALLOWED_MIMETYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
}


class PosCakeUploadSession(models.Model):
    _name = "pos.cake.upload.session"
    _description = "Custom Cake Image Upload Session"
    _order = "id desc"

    token = fields.Char(required=True, index=True, copy=False, readonly=True)
    expiration_date = fields.Datetime(required=True, readonly=True)
    pos_config_id = fields.Many2one("pos.config", string="POS Config", readonly=True)
    pos_session_id = fields.Many2one("pos.session", string="POS Session", readonly=True)
    cake_order_id = fields.Many2one("pos.cake.order", string="Cake Order", readonly=True, copy=False)
    image_ids = fields.One2many("pos.cake.image", "session_id", string="Images")
    image_count = fields.Integer(compute="_compute_image_count")
    upload_url = fields.Char(compute="_compute_upload_url")
    qr_image = fields.Binary(string="QR Code", readonly=True, attachment=False)
    is_valid = fields.Boolean(compute="_compute_is_valid")

    _token_uniq = models.Constraint("unique(token)", "The upload token must be unique.")

    @api.depends("image_ids")
    def _compute_image_count(self):
        for session in self:
            session.image_count = len(session.image_ids)

    @api.depends("token")
    def _compute_upload_url(self):
        for session in self:
            session.upload_url = (
                f"{session.get_base_url()}/pos/custom_cake/upload/{session.token}"
                if session.token
                else False
            )

    @api.depends("expiration_date")
    def _compute_is_valid(self):
        now = fields.Datetime.now()
        for session in self:
            session.is_valid = bool(session.expiration_date and session.expiration_date > now)

    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        for vals in vals_list:
            vals.setdefault("token", secrets.token_urlsafe(32))
            vals.setdefault("expiration_date", now + timedelta(hours=SESSION_HOURS))
        sessions = super().create(vals_list)
        for session in sessions:
            session.qr_image = session._generate_qr_image()
        return sessions

    def _generate_qr_image(self):
        self.ensure_one()
        if not self.upload_url:
            return False
        qr_bytes = self.env["ir.actions.report"].barcode(
            "QR",
            self.upload_url,
            width=300,
            height=300,
        )
        return base64.b64encode(qr_bytes)

    @api.model
    def create_for_pos(self, pos_config_id=None, pos_session_id=None):
        session = self.sudo().create(
            {
                "pos_config_id": int(pos_config_id) if pos_config_id else False,
                "pos_session_id": int(pos_session_id) if pos_session_id else False,
            }
        )
        return session._prepare_pos_data()

    @api.model
    def get_by_token(self, token):
        if not token:
            return self.browse()
        return self.sudo().search([("token", "=", token)], limit=1)

    def _prepare_images_data(self):
        self.ensure_one()
        return [
            {
                "id": image.id,
                "name": image.name or _("Cake photo"),
                "url": f"/web/image/pos.cake.image/{image.id}/image",
            }
            for image in self.image_ids.sorted("id")
        ]

    def _prepare_pos_data(self):
        self.ensure_one()
        qr_image = self.qr_image
        if isinstance(qr_image, bytes):
            qr_image = qr_image.decode()
        return {
            "id": self.id,
            "token": self.token,
            "upload_url": self.upload_url,
            "qr_image": qr_image or False,
            "expiration_date": fields.Datetime.to_string(self.expiration_date),
            "is_valid": self.is_valid,
            "images": self._prepare_images_data(),
        }

    def attach_to_order(self, order):
        self.ensure_one()
        if self.image_ids:
            self.image_ids.write({"order_id": order.id})
        self.cake_order_id = order.id
        order.upload_session_id = self.id
        return True

    def add_uploaded_file(self, uploaded_file):
        self.ensure_one()
        if not self.is_valid:
            raise ValidationError(_("This upload link has expired."))
        if len(self.image_ids) >= MAX_IMAGES:
            raise ValidationError(_("You can upload a maximum of %s photos.") % MAX_IMAGES)
        if not uploaded_file:
            raise ValidationError(_("Please select a photo."))

        filename = uploaded_file.filename or "cake.jpg"
        mimetype = (uploaded_file.mimetype or "").lower()
        content = uploaded_file.read()
        if not content:
            raise ValidationError(_("The selected file is empty."))
        if len(content) > MAX_IMAGE_SIZE:
            raise ValidationError(_("The photo is too large. Maximum size is 8 MB."))
        if mimetype and mimetype not in ALLOWED_MIMETYPES:
            raise ValidationError(_("Please upload a JPG, PNG, WEBP, or GIF photo."))
        try:
            image = self.env["pos.cake.image"].sudo().create(
                {
                    "session_id": self.id,
                    "order_id": self.cake_order_id.id if self.cake_order_id else False,
                    "name": filename,
                    "image": base64.b64encode(content),
                }
            )
        except (UserError, ValueError, ValidationError) as err:
            raise ValidationError(_("The selected file is not a valid image.")) from err
        return image

    def remove_image(self, image_id):
        self.ensure_one()
        if not self.is_valid:
            raise ValidationError(_("This upload link has expired."))
        image = self.image_ids.filtered(lambda img: img.id == int(image_id))
        if not image:
            raise ValidationError(_("Photo not found."))
        image.unlink()
        return True


class PosCakeImage(models.Model):
    _name = "pos.cake.image"
    _description = "Custom Cake Image"
    _order = "id desc"

    name = fields.Char(string="Name")
    image = fields.Image(string="Image", required=True, max_width=1920, max_height=1920)
    session_id = fields.Many2one(
        "pos.cake.upload.session",
        string="Upload Session",
        ondelete="set null",
        index=True,
    )
    order_id = fields.Many2one(
        "pos.cake.order",
        string="Cake Order",
        ondelete="cascade",
        index=True,
    )
