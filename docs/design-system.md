# The Fad — UI design spec (for Figma prototyping)

A single reference for the shop and the staff app. Feed this file to a design/Figma assistant, or use it
as the checklist when building screens. Values match the live stylesheet (`static/style.css`).

---

## 1. Principles

1. **Quiet by default.** White cards on a light grey page, one black primary action per screen.
2. **No decoration without function.** No dashed accent rules, no nested bordered boxes, no long helper
   paragraphs. If a sentence explains a field, it belongs in a label or placeholder.
3. **One accent, one meaning.** Orange (`#ff5a1f`) marks the **selected sidebar item** and nothing else.
4. **Destructive actions are never bare.** They open a confirmation modal that collects the approval PIN.
5. **Readable data.** Dates include the year, money carries the peso sign, records are named, raw IDs and
   JSON payloads are never shown.

---

## 2. Foundations

### Colour

| Token | Value | Use |
|---|---|---|
| `ink` | `#12141a` | Primary text, primary button, active tab |
| `ink-2` | `#3b4050` | Secondary text |
| `muted` | `#667085` | Labels, helper text, table headers |
| `line` | `#e6e8ec` | Dividers, card borders |
| `line-2` | `#d5d9e0` | Input borders |
| `paper` | `#f5f6f8` | Page background |
| `card` | `#ffffff` | Cards, tables, inputs |
| `accent` | `#ff5a1f` | **Sidebar selected item only** |
| `ok` | `#12805c` / `#dcf3ea` | Present, Active, Created |
| `danger` | `#c0362c` | Delete, deactivate, remove |
| `warn` | `#8a5a00` / `#fff1d6` | Low, Late, Upcoming |

### Type

- Family: **Plus Jakarta Sans** (fallback system-ui, Segoe UI).
- Page title `h1`: 28 / 700 / -0.02em. Section `h2`: 18 / 700. Body: 15 / 400 / 1.55.
- Small: 13. Table header: 12 uppercase, 0.05em tracking, muted.
- Section label (e.g. `ADMIN APPROVAL`): 11 uppercase, 700, 0.08em, muted.

### Space, radius, shadow

- Spacing scale: 4 · 8 · 12 · 16 · 24 · 32 · 48.
- Card radius 14, control radius 8, button radius 999 (pill).
- Card shadow `0 1px 2px rgba(18,20,26,.05), 0 6px 18px rgba(18,20,26,.06)`.
- Content padding: 28 px vertical, `clamp(20px, 2.5vw, 48px)` horizontal.

### Layout

- Staff shell: fixed **236 px** dark sidebar (`#101319`), content fills the rest.
- Public shop: full-width container capped at 1920 px, products in a centered grid.
- Responsive: sidebar becomes a top bar at 800 px; forms go to one column below 640 px.

---

## 3. Components

### Buttons

| Variant | Look | Use |
|---|---|---|
| Primary | Black pill, white text | Form submit / primary action |
| Quiet | White, grey border | Secondary actions, Cancel, Back |
| Danger (outline) | White, red text, red border | Delete / Deactivate in tables |
| Danger (solid) | Red fill, white text | Confirm inside the modal |
| Small | 32 px tall, 0.78 rem | Table actions |
| Block | Full width, 8 px radius | Cart checkout |

One primary action per view. Account & security is a full-width sidebar button; **View shop** and
**Sign out** sit beneath it as two equal-width outlined buttons sharing the same left and right edges.

### Form layout

Centered standalone forms use `max-width: 760 px` (560 px for Account & security). Product and promo
editors pair the form with a live preview / coverage panel in a 1240 px grid. Fields use a responsive grid
(`minmax(230px, 1fr)`, gap 17 / 22 px); full-width fields span both columns. Labels sit above the input,
14 / 600. No helper paragraph unless the field is ambiguous.

**Order of fields (staff form):**

| Row | Left | Right |
|---|---|---|
| 1 | Username | Email |
| 2 | First name | Last name |
| 3 | Role | Station (optional) |
| 4 | Start date | Temporary password (new account only) |

### Admin approval

A flat section, never a nested card: 1 px top rule, `ADMIN APPROVAL` label, a PIN input capped at 200 px
with a **Show** toggle. In table rows it collapses to one inline line.

### Approval modal

Management forms open a dialog after the required fields are complete: the dialog names the action,
collects a masked 6–12 digit PIN and offers Cancel and Confirm. Cashier stock changes also ask for the
approving admin username. A wrong PIN shows an error and keeps the form filled.

### Tables

- Card wrapper, 14 px radius, 1 px border, light grey header.
- Header cells 12 uppercase muted; numeric cells right-aligned with tabular figures.
- The last column is always **Actions**, right-aligned with a matching header.
- Actions: quiet grey for Edit/View, quiet for End now, outline red for Delete/Deactivate/Remove.
- **ID column:** every table shows the record id in a narrow right-aligned muted column, and the header
  names it: **Product ID** (products, inventory, movements, promo detail, receipt lines; grouped product
  rows show the id range `46–53`), **User ID**, **Promo ID**, **Refund ID**, **Shift ID**, **Overtime ID**,
  **Event ID**, **Order ID** and **Category ID**.
- **Search matches ids:** inventory, products and POS search accept an exact numeric id as well as text.
- Numbered rows, sortable headers, 10/25/50/100 rows per page, scroll inside the card.

### Badges and chips

- Status badge: pill, 24 px tall, 12/600. Green = ok, amber = warn, grey = neutral.
- Chip: 1 px border, radius 6, 12/500 — sizes and product names.

### Feedback

- Flash: full-width bar above content, 8 px radius, tinted by error / success / info.
- Empty state: dashed border box, centered muted sentence, 24 px padding.
- Errors never lock a form.

---

## 4. Screens

### Sign in
Centered card 380 px, logo, Username, Password, full-width Sign in. Signed-in visitors are redirected into
the app, so this screen never shows account actions.

### Attendance
- Tabs (admin, when a shift is open): My shift · Everyone · Overtime · Schedule.
- Status card with a progress bar for the running shift; otherwise "Off shift" + Clock in.
- **Recent shifts:** Date (`Sun, Nov 08, 2026`) · Shift ID · Type · In · Out · Hours · Status · Note.
- Add/Edit shift: 760 px form with Staff, Time in | Time out (two columns that never overflow) and Reason.
- Schedule: two time inputs + grace, nothing else.

### Attendance: Everyone
Date range toolbar, five stat cards (Present, Late, Absent, Hours, Overtime), then the table with a
**Shift ID** column and Actions (Edit / Add shift).

### New sale (POS)
Two columns: product grid (left, sticky cart right). Available items first; sold-out variants last.
Cart ends with a stack: full-width **Complete sale**, 8 px gap, full-width quiet **Clear cart**.

### Orders + receipt
Table of orders; the detail page shows a receipt on the left and order overview/actions on the right.
Receipt: centered logo, store name, tagline, address, Plus Code, Facebook; dotted rules; meta grid
(Receipt no., Date, Cashier, Order, Payment, Status); item table with **Product ID · Item · Qty · Price ·
Total**; totals; thank-you footer with contact.

### Inventory
- Toolbar only: Search · Category · Low means `at or below N` · Low stock only · Filter · Clear.
- Table: `# | Product | Product ID | Category | In stock | Actions`. Out badge at 0, Low at/below threshold.
- Item page: three cards — Stock in, Stock out, Stock count — each with quantity, approval section, action.
- Stock history: `When · Product · Product ID · Type · Change · Balance · By · Order ID`.

### Promos
| # | Promo | Promo ID | Discount | Dates | Status | Items | Actions |

- Items is the number of items on the promo (right aligned), never a product-name list.
- Actions: Active → `View promo` + `End now`; Upcoming → `View promo` + red `Delete`;
  Ended → `View` + red `Delete` (row dimmed). Destructive actions open the approval modal.
- View promo: read-only campaign page (overview, coverage, included products) with **Edit promo**.
- Create/Edit: details form beside a product coverage panel; product picker appears for "One product".

### Products
Two views, switched by a text link.

| Grouped | # | Product | Product ID | Colors | Sizes | Price | Stock | Discount | Status | Actions |
| Variants | # | Product | Product ID | Color | Size | Category | Price | Stock | Discount | Status | Actions |

- **Status is only Active or Inactive.** Discount is its own column (`20% off` badge or `—`).
- The variants view lists every color/size with `Edit`, `Stock` and a red `Deactivate` per item.
- Grouped rows show `Active` plus an `N inactive` badge when only some variants are off.
- The editor pairs the form with a live preview; below it, "Colors and sizes of this product" carries the
  same per-variant status and Deactivate control.

### Staff
| # | Name | User ID | Username | Role | Station | Since | Status | Actions |
- Actions: `Edit` + red `Deactivate` / quiet `Reactivate`, both through the modal.
- Add/Edit: the two-column form in §3.

### Account & security
560 px card: "Admin approval PIN", one short line, Current password (full width), New PIN + Confirm PIN
side by side, Save PIN.

### Refunds
Order lookup toolbar, then three summary cards (Gross sales · Refunded · Net sales), a per-method table
(Method · Refunds · Units · Refunded with a Total row) and the refunds-in-period table
(When · Refund ID · Order ID · Item · Qty · Amount · Method · Reason · By). No decorative dividers.

### Audit log
Toolbar: From, To, Staff username, Record, Action, Filter, Reset.
| # | Time | Event ID | Staff name | Role | Details |
- Details is a short human sentence — **Stock in · 20 units**, **Receipt created #60** — plus a chip naming
  the record.
- **Show details** expands a compact proof list, one line per field: `Field  old → new`. Updates show only
  changed fields; creations show recorded values; internal ids are omitted. The block ends with
  `Audit event #N · recorded <time> · approved by <admin>`.
- Never display password or PIN values, tokens or binary photos.
- Server paging (50 events) that preserves filters.

### Shop (public)
- Header: logo · centered search · Shop.
- Hero centered; **category pills centered above the grid** (never a sidebar).
- Centered filter row (In stock only, Sort). Product grid centered, cards 230–320 px, 4:5 image.
- Product page: "← Back to shop", breadcrumb, image left, details right, "Order on Facebook".
- Footer: brand, address + Plus Code, map, Facebook.

### Prototype mode
Same screens with a yellow banner: "Prototype copy — navigation is unlocked…". Nothing else changes.

---

## 5. Accessibility

- Focus ring: 2 px `#12141a`, offset 2.
- Visible label on every input; placeholders are hints, not labels.
- Modal: `dialog`, labelled by its title, Escape closes, focus starts in the PIN field.
- Table headers are never blank; destructive buttons name their object.
- Motion respects `prefers-reduced-motion`.

---

## 6. Layouts & page anatomy

### App shell
- Sidebar **236 px**, fixed, full height, dark `#101319`: logo → nav groups → user block (name, role,
  Account & security, then View shop | Sign out).
- Nav group label 11 px uppercase `#7d8494`; item 8 px radius, 2 px orange left bar when selected.
- Content padding 28 px / `clamp(20px, 2.5vw, 48px)`, no max width.
- Page head: title left, actions right (8 px gap), wraps below 800 px.
- Mobile ≤ 800 px: top bar with a Menu toggle.

### Page patterns

| Pattern | Structure | Width |
|---|---|---|
| Table / index | head → toolbar → table card → pagination | full |
| Detail (order, promo view) | head → receipt/products + overview/actions | 1.75 : 1 |
| Form (staff, shift, account) | head → form card → action row | 760 px (560 account) |
| Editor (product, promo create) | head → form + preview / coverage panel | 1240 px, 1.4 : 1 |
| Inventory item | head → 3 equal cards → movements | full, 3 columns |
| Shop | header → hero → categories → filters → grid → footer | max 1920 px |

### Form anatomy
1. Optional eyebrow + `h1`.
2. Field grid (`minmax(230px, 1fr)`, gap 17 / 22).
3. Approval section (1 px top rule, label, 200 px PIN, Show).
4. Action row above a top rule.

---

## 7. Navigation & flow

### Entry points
- `/` public shop, `/login` staff sign-in, `/staff` shortcut to Attendance.
- After sign-in every role lands on **Attendance**.

### Shift gate
Until a shift is running only Attendance opens; other pages redirect back and the sidebar shows Attendance
alone. Prototype mode bypasses this gate.

### Sidebar map
| Cashier | Admin |
|---|---|
| Overview: Dashboard | Overview: Dashboard |
| Sell: New sale, Orders | Sell: New sale, Orders |
| Stock: Inventory, Promos (read-only) | Stock: Inventory, Products, Promos |
| Team: Attendance | Team: Attendance, Staff |
| — | Admin: Refunds, Audit log |

### Screen connections
| From | To | Trigger |
|---|---|---|
| Sign in | Attendance | successful sign-in |
| Dashboard | Orders / Inventory / Promos | stat cards |
| New sale | Order detail (receipt) | Complete sale |
| Orders | Order detail | row link |
| Order detail | Refund order | "Refund items from this order" (admin) |
| Inventory | Inventory item | Manage → stock in / out / count (PIN) |
| Inventory | Stock movements | Stock history |
| Products | Product editor | Edit / Add product → Save → list |
| Product editor | Photos · Inventory item | Manage photos · Stock |
| Promos | Promo view | View promo → Edit promo |
| Promos | Create / Edit | Create promo → Save → list |
| Promo row | Modal → list | End now · Delete (PIN) |
| Staff | Add / Edit | Add staff / Edit → Save → list |
| Staff row | Modal → list | Deactivate / Reactivate (PIN) |
| Refunds | Refund order | Find order to refund |
| Shop | Product page | card / colour dot |

### Modal and redirect rules
- Approval modal opens on management form submit; Cancel keeps the form filled; a wrong PIN reopens it.
- Confirm modal opens from destructive table buttons and names the object.
- After a save: forms → their list; promo End/Delete → Promos; stock move → item; refund → order; sign-out → Sign in.
- Failed validation re-renders the same screen with an error flash.

---

## 8. Sample data

Use this content so the prototype matches the app.

### Store
| Field | Value |
|---|---|
| Name | The Fad |
| Tagline | Fashion You Always Deserve |
| Address | G.Y. Dela Serna St, Lapu-Lapu, Cebu |
| Plus Code | 8W6X+2QC |
| Facebook | facebook.com/profile.php?id=61580609323200 |
| Hours | Monday–Saturday, 09:00–17:00 (Asia/Manila) |

### Staff
| User ID | Name | Username | Role | Station | Since |
|---|---|---|---|---|---|
| 10 | Dev Admin | dev_admin | Admin | — | Nov 03, 2026 |
| 14 | Ana Reyes | ana.reyes | Admin | — | Nov 08, 2026 |
| 11 | Dev Cashier | dev_cashier | Cashier | Counter 1 | Nov 01, 2026 |
| 13 | Juan Dela Cruz | juan.delacruz | Cashier | Counter 1 | Nov 01, 2026 |
| 12 | Maria Santos | maria.santos | Cashier | Counter 2 | Nov 01, 2026 |

### Categories
`10 Men Wear · 13 Tops · 14 Outerwear · 12 Women Wear · 15 Bottoms · 16 Headwear · 17 Accessories`

### Products
| Product ID | Product | Category | Price | Stock | Colors | Sizes | Discount | Status |
|---|---|---|---|---|---|---|---|---|
| 46–53 | Boxy Graphic Tee | Tops | ₱699.00 | 202 | Black, Cream | S, M, L, XL | — | Active |
| 34–45 | Essential Tee | Tops | ₱499.00 | 173 | Black, Sage, White | S, M, L, XL | — | Active |
| 54–61 | Ribbed Tank | Tops | ₱399.00 | 164 | Black, Sand | XS, S, M, L | — | Active |
| 62–73 | Classic Hoodie | Outerwear | ₱1,299.00 | 298 | Charcoal, Forest, Navy | S, M, L, XL | 20% off | Active |
| 74–77 | Denim Jacket | Outerwear | ₱1,899.00 | 91 | Indigo | S, M, L, XL | — | Active |
| 78–83 | Windbreaker | Outerwear | ₱1,499.00 | 126 | Black, Red | M, L, XL | — | Active |
| 84–91 | Straight Jeans | Bottoms | ₱1,499.00 | 173 | Black, Indigo | 28, 30, 32, 34 | — | Active |
| 92–99 | Cargo Shorts | Bottoms | ₱899.00 | 169 | Khaki, Olive | S, M, L, XL | — | Active |
| 108–110 | Dad Cap | Headwear | ₱349.00 | 45 | Beige, Black, Navy | — | — | Active |
| 111–112 | Bucket Hat | Headwear | ₱399.00 | 49 | Cream, Olive | — | — | Active |
| 115–126 | School Shoes | Men Wear | ₱5,000.00 | 184 | Black, Brown, Gray | S, M, X, XL | — | Active |

### Promos
| Promo ID | Name | Discount | Dates | Status | Items |
|---|---|---|---|---|---|
| 24 | Midseason Sale | 20% | Nov 03 – Nov 16, 2026 | Active | 12 |
| 26 | Payday Sale | 25% | Nov 12 – Nov 14, 2026 | Upcoming | 0 |
| 25 | Weekend Deal | 15% | Nov 05 – Nov 08, 2026 | Ended | 0 |
| 23 | go50 | 50% | Nov 03 – Nov 05, 2026 | Ended | 0 |
| 27 | Summer Clearance | 30% | Sep 27 – Oct 17, 2026 | Ended | 0 |

### Orders
| Order ID | When | Type | Cashier | Items | Total | Status |
|---|---|---|---|---|---|---|
| 65 | Nov 09, 2026 · 01:51 AM | Walk-in | Dev Admin | 4 | ₱2,396.00 | Completed |
| 64 | Nov 09, 2026 · 01:17 AM | Walk-in | Dev Cashier | 2 | ₱1,398.00 | Completed |

### Receipt — order 65
| Product ID | Item | Qty | Price | Total |
|---|---|---|---|---|
| 36 | Essential Tee - White (L) | 1 | ₱499.00 | ₱499.00 |
| 45 | Essential Tee - Sage (XL) | 1 | ₱499.00 | ₱499.00 |
| 47 | Boxy Graphic Tee - Black (M) | 1 | ₱699.00 | ₱699.00 |
| 49 | Boxy Graphic Tee - Black (XL) | 1 | ₱699.00 | ₱699.00 |

Subtotal ₱2,396.00 · Total ₱2,396.00 · Cash · Walk-in · Dev Admin · Completed.

### Refunds
| Refund ID | When | Order ID | Item | Qty | Amount | Method | Reason | By |
|---|---|---|---|---|---|---|---|---|
| 5 | Nov 06, 2026 · 11:49 AM | 19 | Cargo Shorts - Khaki (XL) | 1 | ₱899.00 | Cash | Wrong size | Dev Admin |
| 4 | Nov 03, 2026 · 04:17 PM | 12 | Men Shirt Blue | 1 | ₱60.00 | Cash | — | Dev Admin |

Period totals: Gross sales ₱89,902.05 · Refunded ₱959.00 · Net sales ₱88,943.05.

### Attendance
| Shift ID | Date | Staff | Type | In | Out | Hours | Status |
|---|---|---|---|---|---|---|---|
| 27 | Sun, Nov 08, 2026 | Dev Admin | Regular | 09:31 PM | 09:31 PM | 0.00 | Late |
| 26 | Sun, Nov 08, 2026 | Dev Cashier | Regular | 02:59 PM | 05:00 PM | 2.01 | Late |

### Audit events
| Event ID | Time | Staff | Role | Details |
|---|---|---|---|---|
| 151 | Nov 09, 2026 · 12:19 PM | Dev Cashier | Cashier | Stock movement · -1 units · Product #30 |
| 150 | Nov 09, 2026 · 12:19 PM | Dev Cashier | Cashier | Stock changed: 11 → 10 · Women Shirt Red (M) |

Show details for 150: `Current stock  11 → 10` · `Audit event #150 · recorded Nov 09, 2026 · 12:19 PM`.

### Copy bank
- **Primary buttons:** Sign in · Save changes · Save PIN · Create promo · Add product · Add staff · Save shift · Complete sale.
- **Table actions:** Edit · View promo · View · End now · Delete · Deactivate · Reactivate · Manage · Stock · Remove.
- **Empty states:** "No promos yet. Create one, for example 20% off a product for a week." · "No products match." ·
  "No refunds in this period." · "No changes match these filters." · "The cart is empty. Add products from the list."
- **Flash:** "Sale saved." · "Cart cleared." · "Promo ended. Prices are back to normal." ·
  "A valid admin approval PIN is required. Set your PIN in Account & security." · "You have been signed out."
- **Modal copy:** "End “Weekend Deal” now? Prices go back to normal immediately." ·
  "Delete “Weekend Deal”? This cannot be undone…" · "Deactivate Juan Dela Cruz? They cannot sign in until reactivated."
- **Receipt footer:** "Thank you for shopping with The Fad. Questions or sizing help? Message us on Facebook."

---

## 9. Figma build order

1. Foundations → colour, type, spacing styles.
2. Components → Button (6 variants), Input, Select, Badge, Chip, Tabs, Table row, Stat card, Approval modal,
   Confirm modal, Flash, Empty state.
3. Layouts → app shell, table page, form page, editor (preview split), detail page, shop page.
4. Screens → Sign in · Attendance (+ Everyone / Overtime / Schedule / Add shift) · POS · Orders · Receipt ·
   Inventory (+ item, history) · Promos (+ view, create, modal) · Products (+ editor, variants, photos) ·
   Staff (+ form) · Account & security · Refunds (+ refund order) · Audit log · Shop · Product.
5. Prototype links → follow §7: sidebar navigation, table row → detail, actions → modals, save → list.
6. Populate frames with the §8 sample data so text lengths and table widths are realistic.
