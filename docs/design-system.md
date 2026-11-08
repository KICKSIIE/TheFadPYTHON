# The Fad — UI design spec (for Figma prototyping)

A single reference for the shop and the staff app. Feed this file to a design/Figma assistant, or use it
as the checklist when building screens. Values here match the live stylesheet (`static/style.css`).

---

## 1. Principles

1. **Quiet by default.** White cards on a light grey page, one black primary action per screen.
2. **No decoration without function.** No dashed accent rules, no nested bordered boxes, no long helper
   paragraphs. If a sentence explains a form field, it belongs in a label or placeholder.
3. **One accent, one meaning.** Orange (`#ff5a1f`) marks the **selected item in the sidebar** and nothing
   else in the staff area.
4. **Destructive actions are never bare.** They open a confirmation modal that collects the approval PIN.
5. **Readable data.** Dates include the year, money includes the peso sign, records are named, raw IDs and
   JSON payloads are not shown.

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
| `ok` | `#12805c` / `#dcf3ea` | "Present", "Active", "Created" |
| `danger` | `#c0362c` | Delete / deactivate / remove |
| `warn` | `#8a5a00` / `#fff1d6` | "Low", "Late", "Upcoming" |

### Type

- Family: **Plus Jakarta Sans** (fallback system-ui, Segoe UI).
- Page title `h1`: 28 / 700 / -0.02em. Section `h2`: 18 / 700. Body: 15 / 400 / 1.55.
- Small: 13. Table header: 12 uppercase, 0.05em tracking, muted.
- Section label (e.g. `ADMIN APPROVAL`): 11 uppercase, 700, 0.08em, muted.

### Space, radius, shadow

- Spacing scale: 4 · 8 · 12 · 16 · 24 · 32 · 48.
- Card radius 14, control radius 8, pill radius 999.
- Card shadow `0 1px 2px rgba(18,20,26,.05), 0 6px 18px rgba(18,20,26,.06)`.
- Content padding: 28 px vertical, `clamp(20px, 2.5vw, 48px)` horizontal.

### Layout

- Staff shell: fixed **236 px** sidebar (dark `#101319`), content fills the rest, no max width.
- Public shop: full-width container capped at 1920 px, products in a centered grid.
- Responsive: move the sidebar above the content at 800 px; forms go to one column below 640 px.

---

## 3. Components

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:f354c662d8e2f5c25ca2b5a6bfac668f8310d21ec6b0083416b43e233a1a4b54 -->

### Buttons

| Variant | Look | Use |
|---|---|---|
| Primary | Black, white text, 9 px corners in staff screens | Form submit / primary action |
| Quiet | White, grey border | Secondary actions, Cancel, Back |
| Danger (outline) | White, red text, red border | Delete / Deactivate in tables |
| Danger (solid) | Red fill, white text | Confirm inside the modal |
| Small | 32 px tall, 0.78 rem | Table actions |
| Block | Full width, 8 px radius | Cart checkout |

Buttons and styled links retain their existing actions. Account & security is a dedicated sidebar button.



<!-- /coderabbit-ai-generated:v1 -->### Form layout (two columns)

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:48a3849944fe7b8f795cbdc9b2cc1208fb771a81e48a350032ee3d4aae366bf1 -->

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:ef29d44289dd9c92c5aca4b5c0586f0af6f17d7763b5bc4a388c8d9c4745765f -->

Centered standalone forms use `max-width: 760 px`. Product and promo editors use a centered 1240 px grid. Product editing has a live preview; promo editing has a product coverage panel. Fields use a responsive grid with gap `17 / 22 px`.

<!-- /coderabbit-ai-generated:v1 -->

<!-- /coderabbit-ai-generated:v1 -->
Full-width fields span both columns. Labels sit above the input, 14/600. No helper paragraph unless the
field is genuinely ambiguous.

**Order of fields (staff form):**

| Row | Left | Right |
|---|---|---|
| 1 | Username | Email |
| 2 | First name | Last name |
| 3 | Role | Station (optional) |
| 4 | Start date | Temporary password (new account only) |

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:abbb0dea7dab08afc9413399557fd992bf95d23566d06113a7265c514fc90284 -->

### Admin approval modal

Management forms open an approval dialog after the required fields are complete. The dialog names the action, collects a masked 6–12 digit approval PIN and offers Cancel and Confirm. Cashier stock changes also request the approving admin username. Photo actions use action-specific wording and remove actions use the danger button. Cancelling closes the dialog without submitting. The existing confirmation dialogs continue to collect approval for destructive table actions. Server-side PIN and role verification remain required.



<!-- /coderabbit-ai-generated:v1 -->### Tables

- Card wrapper, 14 px radius, 1 px border, header row light grey.
- Header cells: 12 uppercase muted. Numeric cells right-aligned, tabular figures.
- The last column is always **Actions**, right-aligned, with a matching header (never blank).
- Actions: quiet grey for Edit/View, quiet for End now, outline red for Delete/Deactivate/Remove.
- Row height 56 px; secondary line under the primary cell is 13 px muted.

### Badges and chips

- Status badge: pill, 24 px tall, 12/600. `ok` = green, `warn` = amber, neutral = grey.
- Chip: 1 px border, radius 6, 12/500 — used for sizes and product names in a promo.
- Product cell in the promo table: primary chip + `+1 more` chip (tooltip lists the rest) + muted
  "12 items" count. Never a truncated comma-separated string.

### Feedback

- Flash: full-width bar above content, 8 px radius, tinted by `error` / `success` / `info`.
- Empty state: dashed border box, centered muted sentence, 24 px padding.
- Errors never lock a form: a wrong PIN is simply rejected and the modal stays open.

---

## 4. Screens

### Sign in
Centered card 380 px, logo, "Sign in", Username, Password, full-width Sign in. Signed-in visitors are
redirected into the app, so this screen never shows account actions.

### Attendance
- Tabs (admin, only when a shift is open): My shift · Everyone · Overtime · Schedule.
- Status card with a progress bar for the running shift; otherwise "Off shift" + Clock in.
- **Recent shifts** table: Date (`Sun, Nov 08, 2026`) · Type · In · Out · Hours · Status · Note.
- No helper paragraph about shop time; the shift end appears in one short line.
- Schedule tab: two time inputs + grace, nothing else.

### Attendance: Everyone
Date range toolbar, five stat cards (Present, Late, Absent, Hours, Overtime), then the table with an
Actions column (Edit / Add shift).

### New sale (POS)
<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:925569e937b4e35fd0102ef4eb7328d81b0b07e07146e8fa26f1bd5a2d76d4c3 -->

Two columns: product grid (left, sticky cart right). Available items appear first; sold-out variants appear last after search/category filtering.

<!-- /coderabbit-ai-generated:v1 -->
Cart ends with a stack: full-width primary **Complete sale**, 8 px gap, full-width quiet **Clear cart**.

### Orders + receipt
Table of orders; order detail shows the printable receipt:
<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:9eb3af32f1ffecb94bfe532bfed2bbf02c42cb182df98d93d5d45a62d8e6ebc9 -->

receipt on the left and order overview/actions on the right; centered logo, store name, tagline, address, Plus Code, Facebook; dotted rules; meta grid

<!-- /coderabbit-ai-generated:v1 -->
(Receipt no., Date, Cashier, Order, Payment, Status); item table; totals; thank-you footer with contact.

### Inventory
Three equal cards: Stock in, Stock out, Stock count. Each has a quantity field, the approval section,
then the action button. Back button in the header.

### Promo manager
| Promo | Discount | Dates | Status | Products | Actions |

- Products: chips as described in §3.
<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:3e71040b1c3dc41a4b1952ecbee090f31ebba550aa364dfdc9e6d1bc0ad68234 -->

- Open **View promo** to inspect the campaign and linked products, then choose **Edit promo**. Active promos also offer End now; unused upcoming/ended promos can be deleted with approval.

<!-- /coderabbit-ai-generated:v1 -->
- `End now` and `Delete` open the confirmation modal with the PIN.
<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:92c3e84746ef1f37939f45da7d7307ae9f633e799fc8a029fcea9acd22004f88 -->

- Create/Edit promo: details form beside a product coverage panel. Creation sends the selected coverage with the new promo; active promos have a separate Apply promo action. The product picker appears for "One product".

<!-- /coderabbit-ai-generated:v1 -->

### Staff
| Name | Username | Role | Station | Since | Status | Actions |
- Actions: `Edit` + red `Deactivate` / quiet `Reactivate`, both through the modal.
- Add/Edit staff: the two-column form in §3.

### Account & security
560 px card: "Admin approval PIN", one short line, Current password (full width), New PIN + Confirm PIN
side by side, Save PIN.

### Refunds
Order lookup toolbar, then the refund report table, then recent refunds. No decorative dividers.

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:7e8256edd544ba45587485f53de4bacec3ea5822c9703f018bb63062d40a0624 -->

### Audit log
Toolbar: From, To, Staff username, Record, Action, Filter, Reset.
| Time | Staff name | Role | Activity & changes |
- Show the full staff name, username and approving admin; role has a separate column.
- Future events preserve staff name and role at the time of the event (migration 08).
- Each event describes the business action, for example **Receipt created #60** or **Product updated**.
- Expand **View changes** to compare labelled Before / After values. Updates show only changed fields;
  creation and deletion show the recorded values and an empty opposite side.
- Display only reviewed business fields. Never display password/PIN values or hashes, tokens or binary photos.
- Audit uses server paging (50 events) and preserves filters. Other large tables use 10/25/50/100 rows per page.
- Scroll wide tables within their card; headers stay visible.



<!-- /coderabbit-ai-generated:v1 -->### Shop (public)
- Header: logo · centered search · Shop.
- Hero centered; **category pills centered above the grid** (never a sidebar).
- Centered filter row (In stock only, Sort).
- Product grid centered, cards 230–320 px, 4:5 image, name, price, color dots, stock line.
- Product page: "← Back to shop" button, breadcrumb, image left, details right, "Order on Facebook".
- Footer: brand, address + Plus Code, map, Facebook.

### Prototype mode
Same screens with a yellow banner: "Prototype copy — navigation is unlocked…". Nothing else changes.

---

## 5. Accessibility

- Focus ring: 2 px `#ff5a1f`, offset 2.
- Inputs always have a visible `<label>`; placeholders are hints, not labels.
- Modal: `dialog` element, labelled by its title, Escape closes, focus starts in the PIN field.
- Table headers are never blank; destructive buttons name the object ("Delete Weekend Deal" tooltip).
- Motion respects `prefers-reduced-motion`.

---

## 6. Figma build order

1. Foundations → colour, type, spacing styles.
2. Components → Button (6 variants), Input, Select, Badge, Chip, Tabs, Table row, Stat card, Modal,
   Approval section, Flash, Empty state.
3. Screens → Sign in · Attendance · POS · Orders · Receipt · Inventory · Promo manager (+ modal) ·
   Staff · Accounts · Refunds · Audit · Shop · Product.
4. Prototype links → sidebar navigation, table actions → modal, product card → product page.
