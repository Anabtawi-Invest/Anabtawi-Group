import logging

from odoo import api, fields, models


_logger = logging.getLogger(__name__)


class HrAttendanceOvertimeLine(models.Model):
    _inherit = "hr.attendance.overtime.line"

    work_entry_type_id = fields.Many2one(
        "hr.work.entry.type",
        string="Work Entry Type",
        help="Used to convert overtime hours into credited hours for balances.",
    )
    credited_duration = fields.Float(
        string="Credited Extra Hours",
        compute="_compute_credited_duration",
        store=True,
        help="Extra hours after applying the selected work entry type rate.",
    )

    @api.depends("manual_duration", "work_entry_type_id", "work_entry_type_id.amount_rate")
    def _compute_credited_duration(self):
        for overtime in self:
            rate = overtime.work_entry_type_id.amount_rate or 1.0
            overtime.credited_duration = overtime.manual_duration * rate
            _logger.info(
                "[extra_hours_enhancement] Overtime line credit computed: "
                "line_id=%s employee=%s date=%s status=%s manual_duration=%s "
                "work_entry_type=%s rate=%s credited_duration=%s rules=%s",
                overtime.id or "new",
                overtime.employee_id.display_name,
                overtime.date,
                overtime.status,
                overtime.manual_duration,
                overtime.work_entry_type_id.code or overtime.work_entry_type_id.display_name or "N/A",
                rate,
                overtime.credited_duration,
                overtime.rule_ids.mapped("name"),
            )
