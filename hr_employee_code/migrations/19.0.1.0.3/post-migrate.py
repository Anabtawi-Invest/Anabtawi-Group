def migrate(cr, version):
    from odoo import SUPERUSER_ID, api

    env = api.Environment(cr, SUPERUSER_ID, {})
    employees = env["hr.employee"].sudo().search([("employee_number", "!=", False)])
    for employee in employees:
        partners = (employee.work_contact_id | employee.user_partner_id).exists()
        for partner in partners:
            partner.with_company(employee.company_id)._compute_employee_number()
