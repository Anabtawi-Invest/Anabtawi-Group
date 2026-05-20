# Customer Segmentation Module for Odoo 19

## Overview

This module provides department-based customer segmentation with unified bulk import functionality for Odoo 19. It allows organizations to manage different customer types (Export Sales, Local Sales, Procurement Vendors, and POS Customers) with role-based access control.

## Features

- **Department-Based Segmentation**: Automatically categorize customers/vendors by department
- **Access Control Rules**: Each department sees only their own customers
- **Bulk Excel Import**: Import customers from Excel files with department assignment
- **Duplicate Detection**: Automatically detects existing customers by mobile or email
- **Status Tracking**: Monitor import progress and identify errors
- **Group Management**: Built-in user groups for each department

## Installation

1. Download the module
2. Extract to your Odoo addons folder
3. Restart Odoo service
4. Update Apps (Admin → Apps → Update Apps List)
5. Search for "Customer Segmentation" and click Install
6. Ensure openpyxl is installed: `pip install openpyxl`

## Configuration

### Setting Up Departments

1. Go to Settings → Users & Companies → Users
2. Add users to their respective department groups:
   - **Export Sales Team**: For export customers
   - **Local Sales Team**: For local customers
   - **Procurement Department**: For vendors
   - **POS Team**: For POS customers

### Excel Import Format

Create Excel files with the following columns:
- **Name** (Required): Customer/Vendor name
- **Mobile** (Required): Mobile phone number
- **Email** (Optional): Email address
- **Phone** (Optional): Landline number
- **City** (Optional): City name
- **Country** (Optional): Country name

Example:
```
Name          | Mobile       | Email              | Phone        | City      | Country
John Smith    | +1234567890  | john@example.com   | +1098765432  | New York  | USA
ABC Company   | +9876543210  | info@abc.com       | +1111111111  | London    | UK
```

## Usage

### Import Customers

1. Go to Sales → Customer Segmentation → Import Customers/Vendors
2. Select the department (Export Sales, Local Sales, Procurement, or POS)
3. Upload the Excel file
4. Click "Import"
5. System validates the file and creates records

### View Segmented Customers

1. Go to Contacts → Customers
2. Use filters to see:
   - Export Customers
   - Local Customers
   - Vendors
   - POS Customers
3. Each user sees only their department's customers based on their group assignment

### Import History

1. Go to Sales → Customer Segmentation → Import History
2. View all past imports with status (Draft, Validated, Completed, Error)
3. Check import details and error messages

## Access Control

The module creates automatic record rules:

| Department | Can See | Can Edit | Can Delete |
|-----------|---------|----------|-----------|
| Export Sales Team | Export Customers only | Yes | No |
| Local Sales Team | Local Customers only | Yes | No |
| Procurement | Vendors only | Yes | No |
| POS Team | POS Customers only | Yes | No |
| Admin/Manager | All customers | Yes | Yes |

## Field Descriptions

### Partner Fields (res.partner)

- **is_export_customer**: Mark as export sales customer
- **is_local_customer**: Mark as local sales customer
- **is_vendor**: Mark as procurement vendor
- **is_pos_customer**: Mark as POS customer
- **department_category**: Auto-computed primary department (Read-only)

### Import Model Fields

- **Name**: Reference name for the import batch
- **Department**: Target department for this import
- **Excel File**: The uploaded Excel file
- **Status**: Draft → Validated → Completed
- **Import Lines**: Individual records from the file

## Troubleshooting

### "openpyxl library is required"
Install openpyxl: `pip install openpyxl`

### Duplicate Detection Not Working
Ensure mobile and email fields are correctly formatted in Excel and in existing records.

### Users Can't See Customers
- Verify user is assigned to correct department group
- Check that customers are tagged with correct department flag
- Admin users have access to all records

### Import File Validation Errors
- Check Excel file has required columns (Name, Mobile)
- Verify data is in correct rows (headers in row 1)
- Remove empty rows from Excel file

## Module Structure

```
customer_segmentation/
├── __manifest__.py           # Module manifest
├── __init__.py              # Module init
├── models/
│   ├── __init__.py
│   ├── res_partner.py       # Extended Partner model
│   └── customer_import.py    # Import models
├── wizards/
│   ├── __init__.py
│   └── customer_import_wizard.py  # Quick import wizard
├── views/
│   ├── res_partner_views.xml      # Partner view extensions
│   ├── customer_import_views.xml   # Import views
│   └── menu.xml                   # Menu definitions
├── security/
│   ├── ir_model_access.xml   # Model access rights
│   └── ir_rule.xml           # Record-level access rules
└── README.md                 # This file
```

## Development Notes

### Extending the Module

To add custom logic for specific departments:

```python
from odoo import models, fields

class CustomPartner(models.Model):
    _inherit = 'res.partner'
    
    # Add your custom fields
    custom_field = fields.Char(string='Custom Field')
    
    def create(self, vals_list):
        # Add custom logic
        return super().create(vals_list)
```

### Custom Validation Rules

Add validation in customer_import.py's `action_import_customers()` method:

```python
# Example: Custom validation for vendors
if self.department == 'procurement':
    # Add vendor-specific validation
    pass
```

## Support & License

This module is provided as-is. For issues or customization:
- Review Odoo 19 documentation
- Check module logs in Odoo Settings → Technical → Logs
- Contact your Odoo administrator

**License**: LGPL-3

## Version History

- **1.0.0** (Odoo 19.0): Initial release
  - Department-based segmentation
  - Bulk Excel import
  - Access control rules
  - Import history tracking
