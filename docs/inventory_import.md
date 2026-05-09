# Inventory Import Tool

A reusable script that reads a CSV file (or Google Sheets CSV export) and imports
inventory rows into the app through the backend API — no direct database access.

---

## Quick start

```bash
# 1. Fill in the .xlsx template, then export only the "Inventory Import" sheet as CSV
#    File → Download → Comma Separated Values (.csv)

# 2. Set non-secret env vars (password will be prompted — do not put it inline)
export API_BASE_URL=https://mke-bm-inventry-api.onrender.com
export ADMIN_USERNAME=youruser

# 3. Dry run — preview what would be imported, nothing is written
#    The script will prompt for the admin password securely.
python3 backend/scripts/import_inventory.py --csv inventory.csv

# 4. Review the import report: import_report.json / import_report.csv

# 5. Apply the real import (will prompt for password again)
python3 backend/scripts/import_inventory.py --csv inventory.csv --commit
```

---

## Environment variables

| Variable         | Required | Description                                                  |
|------------------|----------|--------------------------------------------------------------|
| `API_BASE_URL`   | Yes      | Backend URL, e.g. `https://mke-bm-inventry-api.onrender.com` |
| `ADMIN_USERNAME` | Yes      | Admin account username                                       |
| `ADMIN_PASSWORD` | Yes      | Admin account password                                       |

If any variable is missing the script will prompt you interactively.  
**Never put these in a `.env` file you commit to git.**

---

## Using the .xlsx template

The recommended workflow uses the provided `.xlsx` template:

1. Open the `.xlsx` workbook.
2. Fill in inventory data on the **Inventory Import** sheet.
   - Use the dropdown menus for **Consumable**, **Condition**, and **Unit** — they help ensure valid values.
   - The **SKU** column may auto-fill using a formula. Leave it as-is; it will export as plain text.
3. **Export only the Inventory Import sheet as CSV:**
   `File → Download → Comma Separated Values (.csv)`
4. Run the import script against the exported `.csv` file.

> **Important:** Do not upload the `.xlsx` file directly. The importer requires a `.csv` file.
> If you try to use a `.xlsx` file, the script will tell you to export as CSV first.

### What carries over into CSV and what doesn't

| Feature | In .xlsx | In exported .csv |
|---------|----------|------------------|
| Dropdown menus | Yes | No — but the selected value is preserved as plain text |
| SKU formula | Yes | No — but the calculated SKU value is preserved as plain text |
| Formatting / colors | Yes | No |
| Extra sheets (Instructions, Lists) | Yes | No — only the active sheet exports |

The importer validates the **actual text values** in the CSV — it does not need the dropdowns
or formulas to be present.

---

## Required permissions

The admin account must have inventory, cabinet, bin, and room management
permissions (i.e. `can_manage_users = True` or all four `can_manage_*` flags).
A normal admin account created in the app will have all of these by default.

---

## How to export from Google Sheets as CSV

1. Open the Google Sheet.
2. Click **File → Download → Comma Separated Values (.csv)**.
3. Save the file somewhere convenient (e.g. `~/Downloads/inventory.csv`).
4. Run the import script against that file.

You can also point the script directly at a Google Sheets CSV export URL:

```
https://docs.google.com/spreadsheets/d/<SHEET_ID>/export?format=csv&gid=0
```

Replace `<SHEET_ID>` with the ID from your sheet URL.
`gid=0` is the first tab; change it if your data is on a different tab.

```bash
python3 backend/scripts/import_inventory.py \
  --csv "https://docs.google.com/spreadsheets/d/1MytKUR.../export?format=csv&gid=0"
```

---

## Expected CSV columns

The script recognises these column names (case-insensitive, whitespace trimmed):

### Required columns

| CSV header | Canonical field | Notes |
|------------|----------------|-------|
| `Name` / `Item` / `Item Name` | name | Item name |
| `Room` | room | Room the item lives in |
| `Cabinet` / `Place` / `Shelf` / `Storage Location` / `Location` | cabinet | Physical cabinet/location within the room |
| `Quantity` / `Qty` / `Amount` | quantity | See quantity parsing below |

> **Note:** `Cabinet` and `Place` are aliases for the same field. Do not include both in the same
> CSV — the importer will reject it with a clear error.

### Optional columns

| CSV header | Canonical field | Notes |
|------------|----------------|-------|
| `Bin` / `Bin (if any)` / `Tote` / `Container` | bin | Sub-location within the cabinet |
| `Bin Requires Full Checkout` / `Requires Full Bin Checkout` / `Full Bin Checkout Required` / `Bin Full Checkout Only` | bin_requires_full_checkout | Yes/No — see below |
| `Unit` / `Metric` | unit | ft, Pack, rolls, etc. |
| `Consumable` / `Is Consumable` | consumable | Yes/No/True/False/Y/N/1/0 — see below |
| `Low Stock Threshold` / `Min Quantity` / `Reorder Threshold` | low_stock_threshold | Numeric — see below |
| `Unit Price` / `Price` / `Cost` | unit_price | Blank or positive decimal (e.g. `9.99` or `$9.99`) |
| `Condition` | condition | GOOD / FAIR / POOR / DAMAGED — blank defaults to GOOD |
| `SKU` | sku | Provided or auto-generated — see below |
| `Notes` / `Note` | notes | Free-text description |

Extra columns not in this table are reported as warnings and ignored. They do not cause
import failures.

---

## Example CSV

```csv
Name,Room,Cabinet,Bin,Quantity,Unit,Consumable,Low Stock Threshold,Unit Price,Condition,SKU,Notes,Bin Requires Full Checkout
Safety Goggles,Group 1 Tijori,Tijori Top Shelf,,10,,No,2,12.99,GOOD,GROUP1TI-0001,UV-rated,
Isopropyl Alcohol 70%,Group 1 Tijori,Tijori Top Shelf,Bin A,1 1/2,Gallon,Yes,0.5,8.50,GOOD,GROUP1TI-0002,,
Extension Cord 10 ft,Group 1 Tijori,Tijori Bottom,,,No,,,FAIR,,Already labelled,
Zip Ties,Group 1 Tijori,Tijori Bottom,Sabha Bin,100,,Yes,20,,GOOD,GROUP1TI-0004,Mixed sizes,Yes
```

---

## Quantity parsing

The script handles all common quantity formats:

| CSV value  | Quantity | Unit |
|------------|----------|------|
| `3`        | 3.00     | —    |
| `1.5`      | 1.50     | —    |
| `1/2`      | 0.50     | —    |
| `1 1/2`    | 1.50     | —    |
| `10 ft`    | 10.00    | ft   |
| `1 Pack`   | 1.00     | Pack |
| `2 Packs`  | 2.00     | Packs |
| *(blank)*  | 1.00 (warning) | — |

When a unit is detected from the quantity string, the numeric amount is stored as
`quantity_total` and the unit is appended to the item's description as `[unit: ft]`.

If a separate **Unit** column is also provided:
- If the Quantity column has no unit, the Unit column value is used.
- If the Quantity column includes a unit and the Unit column says the same thing, no conflict.
- If they disagree, the row fails with a clear error.

Decimal quantities (1.5, 1/2, 1 1/2) are fully supported end-to-end — the database
stores quantities as `Numeric(10, 2)`.

---

## Consumable status

The **Consumable** column controls whether an item uses the checkout/return workflow
(`False`) or the mark-as-used workflow (`True`).

| Value | Result |
|-------|--------|
| `Yes`, `Y`, `True`, `1`, `✓` | `is_consumable = true` |
| `No`, `N`, `False`, `0` | `is_consumable = false` |
| *(blank)* | `is_consumable = false`, adds `[consumable: unknown]` note to description |
| Any other value | **Row fails** with a clear error |

If the Consumable column is blank, the item is imported as non-consumable with a
`[consumable: unknown]` note in its description. You can fix these later in the app.

---

## Low Stock Threshold

**Low stock is computed by the app, not manually imported as a Yes/No status.**

The **Low Stock Threshold** column sets the numeric threshold below which the app
considers the item low on stock:

```
quantity_available <= low_stock_threshold  →  item is considered low stock
```

| Value | Result |
|-------|--------|
| `5` | threshold = 5.0 |
| `1.5` | threshold = 1.5 |
| *(blank)* | threshold = null — app uses its default logic |
| `-1` | **Row fails** — must be >= 0 |
| `abc` | **Row fails** — must be a number |

Do **not** add a "Low Stock: Yes/No" column. Low stock is always computed from the threshold,
never imported as a manual flag.

---

## Condition

Valid values for the **Condition** column:

| Value | Description |
|-------|-------------|
| `GOOD` | Item is in good condition (default) |
| `FAIR` | Item shows normal wear |
| `POOR` | Item is functional but degraded |
| `DAMAGED` | Item is damaged |

The comparison is case-insensitive (`good`, `Good`, and `GOOD` all work).
Blank condition defaults to `GOOD`.
Any other value fails the row with a clear error listing valid options.

---

## SKU behavior

### Provided SKU

If the **SKU** column contains a value, it is imported as-is.

- If the same SKU appears twice in the CSV, the second row fails.
- If the SKU already exists in the system, the row fails.

### Auto-generated SKU

If the **SKU** column is blank (or a placeholder like `—`, `N/A`), the importer
generates a SKU automatically:

- **Prefix:** derived from the room name (uppercase, alphanumeric, max 8 chars)
  → `Group 1 Tijori` → `GROUP1TI`
- **Suffix:** 4-digit zero-padded counter, starting at 0001
  → `GROUP1TI-0001`, `GROUP1TI-0002`, …
- Counter skips any values already in use in the system or in the current CSV.

### SKU from the .xlsx template

The `.xlsx` template may auto-generate SKUs using a formula.
When you export to CSV, the formula result (e.g. `GROUP1TI-0001`) becomes plain text.
The importer treats it as a provided SKU — no special handling required.

### Dry-run report

The dry-run report shows for every row:
- `sku`: the value that would be imported
- `sku_source`: `provided` or `generated`

---

## What the script does with Rooms, Cabinets, Bins, Items

### Rooms
- All existing rooms are fetched at startup and cached.
- Missing rooms are created automatically.
- Room names are matched case-insensitively (trimmed).

### Cabinets
- Matched by `(room, cabinet_name)`, case-insensitively.
- Missing cabinets are created automatically under the correct room.

### Bins
- Matched by `(cabinet, bin_label)`, case-insensitively.
- Missing bins are created automatically under the correct cabinet.
- A blank **Bin** column (or placeholder like `—`, `N/A`) means the item is placed
  directly in the cabinet with no bin.

### Items
- Duplicate detection uses `(cabinet, bin, item_name)` (case-insensitive).
- If a match is found the row is **skipped**.
- If no match is found the item is created.

---

## Bin Requires Full Checkout

The **Bin Requires Full Checkout** column marks a bin so that its items can only be
checked out together as a unit, not individually.

| Value | Result |
|-------|--------|
| `Yes`, `Y`, `True`, `1`, `✓` | `requires_full_bin_checkout = true` |
| `No`, `N`, `False`, `0` | `requires_full_bin_checkout = false` |
| *(blank)* | Not specified — new bins default to `false`; existing bins are left unchanged |
| Any other value | **Row fails** with a clear error |

### Column aliases

All of the following column headers are recognised (case-insensitive):

- `Bin Requires Full Checkout`
- `Requires Full Bin Checkout`
- `Full Bin Checkout Required`
- `Bin Full Checkout Only`

### Conflict detection

If two rows in the same CSV reference the same bin and both provide **explicit** (non-blank)
values that disagree, the second row fails with a message pointing to the first row.  
Blank cells do not trigger conflicts — a blank cell inherits whatever the other rows set.

### Existing bins

If the CSV specifies an explicit `Yes` or `No` for a bin that already exists in the system,
the importer sends a `PATCH` request to update that bin's setting. This enables the
"retrofit" workflow: export the current sheet, fill in `Yes` for the bins that need
full-checkout enforcement, re-import — no manual frontend edits per bin required.

When the cell is blank, the existing bin's setting is left untouched.

### Enforcement

When `requires_full_bin_checkout` is `true`, individual item checkout attempts for items
in that bin are rejected with a 409 error. Items must be checked out via the **Check out bin**
button on the bin's detail page.

---

## Dry run vs. commit

| Flag        | Behaviour |
|-------------|-----------|
| *(default)* | Dry run — fetches existing data, plans the import, prints the summary, writes the report. **Nothing is created.** |
| `--commit`  | Applies the import — creates rooms, cabinets, bins, and items. |
| `--yes`     | Skips the confirmation prompt when targeting a non-local URL.  |

**Always do a dry run first.** Review the report, then run with `--commit`.

### Commit-mode safety gates

The importer will refuse to run `--commit` if:

1. **Any rows have errors** (invalid condition, bad quantity, duplicate SKU, etc.).
   Fix the CSV and retry.
2. **The sheet appears misaligned** (the Cabinet column contains numbers instead of names,
   suggesting the Quantity column shifted left).
   Correct the column order and retry.

---

## Import summary

After every run (dry or live) the script prints a summary:

```
============================================================
  Import Summary  [DRY RUN — no data written]
============================================================
  Rows read:                    12
  Items to create:              10
  Rows skipped (duplicate):     1
  Rows with errors/warnings:    1
  Rooms referenced:             2
  Cabinets referenced:          4
  Bins referenced:              2
  Unknown consumable (blank):   1
  Quantity parse warnings:      0
  Low-stock thresholds set:     8
  Unit prices set:              6
  Fractional/decimal qty rows:  2
  SKUs generated (blank):       3
  Duplicate SKUs found:         0
  Unknown columns ignored:      1
============================================================
```

---

## Import report

After every run two report files are written:

- `import_report.json` — machine-readable, full detail per row
- `import_report.csv` — spreadsheet-friendly version

Both files contain:

| Field | Description |
|-------|-------------|
| `row` | CSV row number (1 = header) |
| `action` | `create`, `skip`, or `warn` |
| `item` | Item name |
| `room` | Room name |
| `cabinet` | Cabinet name |
| `bin` | Bin label (or blank) |
| `quantity_total` | Parsed quantity value |
| `unit` | Unit (ft, Pack, etc.) |
| `consumable` | Parsed consumable flag |
| `low_stock_threshold` | Parsed threshold value (blank if not set) |
| `unit_price` | Parsed unit price (blank if not set) |
| `condition` | Condition value |
| `sku` | SKU value (provided or generated) |
| `sku_source` | `provided` or `generated` |
| `description` | Full description including structured markers |
| `warnings` | Semi-colon separated warnings for this row |
| `errors` | Semi-colon separated errors (row not imported) |
| `created_id` | Item ID returned by the API (commit mode only) |

Use a custom `--report` path to avoid overwriting previous reports:

```bash
python3 backend/scripts/import_inventory.py --csv inventory.csv \
  --report reports/import_2026_05_09
```

---

## Avoiding duplicates

The script is idempotent by default:

- Running it twice with the same CSV will skip all already-existing items on
  the second run.
- The summary will show 0 items to create and N rows skipped.
- No duplicates will be created.

To update an existing item (e.g. changed quantity) you currently need to edit it
in the app directly.

---

## How to safely test with fake data first

1. Set up a local dev server (see `docs/local-dev.md`).
2. Use `API_BASE_URL=http://localhost:8000` to point at the local instance.
3. Create a small test CSV with 2–3 fake rows.
4. Run a dry run, then a commit against local.
5. Verify the items appear in the app.
6. When satisfied, run against production.

No confirmation prompt is shown for `localhost` URLs, even with `--commit`.

---

## Full CLI reference

```
python3 backend/scripts/import_inventory.py --help

  --csv PATH       Path to CSV file or Google Sheets CSV export URL (required)
  --commit         Apply the import (default: dry run)
  --dry-run        Preview without writing (default behaviour)
  --yes, -y        Skip confirmation when targeting a non-local URL
  --report PATH    Base path for report files (default: import_report)
```

---

## Files changed by this feature

```
backend/scripts/__init__.py            (empty, makes scripts a package)
backend/scripts/import_helpers.py      (pure parsing helpers)
backend/scripts/import_inventory.py    (main CLI script)
backend/tests/test_import_helpers.py   (unit tests for helpers + CLI)
docs/inventory_import.md               (this file)
```

No direct database writes are performed — all writes go through the backend API.
