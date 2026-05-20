from odoo import models, fields, api
from odoo.exceptions import ValidationError


class CustomerImportWizard(models.TransientModel):
    _name = 'customer.import.wizard'
    _description = 'Quick Customer Import Wizard'

    department = fields.Selection(
        selection=[
            ('export', 'Export Sales Customers'),
            ('local', 'Local Sales Customers'),
            ('procurement', 'Procurement Vendors'),
            ('pos', 'POS Customers'),
        ],
        string='Department',
        required=True,
        help='Select which department this import is for'
    )

    excel_file = fields.Binary(
        string='Excel File',
        required=True,
        help='Upload Excel file with columns: Name, Mobile, Email (optional), Phone (optional), City (optional), Country (optional)'
    )

    filename = fields.Char(string='Filename')

    def action_import(self):
        """Create import record and process it"""
        timestamp = fields.Datetime.to_string(fields.Datetime.now())
        import_record = self.env['customer.import'].create({
            'name': f'{self.get_department_name()} - {timestamp}',
            'excel_file': self.excel_file,
            'filename': self.filename,
            'department': self.department,
        })

        # Validate and import
        import_record.action_validate_file()
        import_record.action_import_customers()

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'customer.import',
            'res_id': import_record.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def get_department_name(self):
        """Get friendly department name"""
        dept_map = {
            'export': 'Export Sales Customers',
            'local': 'Local Sales Customers',
            'procurement': 'Procurement Vendors',
            'pos': 'POS Customers',
        }
        return dept_map.get(self.department, 'Customers')
