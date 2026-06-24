# HR KPI Dashboard Module 

## Overview
The HR KPI Dashboard is a comprehensive Odoo 19 module that provides dynamic KPI tracking and analytics for Human Resources departments. It allows organizations to monitor key performance indicators across multiple dimensions.

## Features

### Core KPIs (Pre-configured)
1. **Employee Turnover Rate** - Percentage of employees who left during the period
2. **Total Workforce Cost** - Combined payroll, benefits, overtime, and expenses
3. **Workforce Cost by Business Unit** - Cost breakdown by department
4. **Revenue per Employee** - Total revenue divided by average headcount

### Architecture

#### Models
- `hr.kpi.category` - Organize KPIs by category
- `hr.kpi.definition` - Configure KPI metadata and calculations
- `hr.kpi.value` - Store individual KPI measurements
- `hr.kpi.snapshot` - Historical snapshots of KPI calculations
- `hr.kpi.engine` - Abstract engine for KPI calculations

#### Services
- `kpi.service` - Dashboard data retrieval and snapshot management

### Security
- **HR KPI User** - View-only access to KPI dashboard
- **HR KPI Manager** - Manage KPI definitions and create snapshots
- **HR KPI Director** - Full administrative access

## Installation

1. Place the module in your Odoo addons directory
2. Update the module list
3. Install the `soft_hr_kpi_dashboard` module
4. Access via HR → KPI Dashboard menu

## Usage

### Viewing Dashboard
1. Go to HR → KPI Dashboard → Dashboard
2. Select company and department filters
3. View current KPI metrics

### Managing KPIs
1. Go to HR → KPI Dashboard → Configuration → KPI Definitions
2. Create, edit, or deactivate KPI definitions
3. Configure calculation types and visualization options

### Creating Snapshots
1. Go to HR → KPI Dashboard → Monitoring → KPI Snapshots
2. Create new snapshot for a specific KPI
3. View historical data and trends

## Extending KPIs

To add custom KPI calculations:

```python
from soft_hr_kpi_dashboard.models.hr_kpi_engine import register_kpi

def calculate_custom_kpi(engine, company_id, department_id=None, period_date=None):
    # Your calculation logic here
    return calculated_value

# Register the KPI
register_kpi('custom_kpi_code', calculate_custom_kpi)
