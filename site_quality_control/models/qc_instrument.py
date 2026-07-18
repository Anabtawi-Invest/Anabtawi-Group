# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class QcInstrument(models.Model):
    """Measuring instrument (thermometer, scale, ...) with calibration
    tracking. Measures recorded with an overdue instrument are not accepted
    (ISO 22000 §8.7 control of monitoring and measuring)."""
    _name = "qc.instrument"
    _description = "QC Measuring Instrument"
    _inherit = ["mail.thread"]
    _order = "branch_id, name"

    name = fields.Char(string="Instrument", required=True, tracking=True)
    code = fields.Char(string="Code", tracking=True)
    instrument_type = fields.Selection(
        [
            ("thermometer", "Thermometer"),
            ("scale", "Scale"),
            ("ph_meter", "pH Meter"),
            ("other", "Other"),
        ],
        string="Type", default="thermometer", required=True,
    )
    serial_number = fields.Char(string="Serial Number")
    branch_id = fields.Many2one(
        "qc.branch", string="Site", required=True, tracking=True, index=True,
    )
    company_id = fields.Many2one(
        related="branch_id.company_id", store=True, index=True,
    )
    calibration_interval = fields.Integer(
        string="Calibration Interval (months)", default=12, required=True,
    )
    last_calibration_date = fields.Date(
        string="Last Calibration", compute="_compute_calibration_dates",
        store=True,
    )
    next_calibration_date = fields.Date(
        string="Next Calibration Due", compute="_compute_calibration_dates",
        store=True,
    )
    calibration_state = fields.Selection(
        [
            ("never", "Never Calibrated"),
            ("valid", "Valid"),
            ("due_soon", "Due Soon"),
            ("overdue", "Overdue"),
        ],
        string="Calibration Status", compute="_compute_calibration_state",
        search="_search_calibration_state",
    )
    calibration_ids = fields.One2many(
        "qc.instrument.calibration", "instrument_id",
        string="Calibration History",
    )
    active = fields.Boolean(default=True)
    note = fields.Text(string="Notes")

    @api.constrains("calibration_interval")
    def _check_interval(self):
        for instrument in self:
            if instrument.calibration_interval <= 0:
                raise ValidationError(
                    _("The calibration interval must be positive."))

    @api.depends("calibration_ids.date", "calibration_ids.result",
                 "calibration_interval")
    def _compute_calibration_dates(self):
        for instrument in self:
            passed = instrument.calibration_ids.filtered(
                lambda c: c.result == "pass").sorted("date", reverse=True)
            last = passed[:1].date if passed else False
            instrument.last_calibration_date = last
            instrument.next_calibration_date = (
                last + relativedelta(months=instrument.calibration_interval)
                if last else False)

    def _compute_calibration_state(self):
        today = fields.Date.context_today(self)
        for instrument in self:
            due = instrument.next_calibration_date
            if not due:
                instrument.calibration_state = "never"
            elif due < today:
                instrument.calibration_state = "overdue"
            elif due <= today + relativedelta(days=30):
                instrument.calibration_state = "due_soon"
            else:
                instrument.calibration_state = "valid"

    def _search_calibration_state(self, operator, value):
        today = fields.Date.context_today(self)
        soon = today + relativedelta(days=30)
        domains = {
            "never": [("next_calibration_date", "=", False)],
            "overdue": [("next_calibration_date", "!=", False),
                        ("next_calibration_date", "<", today)],
            "due_soon": [("next_calibration_date", ">=", today),
                         ("next_calibration_date", "<=", soon)],
            "valid": [("next_calibration_date", ">", soon)],
        }
        values = value if isinstance(value, (list, tuple)) else [value]
        domain = ["|"] * (len(values) - 1)
        for val in values:
            domain += domains.get(val, [(0, "=", 1)])
        if operator in ("!=", "not in"):
            return ["!"] + domain
        return domain

    def _is_usable(self):
        """An instrument is usable when it has a non-overdue calibration."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        return bool(self.next_calibration_date
                    and self.next_calibration_date >= today)

    # ------------------------------------------------------------------
    # Scheduled automation (cron)
    # ------------------------------------------------------------------
    @api.model
    def _cron_calibration_reminders(self):
        """Remind site managers 7 days before calibration is due, and for
        overdue instruments."""
        today = fields.Date.context_today(self)
        soon = today + relativedelta(days=7)
        instruments = self.search([
            "|",
            ("next_calibration_date", "=", False),
            ("next_calibration_date", "<=", soon),
        ])
        for instrument in instruments:
            user = (instrument.branch_id.manager_id
                    or instrument.branch_id.inspector_id)
            if not user:
                continue
            has_activity = instrument.activity_ids.filtered(
                lambda a: a.user_id == user)
            if has_activity:
                continue
            instrument.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=user.id,
                summary=_("Instrument calibration required"),
                note=_("Instrument %(name)s (%(site)s) needs calibration "
                       "(due: %(due)s).") % {
                    "name": instrument.name,
                    "site": instrument.branch_id.name,
                    "due": instrument.next_calibration_date or _("never calibrated"),
                },
            )
        return True


class QcInstrumentCalibration(models.Model):
    _name = "qc.instrument.calibration"
    _description = "Instrument Calibration Record"
    _order = "date desc, id desc"

    instrument_id = fields.Many2one(
        "qc.instrument", string="Instrument",
        required=True, ondelete="cascade", index=True,
    )
    company_id = fields.Many2one(
        related="instrument_id.company_id", store=True, index=True,
    )
    date = fields.Date(
        string="Calibration Date", required=True,
        default=fields.Date.context_today,
    )
    performed_by = fields.Char(
        string="Performed By",
        help="Technician or external calibration laboratory.",
    )
    result = fields.Selection(
        [("pass", "Passed"), ("fail", "Failed")],
        string="Result", required=True, default="pass",
    )
    certificate = fields.Binary(string="Certificate", attachment=True)
    certificate_name = fields.Char(string="Certificate Filename")
    note = fields.Text(string="Notes")
