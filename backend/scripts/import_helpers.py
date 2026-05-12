"""
Parsing helpers for the inventory import script.
All functions are pure (no I/O) so they can be unit-tested in isolation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Optional


# ---------------------------------------------------------------------------
# Quantity parsing
# ---------------------------------------------------------------------------

@dataclass
class QuantityResult:
    value: float
    unit: Optional[str] = None
    warnings: list[str] = field(default_factory=list)


# Regex atoms
_INT = r"\d+"
_FRAC = rf"{_INT}/{_INT}"          # e.g. 1/2
_MIXED = rf"{_INT}\s+{_FRAC}"     # e.g. 1 1/2
_DEC = r"\d+(?:\.\d+)?"           # e.g. 3.14

# Full numeric patterns — ordered longest-match first
_MIXED_RE = re.compile(rf"^({_INT})\s+({_INT})/({_INT})\s*(.*)", re.IGNORECASE)
_FRAC_RE = re.compile(rf"^({_INT})/({_INT})\s*(.*)", re.IGNORECASE)
_DEC_RE = re.compile(rf"^({_DEC})\s*(.*)", re.IGNORECASE)


def parse_quantity(raw: str) -> QuantityResult:
    """
    Parse a quantity string from the import sheet into a numeric value and an
    optional unit string.

    Supported formats:
      "3"       → 3.0, no unit
      "1.5"     → 1.5, no unit
      "1/2"     → 0.5, no unit
      "1 1/2"   → 1.5, no unit
      "10 ft"   → 10.0, unit="ft"
      "1 Pack"  → 1.0, unit="Pack"
      "5 Packs" → 5.0, unit="Packs"
      ""        → 1.0 with a warning (default)
    """
    s = raw.strip() if raw else ""

    if not s:
        return QuantityResult(value=1.0, warnings=["Quantity was blank; defaulted to 1"])

    m = _MIXED_RE.match(s)
    if m:
        whole, num, den, rest = m.group(1), m.group(2), m.group(3), m.group(4).strip()
        try:
            value = float(int(whole) + Fraction(int(num), int(den)))
        except (ZeroDivisionError, ValueError):
            return QuantityResult(
                value=0.0,
                warnings=[f"Invalid quantity '{s}': division by zero in fraction — row will be skipped"],
            )
        if "/" in rest:
            return QuantityResult(
                value=0.0,
                warnings=[f"Quantity '{s}' looks like a malformed fraction — row will be skipped"],
            )
        unit = rest if rest else None
        return QuantityResult(value=round(value, 2), unit=unit)

    m = _FRAC_RE.match(s)
    if m:
        num, den, rest = m.group(1), m.group(2), m.group(3).strip()
        try:
            value = float(Fraction(int(num), int(den)))
        except (ZeroDivisionError, ValueError):
            return QuantityResult(
                value=0.0,
                warnings=[f"Invalid quantity '{s}': division by zero in fraction — row will be skipped"],
            )
        if "/" in rest:
            return QuantityResult(
                value=0.0,
                warnings=[f"Quantity '{s}' looks like a malformed fraction — row will be skipped"],
            )
        unit = rest if rest else None
        return QuantityResult(value=round(value, 2), unit=unit)

    m = _DEC_RE.match(s)
    if m:
        value = float(m.group(1))
        rest = m.group(2).strip()
        if "/" in rest:
            return QuantityResult(
                value=0.0,
                warnings=[f"Quantity '{s}' looks like a malformed fraction — row will be skipped"],
            )
        unit = rest if rest else None
        return QuantityResult(value=round(value, 2), unit=unit)

    # Nothing matched — text-only value like "Pack".
    # Reject strings containing "/" as likely malformed fractions, not unit names.
    if "/" in s:
        return QuantityResult(
            value=0.0,
            warnings=[f"Quantity '{s}' looks like a malformed fraction — row will be skipped"],
        )
    return QuantityResult(
        value=1.0,
        unit=s,
        warnings=[f"Could not parse quantity '{s}' as a number; defaulted to 1 with unit='{s}'"],
    )


# ---------------------------------------------------------------------------
# Consumable parsing
# ---------------------------------------------------------------------------

_TRUE_VALUES = {"yes", "y", "true", "1", "x", "✓", "consumable"}
_FALSE_VALUES = {"no", "n", "false", "0", "non-consumable", "nonconsumable"}


@dataclass
class ConsumableResult:
    value: bool                  # always a bool for the API
    is_unknown: bool = False     # True only when blank — add [consumable: unknown] note
    raw: str = ""
    error: Optional[str] = None  # non-None when non-blank value is unrecognized → fail the row


def parse_consumable(raw: str) -> ConsumableResult:
    """
    Parse the Consumable column into a boolean for the API.

    - Blank → False, is_unknown=True (note added to description; row not failed)
    - Recognized true/false → appropriate bool, no error
    - Non-blank unrecognized → error field set; caller should fail the row
    """
    s = raw.strip().lower() if raw else ""

    if not s:
        return ConsumableResult(value=False, is_unknown=True, raw="")

    if s in _TRUE_VALUES:
        return ConsumableResult(value=True, is_unknown=False, raw=raw.strip())
    if s in _FALSE_VALUES:
        return ConsumableResult(value=False, is_unknown=False, raw=raw.strip())

    return ConsumableResult(
        value=False,
        is_unknown=False,
        raw=raw.strip(),
        error=(
            f"Unrecognized Consumable value '{raw.strip()}': "
            "expected Yes/No/True/False/Y/N/1/0"
        ),
    )


# ---------------------------------------------------------------------------
# Bin requires-full-checkout parsing
# ---------------------------------------------------------------------------

def parse_bin_requires_full_checkout(raw: str) -> tuple[bool, bool, Optional[str]]:
    """
    Parse Bin Requires Full Checkout column.

    Returns (value, is_explicit, error):
      Blank / placeholder → (False, False, None)  — caller skips conflict tracking
      Yes/True/Y/1/✓     → (True,  True,  None)
      No/False/N/0       → (False, True,  None)
      Other non-blank    → (False, False, error)  — caller fails the row
    """
    s = raw.strip().lower() if raw else ""
    if not s or is_blank_placeholder(s):
        return False, False, None
    if s in _TRUE_VALUES:
        return True, True, None
    if s in _FALSE_VALUES:
        return False, True, None
    return False, False, (
        f"Unrecognized Bin Requires Full Checkout value '{raw.strip()}': "
        "expected Yes/No/True/False/Y/N/1/0"
    )


# ---------------------------------------------------------------------------
# Condition parsing
# ---------------------------------------------------------------------------

VALID_CONDITIONS: frozenset[str] = frozenset({"GOOD", "FAIR", "POOR", "DAMAGED"})


def parse_condition(raw: str) -> tuple[str, Optional[str]]:
    """
    Parse a Condition column value.

    Returns (condition_value, error_or_None).
    Blank → "GOOD" with no error.
    Valid (case-insensitive) → uppercase value, no error.
    Invalid non-blank → "GOOD" with error message.
    """
    s = raw.strip().upper() if raw else ""
    if not s or is_blank_placeholder(s):
        return "GOOD", None
    if s in VALID_CONDITIONS:
        return s, None
    return (
        "GOOD",
        f"Invalid condition '{raw.strip()}': must be one of {sorted(VALID_CONDITIONS)}",
    )


# ---------------------------------------------------------------------------
# Numeric field parsing (low_stock_threshold, unit_price)
# ---------------------------------------------------------------------------

@dataclass
class NumericResult:
    value: Optional[float]
    error: Optional[str] = None


def parse_low_stock_threshold(raw: str) -> NumericResult:
    """
    Parse a Low Stock Threshold column value.

    Blank / placeholder → None (use app default logic).
    Valid non-negative number → rounded float.
    Invalid or negative → error.
    """
    s = raw.strip() if raw else ""
    if not s or is_blank_placeholder(s):
        return NumericResult(value=None)
    try:
        v = float(s)
    except ValueError:
        return NumericResult(
            value=None,
            error=f"Invalid low stock threshold '{s}': must be a number",
        )
    if v < 0:
        return NumericResult(
            value=None,
            error=f"Invalid low stock threshold '{s}': must be >= 0",
        )
    return NumericResult(value=round(v, 2))


def parse_unit_price(raw: str) -> NumericResult:
    """
    Parse a Unit Price column value.

    Blank / placeholder → None.
    Accepts optional leading '$' (e.g. "$5.00").
    Valid non-negative number → rounded float (0 is allowed — free item).
    Invalid or negative → error.
    """
    s = raw.strip() if raw else ""
    if not s or is_blank_placeholder(s):
        return NumericResult(value=None)
    # Strip optional leading currency symbol
    s_stripped = s.lstrip("$").strip()
    try:
        v = float(s_stripped)
    except ValueError:
        return NumericResult(
            value=None,
            error=f"Invalid unit price '{raw.strip()}': must be a number",
        )
    if v < 0:
        return NumericResult(
            value=None,
            error=f"Invalid unit price '{raw.strip()}': must be >= 0",
        )
    return NumericResult(value=round(v, 2))


# ---------------------------------------------------------------------------
# SKU generation
# ---------------------------------------------------------------------------

def room_sku_prefix(room_name: str) -> str:
    """
    Convert a room name to the import SKU room abbreviation.

    "Shishu Mandal" → "SM"
    "Group 1"       → "G1"
    "Room A"        → "RA"
    ""              → "ITEM"
    """
    cleaned = re.sub(r"[^A-Za-z0-9\s]", "", room_name)
    words = cleaned.upper().split()
    if not words:
        return "ITEM"
    if words[0] == "GROUP" and len(words) > 1:
        return f"G{re.sub(r'[^0-9A-Z]', '', words[1])}"[:4]
    if len(words) == 1:
        return words[0][:4]
    return "".join(word[0] for word in words if word)[:4] or "ITEM"


def cabinet_sku_code(cabinet_name: str) -> str:
    """Return the cabinet/tijori code segment for generated item SKUs."""
    normalized = cabinet_name.casefold()
    if "tijori" in normalized or normalized.startswith("t"):
        return "T"
    return "C"


def generate_sku(room_name: str, counter: int, cabinet_name: str = "") -> str:
    """
    Generate a deterministic item-level SKU from room, cabinet type, and counter.

    Counter should start at 1 and increment until a unique item SKU is found.
    Example: generate_sku("Shishu Mandal", 1, "Cabinet") → "SMC1"
    """
    return f"{room_sku_prefix(room_name)}{cabinet_sku_code(cabinet_name)}{counter}"


# ---------------------------------------------------------------------------
# Shifted-sheet detection
# ---------------------------------------------------------------------------

# Matches strings that look like quantity values: integers, decimals, fractions,
# mixed numbers, or numbers followed by a unit word.
_NUMERIC_LIKE_RE = re.compile(
    r"^\d+(\s+\d+/\d+|[./]\d+|\s+[a-zA-Z]+[a-zA-Z ]*)?\s*$"
)


def detect_shifted_sheet(
    rows: list[dict], header_map: dict[str, str]
) -> Optional[str]:
    """
    Return a warning message if the sheet appears to have a column-shift problem.

    Heuristic: ≥30% of rows have a blank Quantity column AND a Cabinet column value
    that looks like a quantity (number, fraction, or number+unit).
    """
    qty_h = header_map.get("quantity")
    cab_h = header_map.get("cabinet")
    if not qty_h or not cab_h or not rows:
        return None

    flagged = sum(
        1
        for r in rows
        if not r.get(qty_h, "").strip()
        and _NUMERIC_LIKE_RE.match(r.get(cab_h, "").strip() or "")
    )

    if flagged / len(rows) >= 0.3:
        return (
            f"Sheet appears misaligned: {flagged}/{len(rows)} rows have a blank Quantity "
            "column and a numeric-looking Cabinet value. "
            "Verify column order before importing."
        )
    return None


# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------

def normalize_name(name: str) -> str:
    """Trim whitespace and casefold for duplicate-detection comparisons."""
    return name.strip().casefold()


# ---------------------------------------------------------------------------
# Blank-placeholder detection
# ---------------------------------------------------------------------------

_BLANK_PLACEHOLDERS: frozenset[str] = frozenset({
    "—", "-", "n/a", "na", "none", "null",
})


def is_blank_placeholder(value: str) -> bool:
    """
    Return True when value is a spreadsheet placeholder meaning 'no value'.
    Matched (case-insensitive, whole stripped string): —  -  N/A  NA  none  null
    Multi-word or dash-containing names like 'Pre-K Supplies' are NOT matched.
    """
    s = value.strip() if value else ""
    return not s or s.casefold() in _BLANK_PLACEHOLDERS


# ---------------------------------------------------------------------------
# Description builder
# ---------------------------------------------------------------------------

def build_description(
    notes: str,
    unit: Optional[str],
    consumable_unknown: bool,
) -> Optional[str]:
    """
    Compose the item description from import-time metadata.

    Structured markers are kept on separate lines so they can be stripped
    cleanly on re-import:
      [unit: Pack]
      [consumable: unknown]
    """
    parts: list[str] = []

    notes_clean = notes.strip() if notes else ""
    if notes_clean:
        parts.append(notes_clean)

    if unit:
        parts.append(f"[unit: {unit}]")

    if consumable_unknown:
        parts.append("[consumable: unknown]")

    return "\n".join(parts) if parts else None


# ---------------------------------------------------------------------------
# CSV column normalisation
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS = {"name", "room", "quantity", "cabinet"}
OPTIONAL_COLUMNS = {
    "bin", "consumable", "notes", "unit",
    "low_stock_threshold", "unit_price", "condition", "sku",
    "bin_requires_full_checkout", "shelf_code", "bin_number",
}

# Map of normalised (casefold+strip) header → canonical key
_HEADER_ALIASES: dict[str, str] = {
    # name
    "name": "name",
    "item": "name",
    "item name": "name",
    # room
    "room": "room",
    # quantity — "amount" maps directly here (no separate "amount" canonical)
    "quantity": "quantity",
    "qty": "quantity",
    "amount": "quantity",
    "quantity (amount and metric)": "quantity",
    "quantity (amount & metric)": "quantity",
    "quantity amount and metric": "quantity",
    "quantity amount metric": "quantity",
    # cabinet (canonical; "place" is a legacy alias)
    "cabinet": "cabinet",
    "place": "cabinet",
    "storage location": "cabinet",
    "shelf": "cabinet",
    "location": "cabinet",
    "place (tijori/cabinet top/cabinet bottom)": "cabinet",
    # bin
    "bin": "bin",
    "bin (if any)": "bin",
    "bin if any": "bin",
    "tote": "bin",
    "container": "bin",
    # shelf code
    "shelf code": "shelf_code",
    "shelf_code": "shelf_code",
    "shelf letter": "shelf_code",
    # unit ("metric" kept as backward-compat alias)
    "unit": "unit",
    "metric": "unit",
    # consumable
    "consumable": "consumable",
    "is consumable": "consumable",
    # notes
    "notes": "notes",
    "note": "notes",
    # low stock threshold
    "low stock threshold": "low_stock_threshold",
    "low_stock_threshold": "low_stock_threshold",
    "reorder threshold": "low_stock_threshold",
    "minimum quantity": "low_stock_threshold",
    "min quantity": "low_stock_threshold",
    # unit price
    "unit price": "unit_price",
    "price": "unit_price",
    "cost": "unit_price",
    # condition
    "condition": "condition",
    # sku
    "sku": "sku",
    # bin number / code
    "bin number": "bin_number",
    "bin code": "bin_number",
    "bin_number": "bin_number",
    "bin_number / bin_code": "bin_number",
    "bin number / bin code": "bin_number",
    "bin #": "bin_number",
    # bin requires full checkout
    "bin requires full checkout": "bin_requires_full_checkout",
    "requires full bin checkout": "bin_requires_full_checkout",
    "full bin checkout required": "bin_requires_full_checkout",
    "bin full checkout only": "bin_requires_full_checkout",
}


def normalize_headers(
    raw_headers: list[str],
) -> tuple[dict[str, str], list[str]]:
    """
    Map CSV column headers to canonical keys.

    Returns:
      (mapping, unknown_column_warnings)
      - mapping: canonical_key → original_header (for csv.DictReader lookup)
      - unknown_column_warnings: list of warning strings for unrecognized columns

    Raises ValueError if:
      - Required columns are missing.
      - Multiple CSV columns map to the same canonical field (conflict).
    """
    mapping: dict[str, str] = {}
    conflicts: dict[str, list[str]] = {}
    unknowns: list[str] = []

    for h in raw_headers:
        key = _HEADER_ALIASES.get(h.strip().casefold())
        if key is None:
            unknowns.append(h)
            continue
        if key in mapping:
            conflicts.setdefault(key, [mapping[key]]).append(h)
        else:
            mapping[key] = h

    if conflicts:
        msgs = [f"  '{k}': {v}" for k, v in conflicts.items()]
        raise ValueError(
            "Multiple columns map to the same canonical field:\n"
            + "\n".join(msgs)
            + "\nRename or remove conflicting columns before importing."
        )

    missing = REQUIRED_COLUMNS - set(mapping.keys())
    if missing:
        raise ValueError(
            f"CSV is missing required column(s): {', '.join(sorted(missing))}.\n"
            f"Found columns: {', '.join(raw_headers)}\n"
            f"Expected (case-insensitive): {', '.join(sorted(REQUIRED_COLUMNS))}"
        )

    unknown_warnings = [f"Unrecognized column ignored: '{h}'" for h in unknowns]
    return mapping, unknown_warnings
