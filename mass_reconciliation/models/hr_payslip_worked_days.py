import logging

from odoo import models

_logger = logging.getLogger(__name__)


class HrPayslipWorkedDays(models.Model):
    _inherit = "hr.payslip.worked_days"

    def _compute_amount(self):
        super()._compute_amount()
        for worked_days in self:
            payslip = worked_days.payslip_id
            if not payslip or not worked_days.work_entry_type_id:
                continue

            code = (worked_days.code or "").strip()
            if code not in ("LAT", "LATE", "Lateness", "L"):
                continue

            attendance_hours = sum(
                wd.number_of_hours
                for wd in payslip.worked_days_line_ids
                if not wd.work_entry_type_id.is_extra_hours
            ) or 1.0

            version = payslip.version_id
            contract_wage = version.contract_wage if version else 0.0
            hourly_rate = version.hourly_wage if payslip.wage_type == "hourly" and version else (contract_wage / attendance_hours)
            amount_rate = worked_days.work_entry_type_id.amount_rate

            _logger.warning(
                "[LatenessAmountTrace] payslip_id=%s payslip=%s employee_id=%s code=%s "
                "contract_wage=%s attendance_hours=%s amount_rate=%s number_of_hours=%s "
                "hourly_rate=%s is_paid=%s computed_amount=%s",
                payslip.id,
                payslip.display_name,
                payslip.employee_id.id if payslip.employee_id else False,
                code,
                contract_wage,
                attendance_hours,
                amount_rate,
                worked_days.number_of_hours or 0.0,
                hourly_rate,
                worked_days.is_paid,
                worked_days.amount,
            )
