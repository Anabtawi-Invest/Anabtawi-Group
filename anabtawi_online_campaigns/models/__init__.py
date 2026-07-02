# Load concrete/table-backed models before SQL report models.
# This ensures Odoo creates the POS line campaign columns before the SQL view init() runs.
from . import online_aggregator
from . import online_campaign
from . import pos_order
from . import pos_session
from . import online_campaign_settlement
from . import online_campaign_report
