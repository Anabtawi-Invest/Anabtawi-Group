# -*- coding: utf-8 -*-

import hashlib
import json
import secrets
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class BiometricDeviceBridge(models.Model):
    _name = "biometric.device.bridge"
    _description = "Biometric Device Bridge"
    _rec_name = "name"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    device_identifier = fields.Char(
        string="Device Identifier",
        help="Optional external identifier sent by the bridge agent.",
    )
    device_timezone = fields.Char(
        string="Device Timezone",
        default=lambda self: self.env.user.tz or "UTC",
        help="IANA timezone used by the biometric device or bridge agent, for example Asia/Amman.",
    )
    import_from_date = fields.Date(
        string="Import From Date",
        default=fields.Date.context_today,
        help="Ignore punches older than this date in the device local timezone.",
    )
    access_token = fields.Char(
        string="Bridge Token",
        required=True,
        copy=False,
        default=lambda self: self._generate_token(),
        readonly=True,
    )
    last_sync_at = fields.Datetime(string="Last Sync At", readonly=True)
    last_request_at = fields.Datetime(string="Last Request At", readonly=True)
    last_request_summary = fields.Char(string="Last Request Summary", readonly=True)
    log_ids = fields.One2many("zk.bridge.attendance.log", "device_id", string="Logs")
    log_count = fields.Integer(compute="_compute_log_count")

    _sql_constraints = [
        (
            "biometric_device_bridge_token_uniq",
            "unique(access_token)",
            "The bridge token must be unique.",
        ),
    ]

    @api.depends("log_ids")
    def _compute_log_count(self):
        for record in self:
            record.log_count = len(record.log_ids)

    @api.model
    def _generate_token(self):
        return secrets.token_urlsafe(24)

    def action_regenerate_token(self):
        for record in self:
            record.access_token = self._generate_token()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Bridge token updated"),
                "message": _("Update the local bridge agent with the new token before the next sync."),
                "type": "warning",
                "sticky": False,
            },
        }

    def action_view_logs(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Attendance Logs"),
            "res_model": "zk.bridge.attendance.log",
            "view_mode": "list,form",
            "domain": [("device_id", "=", self.id)],
            "context": {"default_device_id": self.id},
        }

    @api.model
    def get_device_from_token(self, token, device_identifier=None):
        if not token:
            return self.browse()

        domain = [("access_token", "=", token), ("active", "=", True)]
        if device_identifier:
            domain.append(("device_identifier", "in", [False, device_identifier]))
        return self.search(domain, limit=1)

    @api.model
    def _parse_bridge_datetime(self, value, device_timezone=None):
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            normalized = value.strip()
            if normalized.endswith("Z"):
                normalized = normalized[:-1] + "+00:00"
            parsed = datetime.fromisoformat(normalized)
        else:
            raise ValidationError(_("Invalid punch time: %s") % value)

        if not parsed.tzinfo:
            timezone_name = device_timezone or self.device_timezone or "UTC"
            try:
                parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
            except ZoneInfoNotFoundError as exc:
                raise ValidationError(_("Unknown device timezone: %s") % timezone_name) from exc

        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    @api.model
    def _make_import_key(self, device, device_user_id, punch_time, punch_type):
        raw_key = "%s|%s|%s|%s" % (
            device.id,
            device_user_id,
            punch_time.isoformat(),
            punch_type or "",
        )
        return hashlib.sha1(raw_key.encode("utf-8")).hexdigest()

    @api.model
    def _normalize_punch_values(self, item):
        device_user_id = item.get("device_user_id") or item.get("user_id") or item.get("employee_code")
        if device_user_id is None:
            raise ValidationError(_("Each record must include device_user_id, user_id, or employee_code."))

        punch_time = item.get("punch_time") or item.get("timestamp") or item.get("punch_at")
        if not punch_time:
            raise ValidationError(_("Each record must include punch_time, timestamp, or punch_at."))

        punch_type = item.get("punch_type") or item.get("type") or ""
        record_timezone = item.get("device_timezone") or item.get("timezone") or self.device_timezone or "UTC"
        return {
            "device_user_id": str(device_user_id),
            "punch_time": self._parse_bridge_datetime(punch_time, record_timezone),
            "punch_type": str(punch_type or ""),
            "device_timezone": record_timezone,
        }

    @api.model
    def _get_local_punch_date(self, punch_time, device_timezone):
        try:
            tzinfo = ZoneInfo(device_timezone or self.device_timezone or "UTC")
        except ZoneInfoNotFoundError as exc:
            raise ValidationError(_("Unknown device timezone: %s") % (device_timezone or self.device_timezone or "UTC")) from exc
        return punch_time.replace(tzinfo=timezone.utc).astimezone(tzinfo).date()

    @api.model
    def _apply_punch_to_attendance(self, employee, punch_time):
        attendance = self.env["hr.attendance"].search(
            [("employee_id", "=", employee.id), ("check_out", "=", False)],
            order="check_in desc, id desc",
            limit=1,
        )
        if attendance:
            if punch_time < attendance.check_in:
                attendance.check_in = punch_time
            elif punch_time > attendance.check_in:
                attendance.check_out = punch_time
            return attendance
        return self.env["hr.attendance"].create(
            {
                "employee_id": employee.id,
                "check_in": punch_time,
            }
        )

    def import_bridge_records(self, records, source="bridge_agent"):
        self.ensure_one()
        if not isinstance(records, list):
            raise ValidationError(_("The records payload must be a list."))

        log_model = self.env["zk.bridge.attendance.log"].sudo()
        employee_model = self.env["hr.employee"].sudo()
        results = {
            "received": len(records),
            "imported": 0,
            "duplicates": 0,
            "unmatched": 0,
            "errors": 0,
            "skipped_before_date": 0,
        }

        for item in records:
            payload_text = json.dumps(item, ensure_ascii=True, sort_keys=True)
            try:
                normalized = self._normalize_punch_values(item)
                local_punch_date = self._get_local_punch_date(
                    normalized["punch_time"], normalized["device_timezone"]
                )
                if self.import_from_date and local_punch_date < self.import_from_date:
                    results["skipped_before_date"] += 1
                    continue
                import_key = self._make_import_key(
                    self,
                    normalized["device_user_id"],
                    normalized["punch_time"],
                    normalized["punch_type"],
                )
                if log_model.search_count([("import_key", "=", import_key)]):
                    results["duplicates"] += 1
                    continue

                employee = employee_model.search(
                    [("device_id_num", "=", normalized["device_user_id"])],
                    limit=2,
                )
                if len(employee) > 1:
                    raise ValidationError(
                        _("More than one employee was found with biometric ID %s.")
                        % normalized["device_user_id"]
                    )

                attendance = False
                state = "unmatched"
                if employee:
                    attendance = self._apply_punch_to_attendance(employee, normalized["punch_time"])
                    state = "imported"
                    results["imported"] += 1
                else:
                    results["unmatched"] += 1

                log_model.create(
                    {
                        "device_id": self.id,
                        "employee_id": employee.id if employee else False,
                        "hr_attendance_id": attendance.id if attendance else False,
                        "device_user_id": normalized["device_user_id"],
                        "punch_time": normalized["punch_time"],
                        "punch_type": normalized["punch_type"],
                        "state": state,
                        "import_key": import_key,
                        "source": source,
                        "raw_payload": payload_text,
                    }
                )
            except Exception as exc:
                results["errors"] += 1
                fallback_user_id = str(item.get("device_user_id") or item.get("user_id") or item.get("employee_code") or "")
                fallback_time = fields.Datetime.now()
                import_key = self._make_import_key(self, fallback_user_id, fallback_time, "error-%s" % results["errors"])
                log_model.create(
                    {
                        "device_id": self.id,
                        "device_user_id": fallback_user_id or _("Unknown"),
                        "punch_time": fallback_time,
                        "state": "error",
                        "import_key": import_key,
                        "source": source,
                        "raw_payload": payload_text,
                        "error_message": str(exc),
                    }
                )

        self.sudo().write(
            {
                "last_request_at": fields.Datetime.now(),
                "last_sync_at": fields.Datetime.now() if results["imported"] else self.last_sync_at,
                "last_request_summary": _(
                    "Imported %(imported)s, duplicates %(duplicates)s, skipped %(skipped_before_date)s, unmatched %(unmatched)s, errors %(errors)s"
                )
                % results,
            }
        )
        return results
