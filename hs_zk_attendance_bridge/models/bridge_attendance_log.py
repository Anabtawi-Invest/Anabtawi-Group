# -*- coding: utf-8 -*-

from odoo import fields, models


class BridgeAttendanceLog(models.Model):
    _name = "zk.bridge.attendance.log"
    _description = "Bridge Attendance Log"
    _order = "punch_time desc, id desc"

    device_id = fields.Many2one(
        "biometric.device.bridge",
        string="Device",
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="device_id.company_id",
        store=True,
        readonly=True,
    )
    employee_id = fields.Many2one("hr.employee", string="Employee", readonly=True)
    hr_attendance_id = fields.Many2one("hr.attendance", string="Attendance Entry", readonly=True)
    device_user_id = fields.Char(string="Device User ID", required=True, readonly=True)
    punch_time = fields.Datetime(string="Punch Time", required=True, readonly=True)
    punch_type = fields.Char(string="Punch Type", readonly=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("imported", "Imported"),
            ("duplicate", "Duplicate"),
            ("unmatched", "Unmatched Employee"),
            ("error", "Error"),
        ],
        default="draft",
        required=True,
        readonly=True,
    )
    import_key = fields.Char(string="Import Key", required=True, readonly=True, index=True)
    source = fields.Char(string="Source", readonly=True)
    error_message = fields.Char(string="Error", readonly=True)
    raw_payload = fields.Text(string="Raw Payload", readonly=True)

    _sql_constraints = [
        ("zk_bridge_attendance_log_import_key_uniq", "unique(import_key)", "This punch was already imported."),
    ]
