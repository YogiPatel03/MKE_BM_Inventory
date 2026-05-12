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

    def _api_patch(client: "httpx.Client", path: str, body: dict) -> Any:
        r = client.patch(path, json=body)
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

    def _api_patch(client: "_FallbackClient", path: str, body: dict) -> Any:  # type: ignore[misc]
        url = client.base_url + path
        data = _json.dumps(body).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Authorization": f"Bearer {client.token}", "Content-Type": "application/json"},
            method="PATCH",
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
    VALID_CONDITIONS,
    build_description,
    detect_shifted_sheet,
    generate_sku,
    is_blank_placeholder,
    normalize_headers,
    normalize_name,
    parse_bin_requires_full_checkout,
    parse_condition,
    parse_consumable,
    parse_low_stock_threshold,
    parse_quantity,
    parse_requires_request,
    parse_unit_price,
    room_sku_prefix,
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
        # bin_number_casefold → existing or planned bin metadata
        self.bins_by_number: dict[str, dict] = {}
        # bin id → existing bin metadata
        self.bin_records_by_id: dict[int, dict] = {}
        # (cabinet_id, bin_id_or_none, item_name_casefold) → dict (existing item)
        self.items: dict[tuple[int, Optional[int], str], dict] = {}
        # uppercase SKU → True (for existing-SKU conflict detection)
        self.skus: set[str] = set()

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
                self.bin_records_by_id[b["id"]] = b
                if b.get("bin_number"):
                    self.bins_by_number[normalize_name(b["bin_number"])] = b
        print(f"{len(self.bins)} found")

        print("  Fetching items …", end=" ", flush=True)
        all_items: list[dict] = []
        for cab_id in cabinet_ids:
            for item in _fetch_all_items(client, cab_id):
                bin_id = item.get("bin_id")
                key = (item["cabinet_id"], bin_id, normalize_name(item["name"]))
                self.items[key] = item
                all_items.append(item)
        print(f"{len(self.items)} found")

        # Index existing SKUs for conflict detection
        for item in all_items:
            if item.get("sku"):
                self.skus.add(item["sku"].upper())


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

    # SKU tracking within this CSV run
    _csv_skus: dict[str, int] = {}        # uppercase SKU → row_num (first seen)
    _sku_counters: dict[str, int] = {}    # prefix → next counter to try

    def get_col(row: dict, key: str, default: str = "") -> str:
        col_header = header_map.get(key)
        return row.get(col_header, default).strip() if col_header else default

    # Pre-scan: aggregate BFCO explicit values and validate bin-number identity
    # order-independently before planning creates. Bin number is the stable
    # physical-bin code; bin label remains the human-readable name.
    # BFCO key: (room_casefold, cab_casefold, shelf_casefold, bin_casefold, bin_number_casefold)
    # val: {"value": bool, "has_conflict": bool, "first_value": bool, "conflict_value": bool}
    _bin_bfco_prescan: dict[tuple, dict] = {}
    _bin_number_identity: dict[str, tuple[str, str, str, str]] = {}
    _conflicting_bin_numbers: dict[str, tuple[tuple[str, str, str, str], tuple[str, str, str, str]]] = {}
    _bin_label_number: dict[tuple[str, str, str, str], str] = {}
    _conflicting_bin_labels: dict[tuple[str, str, str, str], tuple[str, str]] = {}
    for _ps_idx, _ps_row in enumerate(rows, start=2):
        _ps_bin = get_col(_ps_row, "bin")
        _ps_room = get_col(_ps_row, "room")
        _ps_cab = get_col(_ps_row, "cabinet")
        _ps_shelf = get_col(_ps_row, "shelf_code")
        _ps_bin_number = get_col(_ps_row, "bin_number")
        if is_blank_placeholder(_ps_bin):
            _ps_bin = ""
        if is_blank_placeholder(_ps_room):
            _ps_room = ""
        if is_blank_placeholder(_ps_cab):
            _ps_cab = ""
        if is_blank_placeholder(_ps_shelf):
            _ps_shelf = ""
        if is_blank_placeholder(_ps_bin_number):
            _ps_bin_number = ""
        if not _ps_bin or not _ps_room or not _ps_cab:
            continue
        if _ps_bin_number:
            _ps_identity = (
                _ps_room.casefold(),
                _ps_cab.casefold(),
                _ps_shelf.casefold(),
                _ps_bin.casefold(),
            )
            _ps_number_key = _ps_bin_number.casefold()
            if _ps_number_key in _bin_number_identity and _bin_number_identity[_ps_number_key] != _ps_identity:
                _conflicting_bin_numbers[_ps_number_key] = (
                    _bin_number_identity[_ps_number_key],
                    _ps_identity,
                )
            else:
                _bin_number_identity[_ps_number_key] = _ps_identity

            _ps_label_key = _ps_identity
            if _ps_label_key in _bin_label_number and _bin_label_number[_ps_label_key] != _ps_number_key:
                _conflicting_bin_labels[_ps_label_key] = (
                    _bin_label_number[_ps_label_key],
                    _ps_number_key,
                )
            else:
                _bin_label_number[_ps_label_key] = _ps_number_key

        _ps_val, _ps_explicit, _ps_err = parse_bin_requires_full_checkout(
            get_col(_ps_row, "bin_requires_full_checkout")
        )
        if _ps_err or not _ps_explicit:
            continue
        _ps_key = (
            _ps_room.casefold(),
            _ps_cab.casefold(),
            _ps_shelf.casefold(),
            _ps_bin.casefold(),
            _ps_bin_number.casefold(),
        )
        if _ps_key not in _bin_bfco_prescan:
            _bin_bfco_prescan[_ps_key] = {
                "value": _ps_val, "has_conflict": False, "first_value": _ps_val,
            }
        elif _bin_bfco_prescan[_ps_key]["value"] != _ps_val:
            _bin_bfco_prescan[_ps_key]["has_conflict"] = True
            _bin_bfco_prescan[_ps_key]["conflict_value"] = _ps_val

    for idx, row in enumerate(rows, start=2):  # row 1 = header
        rr = RowResult(idx, row)

        # --- Read columns -----------------------------------------------
        item_name = get_col(row, "name")
        room_name = get_col(row, "room")
        quantity_raw = get_col(row, "quantity")
        cabinet_name = get_col(row, "cabinet")
        bin_label = get_col(row, "bin")
        shelf_code = get_col(row, "shelf_code")
        bin_number = get_col(row, "bin_number")
        consumable_raw = get_col(row, "consumable")
        notes_raw = get_col(row, "notes")
        unit_raw = get_col(row, "unit")
        lst_raw = get_col(row, "low_stock_threshold")
        unit_price_raw = get_col(row, "unit_price")
        condition_raw = get_col(row, "condition")
        sku_raw = get_col(row, "sku")
        bfco_raw = get_col(row, "bin_requires_full_checkout")
        requires_request_raw = get_col(row, "requires_request")

        # Combine separate unit column into quantity string when present and
        # quantity has no alphabetic characters yet, for backward compat with
        # sheets that use a separate Metric/Unit column.
        if unit_raw and not any(c.isalpha() for c in quantity_raw):
            quantity_raw = f"{quantity_raw} {unit_raw}".strip()
            unit_raw = ""  # unit will be extracted by parse_quantity

        # Normalize spreadsheet placeholder values (—, -, N/A, none, null, …)
        if is_blank_placeholder(item_name):
            item_name = ""
        if is_blank_placeholder(bin_label):
            bin_label = ""
        if is_blank_placeholder(shelf_code):
            shelf_code = ""
        if is_blank_placeholder(bin_number):
            bin_number = ""
        if bin_number:
            bin_number = bin_number.upper()
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
            rr.errors.append("Cabinet is blank — row skipped")
            rr.action = "warn"
            results.append(rr)
            continue

        rr.location = {
            "room": room_name,
            "cabinet": cabinet_name,
            "bin": bin_label,
            "shelf_code": shelf_code,
            "bin_number": bin_number,
        }

        if bin_label and not bin_number:
            rr.errors.append(
                f"Bin Number is required for bin '{bin_label}' — row skipped"
            )
            rr.action = "warn"
            results.append(rr)
            continue

        if bin_number and not bin_label:
            rr.errors.append(
                f"Bin label is required when Bin Number '{bin_number}' is provided — row skipped"
            )
            rr.action = "warn"
            results.append(rr)
            continue

        bin_number_key = bin_number.casefold() if bin_number else ""
        bin_identity_key = (
            room_name.casefold(),
            cabinet_name.casefold(),
            shelf_code.casefold(),
            bin_label.casefold(),
        )

        if bin_number_key in _conflicting_bin_numbers:
            first, second = _conflicting_bin_numbers[bin_number_key]
            rr.errors.append(
                f"Bin Number '{bin_number}' maps to conflicting bins/locations: "
                f"{first} vs {second} — fix before importing"
            )
            rr.action = "warn"
            results.append(rr)
            continue

        if bin_identity_key in _conflicting_bin_labels:
            first_number, second_number = _conflicting_bin_labels[bin_identity_key]
            rr.errors.append(
                f"Bin '{bin_label}' in this room/cabinet/shelf maps to multiple "
                f"Bin Numbers: {first_number} vs {second_number} — fix before importing"
            )
            rr.action = "warn"
            results.append(rr)
            continue

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

        # --- Unit: reconcile quantity-embedded unit with explicit unit column ---
        final_unit: Optional[str] = qty.unit

        if unit_raw:
            # unit_raw was NOT appended to quantity_raw (quantity already had alpha chars)
            if final_unit is None:
                final_unit = unit_raw
            elif final_unit.lower() != unit_raw.lower():
                rr.errors.append(
                    f"Unit conflict: quantity string implies unit='{final_unit}' "
                    f"but Unit column says '{unit_raw}' — row skipped"
                )
                rr.action = "warn"
                results.append(rr)
                continue
            # else: same value — no conflict

        # --- Consumable -------------------------------------------------
        cons = parse_consumable(consumable_raw)
        if cons.error:
            rr.errors.append(cons.error)
            rr.action = "warn"
            results.append(rr)
            continue

        if cons.is_unknown:
            rr.warnings.append(
                f"Consumable column is blank; defaulting to False. "
                "A [consumable: unknown] note will be added to the item."
            )

        # --- Low Stock Threshold ----------------------------------------
        lst = parse_low_stock_threshold(lst_raw)
        if lst.error:
            rr.errors.append(lst.error)
            rr.action = "warn"
            results.append(rr)
            continue

        # --- Unit Price -------------------------------------------------
        up = parse_unit_price(unit_price_raw)
        if up.error:
            rr.errors.append(up.error)
            rr.action = "warn"
            results.append(rr)
            continue

        # --- Condition --------------------------------------------------
        condition, cond_error = parse_condition(condition_raw)
        if cond_error:
            rr.errors.append(cond_error)
            rr.action = "warn"
            results.append(rr)
            continue

        # --- Bin Requires Full Checkout ---------------------------------
        bfco_value, bfco_explicit, bfco_error = parse_bin_requires_full_checkout(bfco_raw)
        if bfco_error:
            rr.errors.append(bfco_error)
            rr.action = "warn"
            results.append(rr)
            continue

        # --- Item Requires Request ---------------------------------------
        requires_request, requires_request_source, requires_request_error = parse_requires_request(
            requires_request_raw
        )
        if requires_request_error:
            rr.errors.append(requires_request_error)
            rr.action = "warn"
            results.append(rr)
            continue

        # Description ------------------------------------------------
        description = build_description(notes_raw, final_unit, cons.is_unknown)

        # --- Resolve room -----------------------------------------------
        room_key = room_name.casefold()
        if room_key not in cache.rooms:
            if room_key not in {k.casefold() for k in _rooms_to_create}:
                _rooms_to_create[room_key] = {"name": room_name}
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
        existing_bin_id: Optional[int] = None
        resolved_bfco_value: bool = False
        resolved_bfco_explicit: bool = False
        if bin_label:
            bfco_key = (
                room_key,
                cabinet_name.casefold(),
                shelf_code.casefold(),
                bin_label.casefold(),
                bin_number_key,
            )
            prescan_entry = _bin_bfco_prescan.get(bfco_key)

            if prescan_entry and prescan_entry["has_conflict"]:
                fv = prescan_entry["first_value"]
                cv = prescan_entry["conflict_value"]
                rr.errors.append(
                    f"Conflicting 'Bin Requires Full Checkout' for bin '{bin_label}': "
                    f"{fv} vs {cv} across rows — fix before importing"
                )
                rr.action = "warn"
                results.append(rr)
                continue

            resolved_bfco_value = prescan_entry["value"] if prescan_entry else False
            resolved_bfco_explicit = prescan_entry is not None

            bins_by_number = getattr(cache, "bins_by_number", {})
            bin_records_by_id = getattr(cache, "bin_records_by_id", {})
            bin_number_record = bins_by_number.get(bin_number_key)
            if bin_number_record:
                record_id = bin_number_record.get("id")
                record_cabinet_id = bin_number_record.get("cabinet_id")
                record_label = bin_number_record.get("label", "")
                if record_cabinet_id != cabinet_id_or_sentinel or normalize_name(record_label) != normalize_name(bin_label):
                    rr.errors.append(
                        f"Bin Number '{bin_number}' already belongs to "
                        f"'{record_label}' in cabinet {record_cabinet_id}; "
                        f"cannot also mean '{bin_label}' in this location"
                    )
                    rr.action = "warn"
                    results.append(rr)
                    continue
                bin_id_or_sentinel = record_id
                if isinstance(record_id, int):
                    existing_bin_id = record_id
            else:
                label_key_tuple = (cabinet_id_or_sentinel, bin_label.casefold())
                raw_bin_id = cache.bins.get(label_key_tuple)
                if isinstance(raw_bin_id, int):
                    existing_record = bin_records_by_id.get(raw_bin_id, {})
                    existing_number = existing_record.get("bin_number")
                    if existing_number and normalize_name(existing_number) != bin_number_key:
                        rr.errors.append(
                            f"Existing bin '{bin_label}' already has Bin Number "
                            f"'{existing_number}', not '{bin_number}' — row skipped"
                        )
                        rr.action = "warn"
                        results.append(rr)
                        continue
                    existing_bin_id = raw_bin_id
                    bin_id_or_sentinel = raw_bin_id
                else:
                    bin_id_or_sentinel = f"NEW:{bin_number}"

                bins_by_number[bin_number_key] = {
                    "id": bin_id_or_sentinel,
                    "cabinet_id": cabinet_id_or_sentinel,
                    "label": bin_label,
                    "bin_number": bin_number,
                }
                cache.bins[label_key_tuple] = bin_id_or_sentinel  # type: ignore[index,assignment]

        # --- Duplicate detection (name-based) ----------------------------
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

        # --- SKU resolution ---------------------------------------------
        sku_value: Optional[str] = None
        sku_source: str = "none"

        raw_sku = sku_raw.strip().upper() if sku_raw else ""
        if raw_sku and not is_blank_placeholder(raw_sku):
            # Provided SKU — check for intra-CSV and existing-backend conflicts
            upper_sku = raw_sku.upper()
            if upper_sku in _csv_skus:
                rr.errors.append(
                    f"Duplicate SKU '{raw_sku}' in this CSV (first seen at row {_csv_skus[upper_sku]}) — row skipped"
                )
                rr.action = "warn"
                results.append(rr)
                continue
            if upper_sku in cache.skus:
                rr.errors.append(
                    f"SKU '{raw_sku}' already exists in the system — row skipped"
                )
                rr.action = "warn"
                results.append(rr)
                continue
            sku_value = raw_sku
            sku_source = "provided"
            _csv_skus[upper_sku] = idx
            cache.skus.add(upper_sku)
        else:
            # Blank SKU — generate one
            prefix = f"{room_sku_prefix(room_name)}{cabinet_name.casefold()}"
            counter = _sku_counters.get(prefix, 0) + 1
            candidate = generate_sku(room_name, counter, cabinet_name)
            while candidate.upper() in cache.skus or candidate.upper() in _csv_skus:
                counter += 1
                candidate = generate_sku(room_name, counter, cabinet_name)
            _sku_counters[prefix] = counter
            sku_value = candidate
            sku_source = "generated"
            _csv_skus[candidate.upper()] = idx
            cache.skus.add(candidate.upper())

        # --- Build payload (sentinels replaced with real IDs at apply time) ---
        rr.item_payload = {
            "_room_name": room_name,
            "_cabinet_name": cabinet_name,
            "_bin_label": bin_label or None,
            "_bin_number": bin_number or None,
            "_shelf_code": shelf_code or None,
            "_bfco_explicit": resolved_bfco_explicit,
            "_existing_bin_id": existing_bin_id,
            "name": item_name,
            "quantity_total": qty.value,
            "is_consumable": cons.value,
            "description": description,
            "condition": condition,
            "unit": final_unit,
            "low_stock_threshold": lst.value,
            "unit_price": up.value,
            "sku": sku_value,
            "sku_source": sku_source,
            "bin_requires_full_checkout": resolved_bfco_value,
            "bin_number": bin_number or None,
            "requires_request": requires_request,
            "requires_request_source": requires_request_source,
        }
        rr.action = "create"
        results.append(rr)

    return results


def print_summary(results: list[RowResult], dry_run: bool, unknown_col_warnings: list[str] | None = None) -> None:
    creates = [r for r in results if r.action == "create"]
    skips = [r for r in results if r.action == "skip"]
    warns = [r for r in results if r.action == "warn" or r.errors]

    rooms_to_create: set[str] = set()
    cabinets_to_create: set[str] = set()
    bins_to_create: set[str] = set()
    unknown_consumable_rows: list[RowResult] = []
    qty_warning_rows: list[RowResult] = []
    lst_count = 0
    up_count = 0
    frac_qty_count = 0
    generated_sku_count = 0
    duplicate_sku_count = 0
    bfco_count = 0

    for r in creates:
        rooms_to_create.add(r.location.get("room", ""))
        cabinets_to_create.add(f"{r.location.get('room', '')} / {r.location.get('cabinet', '')}")
        b = r.location.get("bin", "—")
        if b and b != "—":
            bins_to_create.add(
                f"{r.location.get('cabinet', '')} / {b} "
                f"({r.location.get('bin_number', '')})"
            )
        for w in r.warnings:
            if "consumable" in w.lower():
                unknown_consumable_rows.append(r)
                break
        for w in r.warnings:
            if "quantity" in w.lower() or "parse" in w.lower() or (
                "blank" in w.lower() and "consumable" not in w.lower()
            ):
                qty_warning_rows.append(r)
                break
        p = r.item_payload or {}
        if p.get("low_stock_threshold") is not None:
            lst_count += 1
        if p.get("unit_price") is not None:
            up_count += 1
        qty_val = p.get("quantity_total", 0)
        if qty_val and qty_val != int(qty_val):
            frac_qty_count += 1
        if p.get("sku_source") == "generated":
            generated_sku_count += 1
        if p.get("bin_requires_full_checkout"):
            bfco_count += 1

    for r in warns:
        for e in r.errors:
            if "duplicate sku" in e.lower() or "already exists in this csv" in e.lower():
                duplicate_sku_count += 1
                break

    mode = "DRY RUN — no data written" if dry_run else "COMMITTED"
    print(f"\n{'='*60}")
    print(f"  Import Summary  [{mode}]")
    print(f"{'='*60}")
    print(f"  Rows read:                    {len(results)}")
    print(f"  Items to create:              {len(creates)}")
    print(f"  Rows skipped (duplicate):     {len(skips)}")
    print(f"  Rows with errors/warnings:    {len(warns)}")
    print(f"  Rooms referenced:             {len(rooms_to_create)}")
    print(f"  Cabinets referenced:          {len(cabinets_to_create)}")
    print(f"  Bins referenced:              {len(bins_to_create)}")
    print(f"  Unknown consumable (blank):   {len(unknown_consumable_rows)}")
    print(f"  Quantity parse warnings:      {len(qty_warning_rows)}")
    print(f"  Low-stock thresholds set:     {lst_count}")
    print(f"  Unit prices set:              {up_count}")
    print(f"  Fractional/decimal qty rows:  {frac_qty_count}")
    print(f"  SKUs generated (blank):       {generated_sku_count}")
    print(f"  Duplicate SKUs found:         {duplicate_sku_count}")
    print(f"  Bin full-checkout required:   {bfco_count}")
    if unknown_col_warnings:
        print(f"  Unknown columns ignored:      {len(unknown_col_warnings)}")
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

    real_room_ids: dict[str, int] = {}
    real_cabinet_ids: dict[tuple, int] = {}
    real_bin_ids: dict[str, int] = {}

    # Phase 1: PATCH existing bins before any item creation.
    # Collect from payloads (already resolved order-independently by process_rows).
    # Failure here propagates as RuntimeError, aborting item creation entirely.
    _pending_bin_patches: dict[int, dict[str, Any]] = {}
    for r in creates:
        p_tmp = r.item_payload
        if p_tmp.get("_existing_bin_id"):
            bin_id_tmp: int = p_tmp["_existing_bin_id"]
            patch_body = _pending_bin_patches.setdefault(bin_id_tmp, {})
            if p_tmp.get("_bfco_explicit"):
                patch_body["requires_full_bin_checkout"] = p_tmp["bin_requires_full_checkout"]
            if p_tmp.get("_bin_number"):
                patch_body["bin_number"] = p_tmp["_bin_number"]

    for bin_id_to_patch, patch_body in _pending_bin_patches.items():
        if not patch_body:
            continue
        _api_patch(client, f"/api/bins/{bin_id_to_patch}", patch_body)
        print(f"  Updated bin:     id={bin_id_to_patch} {patch_body}")

    # Phase 2: Create rooms, cabinets, new bins, and items.
    for r in creates:
        p = r.item_payload
        room_name: str = p["_room_name"]
        cabinet_name: str = p["_cabinet_name"]
        bin_label: Optional[str] = p["_bin_label"]
        bin_number: Optional[str] = p.get("_bin_number")

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
            bin_tuple = (bin_number or bin_label).casefold()
            bfco_value: bool = p.get("bin_requires_full_checkout", False)
            if bin_tuple not in real_bin_ids:
                existing_record = getattr(cache, "bins_by_number", {}).get(
                    normalize_name(bin_number or "")
                )
                existing_bin = existing_record.get("id") if existing_record else None
                if isinstance(existing_bin, int):
                    real_bin_ids[bin_tuple] = existing_bin
                    # PATCH already applied in Phase 1 — no scheduling needed
                else:
                    try:
                        created_bin = _api_post(client, "/api/bins", {
                            "label": bin_label,
                            "bin_number": bin_number,
                            "cabinet_id": cabinet_id,
                            "requires_full_bin_checkout": bfco_value,
                        })
                        real_bin_ids[bin_tuple] = created_bin["id"]
                        print(
                            f"  Created bin:     {bin_label} "
                            f"({bin_number}, id={created_bin['id']}, cabinet={cabinet_name})"
                        )
                    except Exception as exc:
                        r.errors.append(f"Failed to create bin '{bin_label}': {exc}")
                        r.action = "warn"
                        continue
            bin_id = real_bin_ids[bin_tuple]

        # --- Item -------------------------------------------------------
        item_body: dict[str, Any] = {
            "name": p["name"],
            "quantity_total": p["quantity_total"],
            "is_consumable": p["is_consumable"],
            "cabinet_id": cabinet_id,
            "condition": p["condition"],
        }
        if bin_id is not None:
            item_body["bin_id"] = bin_id
        if p.get("description"):
            item_body["description"] = p["description"]
        if p.get("sku") is not None:
            item_body["sku"] = p["sku"]
        if p.get("low_stock_threshold") is not None:
            item_body["low_stock_threshold"] = p["low_stock_threshold"]
        if p.get("unit_price") is not None:
            item_body["unit_price"] = p["unit_price"]
        item_body["requires_request"] = p.get("requires_request", False)

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
        p = r.item_payload or {}
        report.append({
            "row": r.row_num,
            "action": r.action,
            "item": p.get("name", ""),
            "room": r.location.get("room", ""),
            "cabinet": r.location.get("cabinet", ""),
            "bin": r.location.get("bin", ""),
            "shelf_code": r.location.get("shelf_code", ""),
            "bin_number": p.get("bin_number", "") or r.location.get("bin_number", ""),
            "quantity_total": p.get("quantity_total", ""),
            "unit": p.get("unit", ""),
            "consumable": p.get("is_consumable", ""),
            "low_stock_threshold": p.get("low_stock_threshold", ""),
            "unit_price": p.get("unit_price", ""),
            "condition": p.get("condition", ""),
            "sku": p.get("sku", ""),
            "sku_source": p.get("sku_source", ""),
            "bin_requires_full_checkout": p.get("bin_requires_full_checkout", ""),
            "requires_request": p.get("requires_request", ""),
            "requires_request_source": p.get("requires_request_source", ""),
            "description": p.get("description", ""),
            "warnings": "; ".join(r.warnings),
            "errors": "; ".join(r.errors),
            "created_id": p.get("_created_id", ""),
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

    # --- Preflight: reject .xlsx files before doing anything --------------
    csv_input = args.csv
    if not csv_input.startswith("http://") and not csv_input.startswith("https://"):
        suffix = Path(csv_input).suffix.lower()
        if suffix in (".xlsx", ".xls"):
            sys.exit(
                f"Error: '{csv_input}' is an Excel file (.{suffix.lstrip('.')}).\n"
                "Please export only the 'Inventory Import' sheet as CSV first:\n"
                "  File → Download → Comma Separated Values (.csv)\n"
                "Then run this script against the exported .csv file."
            )

    # --- Preflight: validate exact report output paths --------------------
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
        header_map, unknown_col_warnings = normalize_headers(raw_headers)
    except ValueError as exc:
        sys.exit(str(exc))

    if unknown_col_warnings:
        print("Column warnings:")
        for w in unknown_col_warnings:
            print(f"  [warn] {w}")
        print()

    # --- Shifted-sheet detection -------------------------------------------
    shift_warning = detect_shifted_sheet(rows, header_map)
    if shift_warning:
        print(f"[WARN] {shift_warning}\n")
        if not dry_run:
            sys.exit(
                "Aborting commit: sheet appears misaligned. "
                "Fix the CSV column order and retry."
            )

    # --- Fetch existing inventory ------------------------------------------
    print("Loading existing inventory …")
    cache = InventoryCache()
    cache.load(client)
    print()

    # --- Process rows (pure, no network) ----------------------------------
    results = process_rows(rows, header_map, cache)
    print_summary(results, dry_run, unknown_col_warnings)

    # --- Validation gate: refuse commit if any rows have errors -----------
    error_rows = [r for r in results if r.action == "warn" and r.errors]
    if not dry_run and error_rows:
        print(f"Cannot commit: {len(error_rows)} row(s) have errors. Fix them and retry.")
        sys.exit(1)

    # --- Apply (if --commit) -----------------------------------------------
    if not dry_run:
        print("Applying import …")
        apply_import(results, client, cache)
        print("\nImport complete.\n")
        print_summary(results, dry_run=False, unknown_col_warnings=unknown_col_warnings)

    # --- Write report ------------------------------------------------------
    print("Writing import report …")
    write_report(results, report_path)


if __name__ == "__main__":
    main()
