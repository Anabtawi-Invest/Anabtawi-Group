# ApexECR Mock Server Usage

## Start
```bash
python custom_modules/payment_apexecr/tools/apexecr_mock_server.py --port 18080
```

## Configure Odoo POS Payment Method
- Payment terminal: `ApexECR (SOAP)`
- Endpoint URL: `http://127.0.0.1:18080/apexecrmock`
- MID/TID/SecureKey: any placeholders for mock

## Scenarios
Set `ReferenceNumber` pattern suffix to force behavior:
- `:APPROVE` => Approved immediately
- `:DECLINE` => Declined immediately
- `:UNKNOWN` => Financial returns unknown, reconciliation enquiry returns approved

If no suffix is provided, default behavior is approved.

