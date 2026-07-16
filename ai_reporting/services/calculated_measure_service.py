from odoo import _, models
from odoo.exceptions import ValidationError


class AiReportingCalculatedMeasureService(models.AbstractModel):
    _name = "ai.reporting.calculated_measure_service"
    _description = "AI Reporting Calculated Measure Service"

    def compute(self, operation, operands):
        values = [float(value or 0.0) for value in operands]
        if operation == "add":
            return sum(values)
        if operation == "subtract":
            return (values[0] if values else 0.0) - (values[1] if len(values) > 1 else 0.0)
        if operation == "multiply":
            result = 1.0
            for value in values:
                result *= value
            return result
        if operation in ("divide", "ratio"):
            return 0.0 if len(values) < 2 or values[1] == 0 else values[0] / values[1]
        if operation == "percentage_change":
            return 0.0 if len(values) < 2 or values[1] == 0 else ((values[0] - values[1]) / values[1]) * 100.0
        if operation == "absolute_difference":
            return abs((values[0] if values else 0.0) - (values[1] if len(values) > 1 else 0.0))
        raise ValidationError(_("Unsupported calculation operation: %s") % operation)

    def apply_row_calculations(self, row, calculations):
        row = dict(row)
        for calculation in calculations or []:
            operands = [row.get(name, 0.0) for name in calculation.get("operands", [])]
            row[calculation.get("code")] = self.compute(calculation.get("operation"), operands)
        return row

