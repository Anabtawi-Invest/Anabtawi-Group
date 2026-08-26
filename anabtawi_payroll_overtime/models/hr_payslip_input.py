def _get_employee_hourly_rate(self):
    self.ensure_one()
    payslip = self.payslip_id
    if not payslip:
        return 0.0

    # 1. Check if hourly wage contract
    if payslip.wage_type == "hourly":
        if hasattr(payslip, "version_id") and payslip.version_id and payslip.version_id.hourly_wage:
            return payslip.version_id.hourly_wage
        if payslip.contract_id and getattr(payslip.contract_id, "hourly_wage", False):
            return payslip.contract_id.hourly_wage

    # 2. Get monthly wage with fallbacks (Payslip -> Employee -> Contract -> Version)
    wage = 0.0
    if getattr(payslip, "wage", False):
        wage = payslip.wage
    elif payslip.employee_id and getattr(payslip.employee_id, "wage", False):
        wage = payslip.employee_id.wage
    elif payslip.contract_id and getattr(payslip.contract_id, "wage", False):
        wage = payslip.contract_id.wage
    elif hasattr(payslip, "version_id") and payslip.version_id and getattr(payslip.version_id, "contract_wage", False):
        wage = payslip.version_id.contract_wage

    return (wage / self._OVERTIME_FIXED_HOURS) if wage else 0.0
