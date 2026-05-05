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
    value: bool                 # always a bool for the API (schema requires it)
    is_unknown: bool = False    # True when blank/unrecognized — caller should warn
    raw: str = ""


def parse_consumable(raw: str) -> ConsumableResult:
    """
    Parse the Consumable column into a boolean for the API.

    The backend schema requires is_consumable: bool (no null option).
    When blank, we default to False and set is_unknown=True so the caller
    can append a structured note to the item description and report it.

    Values:
      "Yes" / "Y" / "True" / "1" / "✓"  → True, is_unknown=False
      "No"  / "N" / "False" / "0"        → False, is_unknown=False
      "" / anything else                  → False, is_unknown=True
    """
    s = raw.strip().lower() if raw else ""

    if s in _TRUE_VALUES:
        return ConsumableResult(value=True, is_unknown=False, raw=raw.strip())
    if s in _FALSE_VALUES:
        return ConsumableResult(value=False, is_unknown=False, raw=raw.strip())

    return ConsumableResult(value=False, is_unknown=True, raw=raw.strip())


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

REQUIRED_COLUMNS = {"name", "room", "quantity", "place"}
OPTIONAL_COLUMNS = {"bin", "consumable", "notes", "metric", "amount"}

# Map of normalised (casefold+strip) header → canonical key
_HEADER_ALIASES: dict[str, str] = {
    "name": "name",
    "item": "name",
    "item name": "name",
    "room": "room",
    "quantity": "quantity",
    "qty": "quantity",
    "amount": "amount",
    "bin": "bin",
    "bin (if any)": "bin",
    "place": "place",
    "place (tijori/cabinet top/cabinet bottom)": "place",
    "cabinet": "place",
    "consumable": "consumable",
    "notes": "notes",
    "note": "notes",
    "metric": "metric",
    "unit": "metric",
    "quantity (amount and metric)": "quantity",
    "quantity (amount & metric)": "quantity",
    "quantity amount and metric": "quantity",
    "quantity amount metric": "quantity",
}


def normalize_headers(raw_headers: list[str]) -> dict[str, str]:
    """
    Return a mapping of canonical key → original column header for the
    columns we recognise.  Raises ValueError if required columns are missing.
    """
    mapping: dict[str, str] = {}
    for h in raw_headers:
        key = _HEADER_ALIASES.get(h.strip().casefold())
        if key and key not in mapping:
            mapping[key] = h  # keep original header for csv.DictReader lookup

    # A sheet with a standalone Amount column (no Quantity column) is acceptable —
    # process_rows will use Amount as the quantity source via its own fallback.
    if "quantity" not in mapping and "amount" in mapping:
        mapping["quantity"] = mapping["amount"]

    missing = REQUIRED_COLUMNS - set(mapping.keys())
    if missing:
        raise ValueError(
            f"CSV is missing required column(s): {', '.join(sorted(missing))}.\n"
            f"Found columns: {', '.join(raw_headers)}\n"
            f"Expected (case-insensitive): {', '.join(sorted(REQUIRED_COLUMNS))}"
        )

    return mapping
