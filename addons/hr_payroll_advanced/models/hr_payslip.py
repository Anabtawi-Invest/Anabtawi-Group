# =====================================================
# SMART LEDGER MODE — AUTO OT + LAT ENGINE
# =====================================================

def _smart_ledger_update(self):

    for slip in self:

        employee = slip.employee_id

        # -----------------------------------
        # READ VALUES
        # -----------------------------------

        late_hours = slip.late_hours or 0.0
        ot_total_amount = slip.ot_total_amount or 0.0
        hour_rate = slip._get_hour_rate()

        if hour_rate <= 0:
            continue

        # -----------------------------------
        # ADD OT TO BANK
        # -----------------------------------

        ot_hours_generated = ot_total_amount / hour_rate if hour_rate else 0.0

        employee.overtime_bank_hours += ot_hours_generated
        employee.overtime_bank_amount += ot_total_amount

        # -----------------------------------
        # AUTO CONSUME LATENESS FROM OT BANK
        # -----------------------------------

        consume_ot = min(employee.overtime_bank_hours, late_hours)

        employee.overtime_bank_hours -= consume_ot
        employee.overtime_bank_amount -= (consume_ot * hour_rate)

        remaining_late = late_hours - consume_ot

        # -----------------------------------
        # WRITE INPUT FOR SALARY DEDUCTION
        # -----------------------------------

        salary_ded_amount = remaining_late * hour_rate

        slip._upsert_input("LAT_SAL_DED", -salary_ded_amount)
