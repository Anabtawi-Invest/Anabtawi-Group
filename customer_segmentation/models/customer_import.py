from odoo import models, fields, api
from odoo.exceptions import ValidationError
import base64
import io

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False


class CustomerImport(models.Model):
    _name = 'customer.import'
    _description = 'Customer Bulk Import'

    name = fields.Char(
        string='Import Name',
        required=True,
        help='Name/reference for this import batch'
    )
    excel_file = fields.Binary(
        string='Excel File',
        required=True,
        help='Upload Excel file with customer/vendor data'
    )
    filename = fields.Char(string='Filename')
    
    department = fields.Selection(
        selection=[
            ('export', 'Export Sales Customers'),
            ('local', 'Local Sales Customers'),
            ('procurement', 'Procurement Vendors'),
            ('pos', 'POS Customers'),
        ],
        string='Department',
        required=True,
        help='Select department this import belongs to'
    )

    import_status = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('validated', 'Validated'),
            ('completed', 'Completed'),
            ('error', 'Error'),
        ],
        string='Status',
        default='draft',
        readonly=True
    )

    import_lines = fields.One2many(
        'customer.import.line',
        'import_id',
        string='Import Lines',
        readonly=True
    )

    notes = fields.Text(
        string='Import Notes',
        readonly=True,
        help='System messages and validation notes'
    )

    @api.constrains('excel_file')
    def _check_excel_file(self):
        """Validate that file is provided"""
        if not self.excel_file:
            raise ValidationError('Please upload an Excel file')

    def action_validate_file(self):
        """Parse and validate the Excel file"""
        if not HAS_OPENPYXL:
            raise ValidationError('openpyxl library is required. Please install it.')

        try:
            # Decode the file
            excel_data = base64.b64decode(self.excel_file)
            excel_file = io.BytesIO(excel_data)
            
            # Load workbook
            workbook = openpyxl.load_workbook(excel_file)
            sheet = workbook.active

            # Extract headers
            headers = []
            for cell in sheet[1]:
                if cell.value:
                    headers.append(cell.value.lower().strip())

            # Validate required columns
            required_columns = ['name', 'mobile']
            missing = [col for col in required_columns if col not in headers]
            if missing:
                raise ValidationError(
                    f'Missing required columns: {", ".join(missing)}. '
                    f'Required: name, mobile. Optional: email, phone, city, country'
                )

            # Parse rows and create import lines
            import_lines = []
            notes = []
            row_num = 2

            for row in sheet.iter_rows(min_row=2, values_only=False):
                if not any(cell.value for cell in row):
                    continue

                row_data = {}
                for idx, header in enumerate(headers):
                    if idx < len(row):
                        row_data[header] = row[idx].value

                # Validate row
                if not row_data.get('name'):
                    notes.append(f'Row {row_num}: Skipped - missing name')
                    row_num += 1
                    continue

                if not row_data.get('mobile'):
                    notes.append(f'Row {row_num}: Skipped - missing mobile number')
                    row_num += 1
                    continue

                # Create import line
                import_line_vals = {
                    'import_id': self.id,
                    'row_number': row_num,
                    'name': row_data.get('name'),
                    'mobile': row_data.get('mobile'),
                    'email': row_data.get('email'),
                    'phone': row_data.get('phone'),
                    'city': row_data.get('city'),
                    'country': row_data.get('country'),
                    'status': 'ready',
                }
                import_lines.append((0, 0, import_line_vals))
                row_num += 1

            # Update import record
            self.import_lines = import_lines
            self.import_status = 'validated'
            self.notes = '\n'.join(notes) if notes else 'File validated successfully'

        except Exception as e:
            self.import_status = 'error'
            self.notes = f'Error reading Excel file: {str(e)}'
            raise ValidationError(f'Error processing Excel file: {str(e)}')

    def action_import_customers(self):
        """Import validated customers/vendors to res.partner"""
        if self.import_status != 'validated':
            raise ValidationError('Please validate the file first')

        Partner = self.env['res.partner']
        created_count = 0
        skipped_count = 0
        error_notes = []

        for line in self.import_lines:
            if line.status == 'skipped':
                skipped_count += 1
                continue

            try:
                # Check if customer already exists by mobile or email
                existing = Partner.search([
                    '|',
                    ('mobile', '=', line.mobile),
                    ('email', '=', line.email),
                ], limit=1)

                if existing:
                    line.status = 'duplicate'
                    error_notes.append(f'Row {line.row_number}: Customer already exists')
                    skipped_count += 1
                    continue

                # Prepare customer values based on department
                partner_vals = {
                    'name': line.name,
                    'mobile': line.mobile,
                    'email': line.email or False,
                    'phone': line.phone or False,
                    'city': line.city or False,
                    'country_id': self._get_country_id(line.country),
                    'is_company': False,
                    'type': 'contact',
                }

                # Set department-specific flags
                if self.department == 'export':
                    partner_vals['is_export_customer'] = True
                elif self.department == 'local':
                    partner_vals['is_local_customer'] = True
                elif self.department == 'procurement':
                    partner_vals['is_vendor'] = True
                    partner_vals['supplier_rank'] = 1
                elif self.department == 'pos':
                    partner_vals['is_pos_customer'] = True

                # Create partner
                partner = Partner.create(partner_vals)
                line.status = 'completed'
                line.partner_id = partner.id
                created_count += 1

            except Exception as e:
                line.status = 'error'
                error_notes.append(f'Row {line.row_number}: {str(e)}')
                skipped_count += 1

        self.import_status = 'completed'
        summary = f'Import completed: {created_count} customers created, {skipped_count} skipped'
        if error_notes:
            summary += '\n\nErrors:\n' + '\n'.join(error_notes)
        self.notes = summary

    def _get_country_id(self, country_name):
        """Get country ID by name"""
        if not country_name:
            return False
        country = self.env['res.country'].search([
            ('name', 'ilike', country_name)
        ], limit=1)
        return country.id if country else False


class CustomerImportLine(models.Model):
    _name = 'customer.import.line'
    _description = 'Customer Import Line'

    import_id = fields.Many2one(
        'customer.import',
        string='Import',
        required=True,
        ondelete='cascade'
    )
    row_number = fields.Integer(string='Row Number')
    
    name = fields.Char(string='Name', required=True)
    mobile = fields.Char(string='Mobile', required=True)
    email = fields.Char(string='Email')
    phone = fields.Char(string='Phone')
    city = fields.Char(string='City')
    country = fields.Char(string='Country')
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Created Customer',
        readonly=True
    )
    
    status = fields.Selection(
        selection=[
            ('ready', 'Ready'),
            ('completed', 'Completed'),
            ('duplicate', 'Duplicate'),
            ('error', 'Error'),
            ('skipped', 'Skipped'),
        ],
        string='Status',
        default='ready'
    )
    error_message = fields.Char(string='Error Message')
