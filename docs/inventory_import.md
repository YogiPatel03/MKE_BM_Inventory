# Inventory Import Tool

A reusable script that reads a CSV file (or Google Sheets CSV export) and imports
inventory rows into the app through the backend API — no direct database access.

---

## Quick start

```bash
# 1. Export your Google Sheet as CSV (see below)

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

## Required permissions

The admin account must have inventory, cabinet, bin, and room management
permissions (i.e. `can_manage_users = True` or all four `can_manage_*` flags).
A normal admin account created in the app will have all of these by default.

---

## How to export the Google Sheet as CSV

1. Open the Google Sheet.
2. Click **File → Download → Comma Separated Values (.csv)**.
3. Save the file somewhere convenient (e.g. `~/Downloads/inventory.csv`).
4. Run the import script against that file.

You can also point the script directly at a Google Sheets CSV export URL:

```
https://docs.google.com/spreadsheets/d/<SHEET_ID>/export?format=csv&gid=0
```

Replace `<SHEET_ID>` with the ID from your sheet URL.  
`gid=0` is the first tab; change it if your data is on a different tab (the gid
appears in the URL when you click on a tab in Google Sheets).

```bash
python3 backend/scripts/import_inventory.py \
  --csv "https://docs.google.com/spreadsheets/d/1MytKUR.../export?format=csv&gid=0"
```

---

## Expected CSV columns

The script recognises these column names (case-insensitive, whitespace trimmed):

| Column            | Maps to     | Required? | Notes                            |
|-------------------|-------------|-----------|----------------------------------|
| `Name` / `Item`   | Item name   | Yes       |                                  |
| `Room`            | Room        | Yes       |                                  |
| `Quantity` / `Amount` | Quantity | Yes      | See quantity parsing below       |
| `Place` / `Cabinet` | Cabinet   | Yes       | e.g. Tijori, Cabinet Top         |
| `Bin` / `Bin (if any)` | Bin    | No        | Leave blank if no bin            |
| `Consumable`      | Consumable  | No        | Yes/No/blank — see below         |
| `Notes`           | Description | No        |                                  |

Extra columns in your CSV are silently ignored.

---

## Quantity parsing

The script handles all common quantity formats:

| CSV value  | Parsed as          |
|------------|--------------------|
| `3`        | 3.00               |
| `1.5`      | 1.50               |
| `1/2`      | 0.50               |
| `1 1/2`    | 1.50               |
| `10 ft`    | 10.00, unit = "ft" |
| `1 Pack`   | 1.00, unit = "Pack"|
| *(blank)*  | 1.00 (with warning)|

When a unit is detected (e.g. "ft", "Pack") the numeric amount is stored as
`quantity_total` and the unit is appended to the item's description as
`[unit: ft]` so the information is not lost.

If the quantity cannot be parsed at all (e.g. pure text with no number), the
script defaults to 1.00, sets the raw text as the unit, and logs a warning in
the report.

---

## Unknown consumable status

The backend requires `is_consumable` to be `true` or `false` — there is no
database-level "unknown" option.

When the `Consumable` column is blank or contains an unrecognised value:

1. `is_consumable` is set to `false` (safe default — item uses the checkout/return flow).
2. A structured marker `[consumable: unknown]` is appended to the item's description.
3. The row is counted in the report under **unknown consumable status**.

To fix these items later: open the item in the app and set the consumable flag
correctly, then remove the `[consumable: unknown]` note from the description.

Recognised truthy values: `Yes`, `Y`, `True`, `1`, `✓`, `consumable`  
Recognised falsy values: `No`, `N`, `False`, `0`, `non-consumable`

---

## What the script does with Rooms, Cabinets, Bins, Items

### Rooms
- All existing rooms are fetched at startup and cached.
- If a row references a room that doesn't exist, the room is created automatically.
- Room names are matched case-insensitively (trimmed).

### Cabinets
- All existing cabinets are fetched and cached by (room_id, cabinet_name).
- Missing cabinets are created automatically under the correct room.

### Bins
- All existing bins are fetched per cabinet and cached by (cabinet_id, label).
- Missing bins are created automatically under the correct cabinet.
- A blank `Bin` column means the item is placed directly in the cabinet with no bin.

### Items
- The script checks for an existing active item with the same name in the same
  Cabinet + Bin location.
- If a match is found the row is **skipped** and a warning is logged.
- If no match is found the item is created.
- The idempotency key is: `(cabinet_id, bin_id, name.casefold().strip())`.

---

## Dry run vs. commit

| Flag        | Behaviour                                                      |
|-------------|----------------------------------------------------------------|
| *(default)* | Dry run — fetches existing data, plans the import, prints the summary, writes the report. **Nothing is created.** |
| `--commit`  | Applies the import — creates rooms, cabinets, bins, and items. |
| `--yes`     | Skips the confirmation prompt when targeting a non-local URL.  |

**Always do a dry run first.** Review the report, then run with `--commit`.

---

## Import report

After every run (dry or live) two report files are written:

- `import_report.json` — machine-readable, full detail per row
- `import_report.csv` — spreadsheet-friendly version

Both files contain:

| Field          | Description                                     |
|----------------|-------------------------------------------------|
| `row`          | CSV row number (1 = header)                     |
| `action`       | `create`, `skip`, or `warn`                     |
| `item`         | Item name                                       |
| `room`         | Room name                                       |
| `cabinet`      | Cabinet name                                    |
| `bin`          | Bin label (or "—")                              |
| `quantity`     | Parsed quantity value                           |
| `is_consumable`| Parsed consumable flag                          |
| `warnings`     | Semi-colon separated warnings for this row      |
| `errors`       | Semi-colon separated errors (row not imported)  |
| `created_id`   | Item ID returned by the API (commit mode only)  |

Use a custom `--report` path to avoid overwriting previous reports:

```bash
python3 backend/scripts/import_inventory.py --csv inventory.csv \
  --report reports/import_2026_05_03
```

---

## Avoiding duplicates

The script is idempotent by default:

- Running it twice with the same CSV will skip all already-existing items on
  the second run.
- The summary will show 0 items to create and N rows skipped.
- No duplicates will be created.

To update an existing item (e.g. changed quantity) you currently need to edit it
in the app directly. An `--update` flag is not implemented to keep the default
behavior safe.

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
backend/tests/test_import_helpers.py   (59 unit tests for helpers)
docs/inventory_import.md               (this file)
```

No existing files were modified.  
No database migrations required.  
No backend routes were added.
