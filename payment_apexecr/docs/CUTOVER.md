# Mock to Apex UAT/Production Cutover

## 1) Configuration Switch Only
- Keep module code unchanged.
- Update POS payment method:
  - `ApexECR Endpoint URL` => Apex UAT/Prod endpoint
  - `Apex MID`
  - `Apex TID`
  - `Apex Merchant Secure Key`
  - `ECR Currency Code`

## 2) Validation Matrix
- Sale approved
- Sale declined
- Refund approved
- Refund declined
- Unknown result followed by successful reconciliation (`EnquiryByRef`)
- Duplicate reference/idempotent retry behavior

## 3) Production Readiness
- Restrict access to Apex credentials (POS manager only).
- Review `ApexECR Logs` for redaction and operational diagnostics.
- Confirm cron `ApexECR Reconcile Pending POS Payments` is active.

