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

### Buttons

| Variant | Look | Use |
|---|---|---|
| Primary | Black pill, white text | One per screen / form submit |
| Quiet | Transparent, grey border | Secondary actions, Cancel, Back |
| Danger (outline) | White, red text, red border | Delete / Deactivate in tables |
| Danger (solid) | Red fill, white text | Confirm inside the modal |
| Small | 32 px tall, 0.85 rem | Table actions only |
| Block | Full width, 8 px radius | Cart checkout |

Rules: one primary per view; destructive buttons never appear without the modal; table action gaps are 8 px.

### Form layout (two columns)

Container `max-width: 760 px`. Fields in a responsive grid, `minmax(230px, 1fr)`, gap `17 / 22 px`.
Full-width fields span both columns. Labels sit above the input, 14/600. No helper paragraph unless the
field is genuinely ambiguous.

**Order of fields (staff form):**

| Row | Left | Right |
|---|---|---|
| 1 | Username | Email |
| 2 | First name | Last name |
| 3 | Role | Station (optional) |
| 4 | Start date | Temporary password (new account only) |

### Admin approval section (flat)

Never a nested card. A 1 px top rule, 16 px above the actions, then:

```
────────────── 1px #e6e8ec ──────────────
ADMIN APPROVAL            (11px uppercase muted)
[ Approval PIN              ]   Show
[ 6–12 digits · max 200px   ]
```

- PIN input: `max-width: 200 px`, numeric, masked, with a **Show / Hide** text toggle.
- Cashier stock screens add an "Approving admin" text field beside it.
- Inside table rows only, the section collapses to one inline line: `Approval PIN [ 108px ]` (no heading).

### Confirmation modal

Width 440 px (max 92 vw), radius 16, backdrop `rgba(16,19,25,.45)`.

```
Delete promo
Delete "Weekend Deal"? This cannot be undone.

Approval PIN
[ •••••• ]  Show

                         [ Cancel ]  [ Delete ]
```

- Opened by any destructive action button.
- Confirm button is solid red for destructive actions, black for neutral ones.
- Escape / backdrop / Cancel close it; focus starts in the PIN field.

### Tables

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
Two columns: product grid (left, sticky cart right).
Cart ends with a stack: full-width primary **Complete sale**, 8 px gap, full-width quiet **Clear cart**.

### Orders + receipt
Table of orders; order detail shows the printable receipt:
centered logo, store name, tagline, address, Plus Code, Facebook; dotted rules; meta grid
(Receipt no., Date, Cashier, Order, Payment, Status); item table; totals; thank-you footer with contact.

### Inventory
Three equal cards: Stock in, Stock out, Stock count. Each has a quantity field, the approval section,
then the action button. Back button in the header.

### Promo manager
| Promo | Discount | Dates | Status | Products | Actions |

- Products: chips as described in §3.
- Actions: **Active** → `Edit` + `End now`; **Upcoming** → `Edit` + red `Delete`;
  **Ended** → `View` + red `Delete` (row dimmed).
- `End now` and `Delete` open the confirmation modal with the PIN.
- Create/Edit promo: two-column form (Promo name | Discount %, Starts | Ends, Apply to | Product), then
  Save / Cancel. The product picker only appears when "One product" is chosen.

### Staff
| Name | Username | Role | Station | Since | Status | Actions |
- Actions: `Edit` + red `Deactivate` / quiet `Reactivate`, both through the modal.
- Add/Edit staff: the two-column form in §3.

### Account & security
560 px card: "Admin approval PIN", one short line, Current password (full width), New PIN + Confirm PIN
side by side, Save PIN.

### Refunds
Order lookup toolbar, then the refund report table, then recent refunds. No decorative dividers.

### Audit log
Toolbar: From, To, Staff username, Record, Action, Filter, Reset.
| Time | Staff | Details |
- Time: `Nov 08, 2026 10:53 PM`.
- Staff: username, with role underneath ("Admin" / "Cashier"), plus "Approved by …" when relevant.
- Details: a short human phrase ("Updated product") plus a chip with the record name ("Essential Tee").
- No JSON, no before/after payloads, no long explanation paragraph.

### Shop (public)
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
