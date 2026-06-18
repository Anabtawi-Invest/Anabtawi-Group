# ApexECR Contract (Mock and Real)

## Outbound Financial Request
- Root: `FinancialTxnRequest`
- Required nodes:
  - `Config/Tid`, `Config/Mid`, `Config/MerchantSecureKey`, `Config/EcrCurrencyCode`
  - `Printer/ReferenceNumber`, `Printer/InvoiceNumber`
  - `TransactionType` (`SALE` or `REFUND`)
  - `EcrAmount`
- Refund-only optional:
  - `OrigRrn`
  - `OrigAuthCode`

## Outbound Enquiry Request
- Root: `EnquiryByRefRequest`
- Required nodes:
  - `Config/*`
  - `Printer/ReferenceNumber`
  - `ReferenceNumber`

## Expected Response Mapping
- `WebResponseStatus`:
  - `Success` / `0` => web success
  - other => web failure
- `PosRespStatus`:
  - `1` => approved (`sync_state=done`)
  - `0` => declined (`sync_state=error`)
  - `-1` => unknown (`sync_state=pending`)

## Persisted Payment Fields
- `apexecr_reference_number`
- `apexecr_invoice_number`
- `apexecr_rrn`
- `apexecr_auth_code`
- `apexecr_response_code`
- `apexecr_response_text`
- `apexecr_web_status`
- `apexecr_pos_status`
- `apexecr_transaction_name`
- `apexecr_masked_pan`
- `apexecr_raw_response`
- `apexecr_sync_state`

