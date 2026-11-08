<!-- coderabbit-ai-generated:v1 -->

# UI and audit update

Based on main commit 2075275. Staff controls now share spacing, custom button styles, table scrolling and pagination. <!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:d76cf1aaed0627ad401a0c18846957593f28ffa3f572680970c0d0bca24b2343 -->

Standalone forms are centered; product editors have a live preview, while promo editors have a product coverage panel.

<!-- /coderabbit-ai-generated:v1 --> Promo list → View promo → Edit promo keeps inspection separate from changes. Receipt details use the right side for order status, totals and actions. POS sorts available stock before sold-out variants.

## Existing database update

If your database already has audit storage and triggers from 05 or 07, run **sql/08_audit_details.sql** once in pgAdmin. It is transactional and can be rerun. If audit storage/routines are missing, first run **sql/07_security_populate.sql**, then 08. The complete setup bundle includes both for a restored base database. This update adds audit metadata and photo auditing; attendance enforcement remains in the backend.

08 stores staff name/role for future events, redacts credential fields and binary photos, records password-only changes without values, and audits photo metadata. Existing events retain their original payloads; the viewer applies an explicit allowlist so old credential fields cannot appear. Existing identities fall back to current staff details and cannot be reconstructed historically. Audit history remains append-only. New records roll back with the business transaction if it fails.

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:15b9c24323e2aecbbfd3a540b6355a02c37a70e2788dcd871fb3ef3120f594f2 -->

## Follow-up fixes
Run **sql/09_sale_audit_context.sql** after 08 on an existing database, then restart the Flask server with the updated Python modules and templates together. The new migration links product stock snapshots to the receipt within the same sale/return transaction. Existing saved snapshots with uppercase fields or JSON text now display their business values; history with no saved payload cannot be reconstructed. Sales show receipt, quantity, unit price and stock balances. Before/after proof is expanded by default.

The promo list opens its summary through the existing edit endpoint with `?view=1`; Edit then opens the form. Inventory defaults to A–Z, with category/stock and sorting filters. Staff data tables have row numbers and ascending/descending column controls. Audit sorting applies to the current server page only. POS cart mutations refresh in place, preserve checkout details and keep the scroll position. Photo selections accumulate across picker openings and show removable thumbnails; the first selected photo is the cover. Saved products use Add / manage photos for additional uploads.

## Audit display

<!-- /coderabbit-ai-generated:v1 -->

Separate Time, Staff name, Role, Activity & changes columns. Creation/deletion shows recorded business values; updates show changed fields only. Receipt creation is named explicitly. Product subjects include color/size. Expand View changes for before/after comparison. PIN/password values and hashes are never displayed. PIN changes retain an action with no public values. Audit pages contain up to 50 events and preserve filters.

Other tables paginate the rows already returned by their current endpoint in the browser (10/25/50/100 rows), with accessible controls and sticky table headers. This does not add server-side query paging to those endpoints. JavaScript-disabled clients still see all returned rows and functional forms.

Validation uses a synthetic local database; compatibility with your original backup is not established by those checks.
