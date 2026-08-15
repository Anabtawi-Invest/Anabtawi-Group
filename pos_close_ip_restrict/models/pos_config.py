import ipaddress
import re

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request


_IP_SPLIT_RE = re.compile(r"[\s,;]+")


class PosConfig(models.Model):
    _inherit = "pos.config"

    close_allowed_ips = fields.Text(
        string="Allowed Close IPs",
        help=(
            "Optional extra filter. On Odoo.sh, all devices on the same WiFi usually share "
            "one public IP, so this cannot block a cashier's phone in the shop. "
            "Use Allowed Close Devices for that. Leave empty to skip the IP check."
        ),
    )
    close_allowed_device_ids = fields.One2many(
        "pos.close.allowed.device",
        "config_id",
        string="Allowed Close Devices",
        help=(
            "POS computers or tablets that may close this session. "
            "Open the POS on that device as a manager and choose "
            "'Allow this device to close'. A phone is a different device "
            "even on the same network. Leave empty to skip the device check."
        ),
    )
    current_client_ip = fields.Char(
        string="Your Current IP",
        compute="_compute_current_client_ip",
        help="The IP address the server currently sees for this computer. Copy it into Allowed Close IPs.",
    )

    def _compute_current_client_ip(self):
        client_ip = self._get_request_ip() or ""
        for rec in self:
            rec.current_client_ip = client_ip

    @api.model
    def _get_request_ip(self):
        try:
            if not request:
                return False
            httprequest = request.httprequest
        except RuntimeError:
            return False
        forwarded = httprequest.headers.get("X-Forwarded-For") or ""
        if forwarded:
            return forwarded.split(",", 1)[0].strip() or False
        return httprequest.remote_addr or httprequest.environ.get("REMOTE_ADDR") or False

    def _iter_close_ip_tokens(self):
        self.ensure_one()
        raw = (self.close_allowed_ips or "").strip()
        if not raw:
            return []
        return [token for token in _IP_SPLIT_RE.split(raw) if token]

    def _parse_allowed_close_networks(self):
        self.ensure_one()
        networks = []
        for token in self._iter_close_ip_tokens():
            networks.append(self._token_to_network(token))
        return networks

    @staticmethod
    def _token_to_network(token):
        if "/" in token:
            return ipaddress.ip_network(token, strict=False)
        ip = ipaddress.ip_address(token)
        prefix = 32 if ip.version == 4 else 128
        return ipaddress.ip_network(f"{token}/{prefix}", strict=False)

    @api.constrains("close_allowed_ips")
    def _check_close_allowed_ips(self):
        for rec in self:
            for token in rec._iter_close_ip_tokens():
                try:
                    rec._token_to_network(token)
                except ValueError as err:
                    raise ValidationError(
                        _("Invalid IP or network %(token)s: %(error)s", token=token, error=err)
                    ) from err

    def _ip_is_allowed(self, client_ip, networks=None):
        self.ensure_one()
        networks = self._parse_allowed_close_networks() if networks is None else networks
        try:
            ip = ipaddress.ip_address(client_ip)
        except ValueError:
            return False
        candidates = [ip]
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            candidates.append(ip.ipv4_mapped)
        return any(
            candidate in network for candidate in candidates for network in networks
        )

    def _check_close_ip(self):
        """Return ``(allowed, client_ip, message)``.

        Empty IP list means no restriction. Missing HTTP request (tests / cron) is allowed.
        """
        self.ensure_one()
        networks = self._parse_allowed_close_networks()
        client_ip = self._get_request_ip() or ""
        if not networks:
            return True, client_ip, ""
        if not client_ip:
            return True, "", ""
        if self._ip_is_allowed(client_ip, networks):
            return True, client_ip, ""
        message = _(
            "You cannot close this register from this device (IP: %(ip)s).",
            ip=client_ip,
        )
        return False, client_ip, message

    def _get_close_device_token(self):
        token = self.env.context.get("close_device_token")
        if token in (None, False):
            return ""
        return str(token).strip()

    def _check_close_device(self):
        """Return ``(allowed, token, message)``. Empty device list means no restriction."""
        self.ensure_one()
        devices = self.close_allowed_device_ids
        token = self._get_close_device_token()
        if not devices:
            return True, token, ""
        if token and token in set(devices.mapped("device_token")):
            return True, token, ""
        return (
            False,
            token,
            _("You cannot close this register from this device."),
        )

    def _check_close_allowed(self):
        """Return ``(allowed, client_ip, device_token, message)``."""
        self.ensure_one()
        ip_allowed, client_ip, ip_message = self._check_close_ip()
        if not ip_allowed:
            return False, client_ip, self._get_close_device_token(), ip_message
        device_allowed, token, device_message = self._check_close_device()
        if not device_allowed:
            return False, client_ip, token, device_message
        return True, client_ip, token, ""

    def register_close_device(self, device_token, name=False):
        self.ensure_one()
        if not self.env.user.has_group("point_of_sale.group_pos_manager"):
            raise AccessError(_("Only a POS manager can allow a device to close the register."))
        token = (device_token or "").strip()
        if not token:
            raise UserError(_("Missing device token."))
        existing = self.close_allowed_device_ids.filtered(lambda d: d.device_token == token)
        if existing:
            return {
                "created": False,
                "id": existing[0].id,
                "name": existing[0].name,
            }
        device_name = (name or "").strip() or _("POS Device")
        device_name = _("%(name)s (%(code)s)", name=device_name, code=token[:8])
        device = self.env["pos.close.allowed.device"].sudo().create({
            "config_id": self.id,
            "device_token": token,
            "name": device_name,
        })
        return {
            "created": True,
            "id": device.id,
            "name": device.name,
        }
