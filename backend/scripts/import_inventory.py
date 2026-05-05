#!/usr/bin/env python3
"""
Inventory import script — reads a CSV file and imports rows into the app
via the backend API (no direct database access).

Usage:
  # Dry run (default — safe, no data written):
  python backend/scripts/import_inventory.py --csv inventory.csv

  # Apply changes:
  python backend/scripts/import_inventory.py --csv inventory.csv --commit

  # Skip confirmation prompt when targeting a non-local URL:
  python backend/scripts/import_inventory.py --csv inventory.csv --commit --yes

Environment variables (or will be prompted interactively):
  API_BASE_URL   — e.g. https://mke-bm-inventry-api.onrender.com
  ADMIN_USERNAME
  ADMIN_PASSWORD
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
import urllib.request
import urllib.parse
from datetime import datetime
from getpass import getpass
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Try to use httpx (already in requirements.txt); fall back to urllib
# ---------------------------------------------------------------------------
try:
    import httpx

    def _make_client(base_url: str, token: str) -> "httpx.Client":
        return httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )

    def _api_get(client: "httpx.Client", path: str, params: dict | None = None) -> Any:
        r = client.get(path, params=params)
        r.raise_for_status()
        return r.json()

    def _api_post(client: "httpx.Client", path: str, body: dict) -> Any:
        r = client.post(path, json=body)
        r.raise_for_status()
        return r.json()

    def _login(base_url: str, username: str, password: str) -> str:
        with httpx.Client(base_url=base_url, timeout=30) as c:
            r = c.post("/api/auth/login", json={"username": username, "password": password})
            if r.status_code == 401:
                sys.exit("Login failed: invalid username or password.")
            r.raise_for_status()
            return r.json()["access_token"]

    _USE_HTTPX = True

except ImportError:
    import json as _json
    import urllib.error

    _USE_HTTPX = False

    class _FallbackClient:
        def __init__(self, base_url: str, token: str):
            self.base_url = base_url.rstrip("/")
            self.token = token

    def _make_client(base_url: str, token: str) -> "_FallbackClient":  # type: ignore[misc]
        return _FallbackClient(base_url, token)

    def _api_get(client: "_FallbackClient", path: str, params: dict | None = None) -> Any:  # type: ignore[misc]
        url = client.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {client.token}"})
        with urllib.request.urlopen(req) as resp:
            return _json.loads(resp.read())

    def _api_post(client: "_FallbackClient", path: str, body: dict) -> Any:  # type: ignore[misc]
        url = client.base_url + path
        data = _json.dumps(body).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Authorization": f"Bearer {client.token}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            return _json.loads(resp.read())

    def _login(base_url: str, username: str, password: str) -> str:  # type: ignore[misc]
        url = base_url.rstrip("/") + "/api/auth/login"
        data = _json.dumps({"username": username, "password": password}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as resp:
                return _json.loads(resp.read())["access_token"]
        except urllib.error.HTTPError as e:
            if e.code == 401:
                sys.exit("Login failed: invalid username or password.")
            raise


# ---------------------------------------------------------------------------
# Import from local helper module
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

_PAGE_SIZE = 500
_MAX_PAGES = 200  # hard ceiling: 200 × 500 = 100 000 items per cabinet


def _fetch_all_items(client: Any, cabinet_id: int) -> list[dict]:
    """Paginate /api/items for a single cabinet until all items are returned."""
    results: list[dict] = []
    skip = 0
    seen_ids: set = set()

    for page_num in range(_MAX_PAGES):
        page = _api_get(client, "/api/items", params={"cabinet_id": cabinet_id, "skip": skip, "limit": _PAGE_SIZE})
        if not page:
            break

        page_ids = {item.get("id") for item in page if item.get("id") is not None}
        if page_ids and page_ids.issubset(seen_ids):
            raise RuntimeError(
                f"Pagination loop detected fetching cabinet {cabinet_id}: "
                f"page {page_num + 1} returned only IDs already seen. "
                "The backend may be ignoring the 'skip' parameter."
            )
        seen_ids.update(page_ids)
        results.extend(page)

        if len(page) < _PAGE_SIZE:
            break
        skip += _PAGE_SIZE
    else:
        raise RuntimeError(
            f"Cabinet {cabinet_id} hit the {_MAX_PAGES}-page safety limit "
            f"({_MAX_PAGES * _PAGE_SIZE} items). Aborting to prevent runaway API calls."
        )

    return results

from import_helpers import (  # noqa: E402
    build_description,
    is_blank_placeholder,
    normalize_headers,
    normalize_name,
    parse_consumable,
    parse_quantity,
)


# ---------------------------------------------------------------------------
# Data classes for the import plan
# ---------------------------------------------------------------------------

class RowResult:
    """Outcome of processing one CSV row."""
    def __init__(self, row_num: int, raw: dict):
        self.row_num = row_num
        self.raw = raw
        self.action: str = "create"           # create | skip | warn
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self.item_payload: Optional[dict] = None
        self.location: dict = {}              # room/cabinet/bin names for report


# ---------------------------------------------------------------------------
# Inventory cache (fetched once, looked up by name)
# ---------------------------------------------------------------------------

class InventoryCache:
    def __init__(self):
        # name (casefold) → id
        self.rooms: dict[str, int] = {}
        # (room_id, cabinet_name_casefold) → id
        self.cabinets: dict[tuple[int, str], int] = {}
        # (cabinet_id, bin_label_casefold) → id
        self.bins: dict[tuple[int, str], int] = {}
        # (cabinet_id, bin_id_or_none, item_name_casefold) → dict (existing item)
        self.items: dict[tuple[int, Optional[int], str], dict] = {}

    def load(self, client: Any) -> None:
        print("  Fetching rooms …", end=" ", flush=True)
        for r in _api_get(client, "/api/rooms"):
            self.rooms[normalize_name(r["name"])] = r["id"]
        print(f"{len(self.rooms)} found")

        print("  Fetching cabinets …", end=" ", flush=True)
        for c in _api_get(client, "/api/cabinets"):
            key = (c["room_id"], normalize_name(c["name"]))
            self.cabinets[key] = c["id"]
        print(f"{len(self.cabinets)} found")

        print("  Fetching bins …", end=" ", flush=True)
        cabinet_ids = set(self.cabinets.values())
        for cab_id in cabinet_ids:
            for b in _api_get(client, "/api/bins", params={"cabinet_id": cab_id}):
                key = (b["cabinet_id"], normalize_name(b["label"]))
                self.bins[key] = b["id"]
        print(f"{len(self.bins)} found")

        print("  Fetching items …", end=" ", flush=True)
        for cab_id in cabinet_ids:
            for item in _fetch_all_items(client, cab_id):
                bin_id = item.get("bin_id")
                key = (item["cabinet_id"], bin_id, normalize_name(item["name"]))
                self.items[key] = item
        print(f"{len(self.items)} found")


# ---------------------------------------------------------------------------
# Main import logic
# ---------------------------------------------------------------------------

def process_rows(rows: list[dict], header_map: dict[str, str], cache: InventoryCache) -> list[RowResult]:
    """
    Convert CSV rows to RowResult objects.  No network calls — everything is
    resolved against the cache (pre-fetched) or marked as 'to create'.

    New rooms/cabinets/bins needed are tracked via side-effects on cache so
    later rows in the same import can reference them by the same name.
    """
    results: list[RowResult] = []

    # Counters for entities to create (tracked here so we can assign temp ids)
    _rooms_to_create: dict[str, dict] = {}           # name → payload
    _cabinets_to_create: dict[tuple, dict] = {}       # (room_key, name) → payload
    _bins_to_create: dict[tuple, dict] = {}           # (cab_key, label) → payload

    def get_col(row: dict, key: str, default: str = "") -> str:
        col_header = header_map.get(key)
        return row.get(col_header, default).strip() if col_header else default

    for idx, row in enumerate(rows, start=2):  # row 1 = header
        rr = RowResult(idx, row)

        # --- Read columns -----------------------------------------------
        item_name = get_col(row, "name")
        room_name = get_col(row, "room")
        quantity_raw = get_col(row, "quantity")
        cabinet_name = get_col(row, "place")
        bin_label = get_col(row, "bin")
        consumable_raw = get_col(row, "consumable")
        notes_raw = get_col(row, "notes")

        # Fall back to a separate Amount column when the Quantity cell is blank.
        # This handles sheets where Amount and Metric are separate columns and
        # both a Quantity header and an Amount header exist.
        if not quantity_raw:
            quantity_raw = get_col(row, "amount")

        # Combine separate Metric column into the quantity string when present.
        # Only append when quantity_raw has no alphabetic characters yet so we
        # do not double-append if the sheet already encodes unit in the string.
        metric_raw = get_col(row, "metric")
        if metric_raw and not any(c.isalpha() for c in quantity_raw):
            quantity_raw = f"{quantity_raw} {metric_raw}".strip()

        # Normalize spreadsheet placeholder values (—, -, N/A, none, null, …)
        if is_blank_placeholder(item_name):
            item_name = ""
        if is_blank_placeholder(bin_label):
            bin_label = ""
        if is_blank_placeholder(room_name):
            room_name = ""
        if is_blank_placeholder(cabinet_name):
            cabinet_name = ""

        if not item_name:
            rr.action = "skip"
            rr.warnings.append("Empty item name — row skipped")
            results.append(rr)
            continue

        if not room_name:
            rr.errors.append("Room is blank — row skipped")
            rr.action = "warn"
            results.append(rr)
            continue

        if not cabinet_name:
            rr.errors.append("Place/Cabinet is blank — row skipped")
            rr.action = "warn"
            results.append(rr)
            continue

        rr.location = {"room": room_name, "cabinet": cabinet_name, "bin": bin_label}

        # --- Quantity ---------------------------------------------------
        qty = parse_quantity(quantity_raw)
        rr.warnings.extend(qty.warnings)

        if qty.value <= 0:
            rr.errors.append(
                f"Quantity must be > 0 (got {qty.value} from '{quantity_raw}') — row skipped"
            )
            rr.action = "warn"
            results.append(rr)
            continue

        # --- Consumable -------------------------------------------------
        cons = parse_consumable(consumable_raw)
        if cons.is_unknown:
            rr.warnings.append(
                f"Consumable value '{consumable_raw}' is blank/unrecognised; "
                "defaulting to False. A [consumable: unknown] note will be added to the item."
            )

        # --- Description ------------------------------------------------
        description = build_description(notes_raw, qty.unit, cons.is_unknown)

        # --- Resolve room -----------------------------------------------
        room_key = room_name.casefold()
        if room_key not in cache.rooms:
            if room_key not in {k.casefold() for k in _rooms_to_create}:
                _rooms_to_create[room_key] = {"name": room_name}
            # Assign a sentinel so later same-name lookups work within this run
            cache.rooms[room_key] = f"NEW:{room_name}"  # type: ignore[assignment]

        room_id_or_sentinel = cache.rooms[room_key]

        # --- Resolve cabinet --------------------------------------------
        cab_key_tuple = (room_id_or_sentinel, cabinet_name.casefold())
        if cab_key_tuple not in cache.cabinets:
            tc_key = (room_key, cabinet_name.casefold())
            if tc_key not in _cabinets_to_create:
                _cabinets_to_create[tc_key] = {"name": cabinet_name, "room_sentinel": room_id_or_sentinel}
            cache.cabinets[cab_key_tuple] = f"NEW:{cabinet_name}"  # type: ignore[assignment]

        cabinet_id_or_sentinel = cache.cabinets[cab_key_tuple]

        # --- Resolve bin (optional) ------------------------------------
        bin_id_or_sentinel: Any = None
        if bin_label:
            bin_key_tuple = (cabinet_id_or_sentinel, bin_label.casefold())
            if bin_key_tuple not in cache.bins:
                tb_key = (room_key, cabinet_name.casefold(), bin_label.casefold())
                if tb_key not in _bins_to_create:
                    _bins_to_create[tb_key] = {
                        "label": bin_label,
                        "cabinet_sentinel": cabinet_id_or_sentinel,
                    }
                cache.bins[bin_key_tuple] = f"NEW:{bin_label}"  # type: ignore[assignment]
            bin_id_or_sentinel = cache.bins[bin_key_tuple]

        # --- Duplicate detection ----------------------------------------
        item_key = (
            cabinet_id_or_sentinel,
            bin_id_or_sentinel,
            normalize_name(item_name),
        )
        if item_key in cache.items:
            rr.action = "skip"
            rr.warnings.append(
                f"Item '{item_name}' already exists in {room_name} / {cabinet_name}"
                + (f" / {bin_label}" if bin_label else "")
                + " — skipped (use --update to overwrite)"
            )
            results.append(rr)
            continue

        # Mark as seen so later rows don't duplicate within the same import
        cache.items[item_key] = {"name": item_name, "_pending": True}

        # --- Build payload (sentinels replaced with real IDs at apply time) ---
        rr.item_payload = {
            "_room_name": room_name,
            "_cabinet_name": cabinet_name,
            "_bin_label": bin_label or None,
            "name": item_name,
            "quantity_total": qty.value,
            "is_consumable": cons.value,
            "description": description,
            "condition": "GOOD",
        }
        rr.action = "create"
        results.append(rr)

    return results


def print_summary(results: list[RowResult], dry_run: bool) -> None:
    creates = [r for r in results if r.action == "create"]
    skips = [r for r in results if r.action == "skip"]
    warns = [r for r in results if r.action == "warn" or r.errors]

    rooms_to_create: set[str] = set()
    cabinets_to_create: set[str] = set()
    bins_to_create: set[str] = set()
    unknown_consumable_rows: list[RowResult] = []
    qty_warning_rows: list[RowResult] = []

    for r in creates:
        rooms_to_create.add(r.location.get("room", ""))
        cabinets_to_create.add(f"{r.location.get('room', '')} / {r.location.get('cabinet', '')}")
        b = r.location.get("bin", "—")
        if b and b != "—":
            bins_to_create.add(f"{r.location.get('cabinet', '')} / {b}")
        for w in r.warnings:
            if "consumable" in w.lower():
                unknown_consumable_rows.append(r)
                break
        for w in r.warnings:
            if "quantity" in w.lower() or "parse" in w.lower() or "blank" in w.lower() and "consumable" not in w.lower():
                qty_warning_rows.append(r)
                break

    mode = "DRY RUN — no data written" if dry_run else "COMMITTED"
    print(f"\n{'='*60}")
    print(f"  Import Summary  [{mode}]")
    print(f"{'='*60}")
    print(f"  Rows read:                  {len(results)}")
    print(f"  Items to create:            {len(creates)}")
    print(f"  Rows skipped (duplicate):   {len(skips)}")
    print(f"  Rows with errors/warnings:  {len(warns)}")
    print(f"  Rooms referenced:           {len(rooms_to_create)}")
    print(f"  Cabinets referenced:        {len(cabinets_to_create)}")
    print(f"  Bins referenced:            {len(bins_to_create)}")
    print(f"  Unknown consumable status:  {len(unknown_consumable_rows)}")
    print(f"  Quantity parse warnings:    {len(qty_warning_rows)}")
    print(f"{'='*60}\n")

    if warns:
        print("Rows with errors (skipped):")
        for r in warns:
            print(f"  Row {r.row_num}: {r.errors or r.warnings}")
        print()

    if skips:
        print("Rows skipped (already exist):")
        for r in skips[:10]:
            print(f"  Row {r.row_num}: {r.warnings[0] if r.warnings else ''}")
        if len(skips) > 10:
            print(f"  … and {len(skips)-10} more")
        print()


def apply_import(results: list[RowResult], client: Any, cache: InventoryCache) -> list[RowResult]:
    """
    Walk through the RowResults and actually create rooms/cabinets/bins/items
    via the API.  Sentinels (NEW:X) are resolved to real IDs as we go.

    Modifies results in-place, adding errors if any API call fails.
    """
    creates = [r for r in results if r.action == "create" and r.item_payload]

    # We'll build name→real_id maps as we create things, keyed the same way
    # as the cache (which still holds sentinels for pending entities).
    real_room_ids: dict[str, int] = {}
    real_cabinet_ids: dict[tuple, int] = {}
    real_bin_ids: dict[tuple, int] = {}

    for r in creates:
        p = r.item_payload
        room_name: str = p["_room_name"]
        cabinet_name: str = p["_cabinet_name"]
        bin_label: Optional[str] = p["_bin_label"]

        # --- Room -------------------------------------------------------
        room_key = room_name.casefold()
        if room_key not in real_room_ids:
            existing = cache.rooms.get(room_key)
            if isinstance(existing, int):
                real_room_ids[room_key] = existing
            else:
                try:
                    created = _api_post(client, "/api/rooms", {"name": room_name})
                    real_room_ids[room_key] = created["id"]
                    print(f"  Created room:    {room_name} (id={created['id']})")
                except Exception as exc:
                    r.errors.append(f"Failed to create room '{room_name}': {exc}")
                    r.action = "warn"
                    continue

        room_id = real_room_ids[room_key]

        # --- Cabinet ----------------------------------------------------
        cab_tuple = (room_key, cabinet_name.casefold())
        if cab_tuple not in real_cabinet_ids:
            existing_cab = cache.cabinets.get((room_id, cabinet_name.casefold()))
            if isinstance(existing_cab, int):
                real_cabinet_ids[cab_tuple] = existing_cab
            else:
                try:
                    created_cab = _api_post(client, "/api/cabinets", {
                        "name": cabinet_name,
                        "room_id": room_id,
                    })
                    real_cabinet_ids[cab_tuple] = created_cab["id"]
                    print(f"  Created cabinet: {cabinet_name} (id={created_cab['id']}, room={room_name})")
                except Exception as exc:
                    r.errors.append(f"Failed to create cabinet '{cabinet_name}': {exc}")
                    r.action = "warn"
                    continue

        cabinet_id = real_cabinet_ids[cab_tuple]

        # --- Bin (optional) --------------------------------------------
        bin_id: Optional[int] = None
        if bin_label:
            bin_tuple = (cab_tuple, bin_label.casefold())
            if bin_tuple not in real_bin_ids:
                existing_bin = cache.bins.get((cabinet_id, bin_label.casefold()))
                if isinstance(existing_bin, int):
                    real_bin_ids[bin_tuple] = existing_bin
                else:
                    try:
                        created_bin = _api_post(client, "/api/bins", {
                            "label": bin_label,
                            "cabinet_id": cabinet_id,
                        })
                        real_bin_ids[bin_tuple] = created_bin["id"]
                        print(f"  Created bin:     {bin_label} (id={created_bin['id']}, cabinet={cabinet_name})")
                    except Exception as exc:
                        r.errors.append(f"Failed to create bin '{bin_label}': {exc}")
                        r.action = "warn"
                        continue
            bin_id = real_bin_ids[bin_tuple]

        # --- Item -------------------------------------------------------
        item_body = {
            "name": p["name"],
            "quantity_total": p["quantity_total"],
            "is_consumable": p["is_consumable"],
            "cabinet_id": cabinet_id,
            "condition": p["condition"],
        }
        if bin_id:
            item_body["bin_id"] = bin_id
        if p.get("description"):
            item_body["description"] = p["description"]

        try:
            created_item = _api_post(client, "/api/items", item_body)
            r.action = "create"
            r.item_payload["_created_id"] = created_item["id"]
        except Exception as exc:
            r.errors.append(f"Failed to create item '{p['name']}': {exc}")
            r.action = "warn"

    return results


def _preflight_report_paths(report_path: Path) -> tuple[Path, Path]:
    """
    Validate the exact report output paths before any credentials or API calls.

    - Creates the parent directory (including any missing parents).
    - Exits if either target (.json or .csv) is an existing directory.
    - Verifies the parent directory is writable using a unique temp file
      (no fixed sentinel filename that could clobber existing files).

    Returns the (json_path, csv_path) tuple on success.
    """
    json_path = report_path.with_suffix(".json")
    csv_path = report_path.with_suffix(".csv")

    report_path.parent.mkdir(parents=True, exist_ok=True)

    for check_path in (json_path, csv_path):
        if check_path.is_dir():
            sys.exit(
                f"Report path conflict: '{check_path}' is a directory. "
                "Choose a different --report base path."
            )

    try:
        with tempfile.NamedTemporaryFile(dir=report_path.parent, delete=True):
            pass
    except OSError as exc:
        sys.exit(f"Report directory is not writable ({report_path.parent}): {exc}")

    return json_path, csv_path


def write_report(results: list[RowResult], out_path: Path) -> None:
    report = []
    for r in results:
        report.append({
            "row": r.row_num,
            "action": r.action,
            "item": r.item_payload.get("name", "") if r.item_payload else "",
            "room": r.location.get("room", ""),
            "cabinet": r.location.get("cabinet", ""),
            "bin": r.location.get("bin", ""),
            "quantity": r.item_payload.get("quantity_total", "") if r.item_payload else "",
            "is_consumable": r.item_payload.get("is_consumable", "") if r.item_payload else "",
            "warnings": "; ".join(r.warnings),
            "errors": "; ".join(r.errors),
            "created_id": (r.item_payload or {}).get("_created_id", ""),
        })

    json_path = out_path.with_suffix(".json")
    csv_path = out_path.with_suffix(".csv")
    parent = out_path.parent

    # Write JSON atomically: temp file → replace final path
    tmp_json: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", dir=parent, delete=False, encoding="utf-8"
        ) as tf:
            json.dump(report, tf, indent=2)
            tmp_json = Path(tf.name)
        tmp_json.replace(json_path)
        print(f"  Report written: {json_path}")
    except Exception:
        if tmp_json is not None:
            tmp_json.unlink(missing_ok=True)
        raise

    # Write CSV atomically: temp file → replace final path
    tmp_csv: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", dir=parent, delete=False,
            encoding="utf-8", newline=""
        ) as tf:
            if report:
                writer = csv.DictWriter(tf, fieldnames=list(report[0].keys()))
                writer.writeheader()
                writer.writerows(report)
            tmp_csv = Path(tf.name)
        tmp_csv.replace(csv_path)
        print(f"  Report written: {csv_path}")
    except Exception:
        if tmp_csv is not None:
            tmp_csv.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import inventory from a CSV file into the cabinet-inventory app."
    )
    parser.add_argument("--csv", required=True, help="Path to CSV file (or a Google Sheets CSV export URL)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", default=True,
                       help="Preview what would be imported without writing anything (default)")
    group.add_argument("--commit", action="store_true",
                       help="Actually import data into the app")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Skip confirmation prompt when targeting a non-local URL")
    parser.add_argument("--report", default="import_report",
                        help="Base path for report files (default: import_report)")
    args = parser.parse_args()

    dry_run = not args.commit

    # --- Preflight: validate exact report output paths ---------------------
    # Runs before credential prompts, auth, or any API call so that a bad
    # path causes an immediate, clear failure rather than one discovered
    # after production data has already been written.
    report_path = Path(args.report)
    _preflight_report_paths(report_path)

    # --- Credentials & base URL ----------------------------------------
    base_url = os.environ.get("API_BASE_URL", "").rstrip("/")
    if not base_url:
        base_url = input("API_BASE_URL (e.g. https://mke-bm-inventry-api.onrender.com): ").strip().rstrip("/")
    if not base_url:
        sys.exit("API_BASE_URL is required.")

    username = os.environ.get("ADMIN_USERNAME", "")
    if not username:
        username = input("Admin username: ").strip()

    password = os.environ.get("ADMIN_PASSWORD", "")
    if not password:
        password = getpass("Admin password: ")

    # --- Confirmation for non-local commit ------------------------------------------
    is_local = "localhost" in base_url or "127.0.0.1" in base_url
    if args.commit and not is_local and not args.yes:
        print(f"\nTarget API: {base_url}")
        print("This will write data to the production server.")
        confirm = input("Type 'yes' to continue: ").strip().lower()
        if confirm != "yes":
            sys.exit("Aborted.")

    print(f"\nTarget API: {base_url}")
    print(f"Mode:       {'DRY RUN' if dry_run else 'COMMIT'}\n")

    # --- Login -------------------------------------------------------------
    print("Authenticating …")
    token = _login(base_url, username, password)
    print("Login successful.\n")

    client = _make_client(base_url, token)

    # --- Load CSV ----------------------------------------------------------
    csv_input = args.csv
    rows: list[dict] = []
    raw_headers: list[str] = []

    if csv_input.startswith("http://") or csv_input.startswith("https://"):
        print(f"Downloading CSV from {csv_input} …")
        with urllib.request.urlopen(csv_input) as resp:
            content = resp.read().decode("utf-8")
        reader = csv.DictReader(content.splitlines())
        raw_headers = list(reader.fieldnames or [])
        rows = list(reader)
    else:
        csv_path = Path(csv_input)
        if not csv_path.exists():
            sys.exit(f"CSV file not found: {csv_path}")
        with csv_path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            raw_headers = list(reader.fieldnames or [])
            rows = list(reader)

    if not rows:
        sys.exit("CSV file is empty or has no data rows.")

    print(f"CSV loaded: {len(rows)} data row(s), columns: {raw_headers}\n")

    # --- Validate headers --------------------------------------------------
    try:
        header_map = normalize_headers(raw_headers)
    except ValueError as exc:
        sys.exit(str(exc))

    # --- Fetch existing inventory ------------------------------------------
    print("Loading existing inventory …")
    cache = InventoryCache()
    cache.load(client)
    print()

    # --- Process rows (pure, no network) ----------------------------------
    results = process_rows(rows, header_map, cache)
    print_summary(results, dry_run)

    # --- Apply (if --commit) -----------------------------------------------
    if not dry_run:
        print("Applying import …")
        apply_import(results, client, cache)
        print("\nImport complete.\n")
        print_summary(results, dry_run=False)

    # --- Write report ------------------------------------------------------
    print("Writing import report …")
    write_report(results, report_path)


if __name__ == "__main__":
    main()
