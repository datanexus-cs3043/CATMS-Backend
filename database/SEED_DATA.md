# Sri Lankan demonstration data

The seed represents MedSync Colombo, Kandy and Galle. People, clinic addresses,
phone numbers, licence identifiers, visit narratives and policy numbers are
fictional. They must not be used for patient care, outbound calls or messaging.
There are no real medical histories or asserted SLMC registrations in this dataset.

## Reference conventions

- National contact formatting and Colombo 011, Kandy 081 and Galle 091 area codes
  follow the [TRCSL numbering plan](https://www.trc.gov.lk/content/files/numbering/numberingmanual.pdf).
  Format-compatible example numbers are not guaranteed unassigned numbers.
- Insurer names follow the [IRCSL licensed-insurer register](https://ircsl.gov.lk/insurance-companies/),
  checked on 12 October 2026. Sri Lanka Insurance Corporation General Limited is
  distinct from the life company. Public company URLs are references, not a MedSync
  partnership, eligibility guarantee or copied insurance contract.
- Consultation disciplines are informed by the [Sri Lankan channeling directory](https://www.doc.lk/search?hospital=126&specialization=0).
  No real doctor identities or licence numbers are copied.
- Amounts are illustrative LKR values. Coverage percentages and treatment caps
  demonstrate the application's per-policy/per-invoice rule, not actual insurer
  benefits. Annual limits, settlements and historical coverage versioning are not modeled.

## Fresh setup

Select an empty PostgreSQL database/schema. Run 01 through 08 in order, install
`pgcrypto`, then run 09 and 10. File 09 refuses a populated target and uses generated
identities rather than fixed IDs or sequence resets. It creates 3 branches, 18 staff,
6 doctors, 24 patients and 73 visits with completed/scheduled/cancelled journeys,
itemized invoices, receipt-ledger entries, compensation and claim outcomes.
Every table receives linked data. Dates are relative to the execution date in
Asia/Colombo so the dashboard has current and historical visits.

The fresh seed retains each patient's registering branch while demonstrating
visits at another branch, gives two general physicians a second Family Medicine
specialty, includes a history-preserving reschedule, and supplies both 80% and
100% illustrative coverage. These are fresh-setup scenarios, not changes applied
to the existing shared database by replaying file 09.

Seed accounts use independently salted bcrypt hashes of the demonstration initial
password `password123`; change it before any non-demonstration use. The backend
supports bcrypt as well as Argon2id.

## Existing databases

Do not replay the numbered create-table or seed scripts on a populated database.
Use reviewed forward migrations and an explicitly approved maintenance operation
with a verified target, recovery snapshot, integrity gates and transaction rollback
validation. Catalogue changes do not retroactively reprice captured treatments,
invoice items, receipts or compensation. Main-branch hosting is a separate release.
