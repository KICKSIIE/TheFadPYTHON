<!-- coderabbit-ai-generated:v1 -->

# UI and audit update

Based on main commit 2075275. Staff controls now share spacing, custom button styles, table scrolling and pagination. Standalone forms are centered; product/promo editors use a form plus live preview. Promo list → View promo → Edit promo keeps inspection separate from changes. Receipt details use the right side for order status, totals and actions. POS sorts available stock before sold-out variants.

## Existing database update

If your database already has audit storage and triggers from 05 or 07, run **sql/08_audit_details.sql** once in pgAdmin. It is transactional and can be rerun. If audit storage/routines are missing, first run **sql/07_security_populate.sql**, then 08. The complete setup bundle includes both for a restored base database. This update adds audit metadata and photo auditing; attendance enforcement remains in the backend.

08 stores staff name/role for future events, redacts credential fields and binary photos, records password-only changes without values, and audits photo metadata. Existing events retain their original payloads; the viewer applies an explicit allowlist so old credential fields cannot appear. Existing identities fall back to current staff details and cannot be reconstructed historically. Audit history remains append-only. New records roll back with the business transaction if it fails.

## Audit display

Separate Time, Staff name, Role, Activity & changes columns. Creation/deletion shows recorded business values; updates show changed fields only. Receipt creation is named explicitly. Product subjects include color/size. Expand View changes for before/after comparison. PIN/password values and hashes are never displayed. PIN changes retain an action with no public values. Audit pages contain up to 50 events and preserve filters.

Other tables paginate the rows already returned by their current endpoint in the browser (10/25/50/100 rows), with accessible controls and sticky table headers. This does not add server-side query paging to those endpoints. JavaScript-disabled clients still see all returned rows and functional forms.

Validation uses a synthetic local database; compatibility with your original backup is not established by those checks.
