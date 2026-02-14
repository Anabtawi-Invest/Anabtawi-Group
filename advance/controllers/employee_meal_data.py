from odoo import http
from odoo.http import request

class EmployeeFreeData(http.Controller):

    @http.route('/pos/employee_free/data', type='jsonrpc', auth='user')
    def get_employee_free_data(self):

        # ------------------- Get POS Session -------------------
        session = request.env['pos.session'].sudo().search([
            ('user_id', '=', request.env.user.id),
            ('state', '=', 'opened'),
        ], limit=1)

        if not session:
            return {'error': 'No open POS session found'}

        company = session.company_id  # The correct active company


        # ------------------- Employees (filtered by company) -------------------
        employees = request.env['hr.employee'].sudo().search_read(
            [
                ('company_id', '=', company.id)
            ],
            fields=['id', 'name']
        )

        # Optional: remove duplicates by name inside same company (rare)
        unique_employees = {}
        for emp in employees:
            unique_employees[emp['name']] = emp

        employees = list(unique_employees.values())


        # ------------------- Products (filtered by company) -------------------
        allowed_categ_ids = request.env['pos.category'].sudo().search([
            ('is_employee_free_category', '=', True)
        ]).ids

        products = request.env['product.product'].sudo().search_read(
            [
                ('available_in_pos', '=', True),
                ('pos_categ_ids', 'in', allowed_categ_ids),
                ('company_id', 'in', [company.id, False]),
            ],
            fields=['id', 'display_name', 'lst_price', 'pos_categ_ids'],
        )


        return {
            'employees': employees,
            'products': products,
        }
