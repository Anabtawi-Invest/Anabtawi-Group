import base64
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

UPLOAD_HOURS = 2
MAX_IMAGE_SIZE = 8 * 1024 * 1024
ALLOWED_MIMETYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}


class PosExpenseUpload(models.Model):
    _name = "pos.expense.upload"
    _description = "POS Expense Receipt Upload"
    _order = "id desc"

    token = fields.Char(required=True, index=True, copy=False, readonly=True)
    expiration_date = fields.Datetime(required=True, readonly=True)
    session_id = fields.Many2one("pos.session", required=True, readonly=True, ondelete="cascade")
    image = fields.Image(max_width=1920, max_height=1920)
    image_256 = fields.Image(string="Thumbnail", related="image", max_width=256, max_height=256, store=True)
    is_valid = fields.Boolean(compute="_compute_is_valid")

    _token_uniq = models.Constraint("unique(token)", "The upload token must be unique.")

    @api.depends("expiration_date")
    def _compute_is_valid(self):
        now = fields.Datetime.now()
        for upload in self:
            upload.is_valid = bool(upload.expiration_date and upload.expiration_date > now)

    @api.model_create_multi
    def create(self, vals_list):
        expiration = fields.Datetime.now() + timedelta(hours=UPLOAD_HOURS)
        for vals in vals_list:
            vals.setdefault("token", secrets.token_urlsafe(32))
            vals.setdefault("expiration_date", expiration)
        return super().create(vals_list)

    @api.model
    def get_by_token(self, token):
        if not token:
            return self.browse()
        return self.sudo().search([("token", "=", token)], limit=1)

    def get_upload_url(self):
        self.ensure_one()
        return f"{self.get_base_url()}/pos/expense/upload/{self.token}"

    def _prepare_pos_data(self):
        self.ensure_one()
        qr_bytes = self.env["ir.actions.report"].barcode("QR", self.get_upload_url(), width=300, height=300)
        return {
            "token": self.token,
            "upload_url": self.get_upload_url(),
            "qr_image": base64.b64encode(qr_bytes).decode(),
            **self._prepare_status_data(),
        }

    def _prepare_status_data(self):
        self.ensure_one()
        thumbnail = self.image_256
        if isinstance(thumbnail, bytes):
            thumbnail = thumbnail.decode()
        return {
            "is_valid": self.is_valid,
            "has_image": bool(self.image),
            "image_thumbnail": thumbnail or False,
        }

    def set_uploaded_file(self, uploaded_file):
        self.ensure_one()
        if not self.is_valid:
            raise ValidationError(_("This upload link has expired."))
        if not uploaded_file or not uploaded_file.filename:
            raise ValidationError(_("Please select a photo."))
        mimetype = (uploaded_file.mimetype or "").lower()
        content = uploaded_file.read()
        if not content:
            raise ValidationError(_("The selected file is empty."))
        if len(content) > MAX_IMAGE_SIZE:
            raise ValidationError(_("The photo is too large. Maximum size is 8 MB."))
        if mimetype and mimetype not in ALLOWED_MIMETYPES:
            raise ValidationError(_("Please upload a JPG, PNG, WEBP or GIF photo."))
        try:
            self.sudo().image = base64.b64encode(content)
        except (UserError, ValueError) as err:
            raise ValidationError(_("The selected file is not a valid image.")) from err

    @api.autovacuum
    def _gc_expired_uploads(self):
        limit = fields.Datetime.now() - timedelta(days=1)
        self.sudo().search([("expiration_date", "<", limit)]).unlink()
