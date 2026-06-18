# POS UAT Checklist (Mock First)

- Create POS payment method with terminal type `ApexECR (SOAP)`.
- Start mock server and confirm endpoint is reachable.
- Test sale approved (`ReferenceNumber` with `:APPROVE`).
- Test sale declined (`ReferenceNumber` with `:DECLINE`).
- Test sale unknown then reconcile (`ReferenceNumber` with `:UNKNOWN`), then run/await cron.
- Test refund approved from refunded order that has Apex RRN/AuthCode.
- Test duplicate retry behavior on same order after temporary failure.
- Validate stored fields on `pos.payment` and entries in `ApexECR Logs`.

