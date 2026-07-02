# Anabtawi Online Campaigns

Deployment bridge for the portable `online_campaigns_discount` engine.

Version 2 includes the portable dashboard, profitability, pivot/graph, and
aggregator settlement reconciliation features.

It requires the Anabtawi JoFotara POS fix from `D:\Anabtawi-Group-main.zip`
and creates editable Talabat, Careem, and MyThings aggregator records for the
main company. Commission percentages and accounting accounts intentionally
remain unset because they must match the current signed contracts and chart of
accounts.

Install `online_campaigns_discount`, copy/install
`anabtawi_jo_pos_refund_buyer` from the Anabtawi repository, then install this
module. Configure each aggregator before approving a campaign.
