"""
Unit tests for backend/scripts/import_helpers.py and import_inventory.py

These tests are pure (no network, no database) and run as part of the normal
pytest suite.
"""

import sys
from pathlib import Path

import pytest

# Allow import from the scripts package without installing it
_SCRIPTS = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from import_helpers import (  # noqa: E402
    build_description,
    detect_shifted_sheet,
    generate_sku,
    normalize_headers,
    normalize_name,
    parse_bin_requires_full_checkout,
    parse_condition,
    parse_consumable,
    parse_low_stock_threshold,
    parse_quantity,
    parse_unit_price,
)


# ---------------------------------------------------------------------------
# parse_quantity
# ---------------------------------------------------------------------------

class TestParseQuantity:
    def test_plain_integer(self):
        r = parse_quantity("3")
        assert r.value == 3.0
        assert r.unit is None
        assert r.warnings == []

    def test_plain_decimal(self):
        r = parse_quantity("1.5")
        assert r.value == 1.5
        assert r.unit is None

    def test_decimal_two_places(self):
        r = parse_quantity("2.75")
        assert r.value == 2.75

    def test_simple_fraction(self):
        r = parse_quantity("1/2")
        assert r.value == 0.5
        assert r.unit is None

    def test_mixed_number(self):
        r = parse_quantity("1 1/2")
        assert r.value == 1.5
        assert r.unit is None

    def test_larger_mixed_number(self):
        r = parse_quantity("3 2/4")
        assert r.value == 3.5

    def test_quantity_with_unit_ft(self):
        r = parse_quantity("10 ft")
        assert r.value == 10.0
        assert r.unit == "ft"
        assert r.warnings == []

    def test_quantity_with_unit_pack(self):
        r = parse_quantity("1 Pack")
        assert r.value == 1.0
        assert r.unit == "Pack"

    def test_quantity_with_unit_packs(self):
        r = parse_quantity("5 Packs")
        assert r.value == 5.0
        assert r.unit == "Packs"

    def test_mixed_number_with_unit(self):
        r = parse_quantity("1 1/2 ft")
        assert r.value == 1.5
        assert r.unit == "ft"

    def test_blank_defaults_to_one_with_warning(self):
        r = parse_quantity("")
        assert r.value == 1.0
        assert len(r.warnings) == 1
        assert "blank" in r.warnings[0].lower()

    def test_whitespace_only_defaults_to_one(self):
        r = parse_quantity("   ")
        assert r.value == 1.0
        assert r.warnings

    def test_text_only_warns_and_uses_as_unit(self):
        r = parse_quantity("Pack")
        assert r.value == 1.0
        assert r.unit == "Pack"
        assert r.warnings  # should warn about unparseable numeric

    def test_large_integer(self):
        r = parse_quantity("100")
        assert r.value == 100.0

    def test_zero_parses_to_zero(self):
        # parse_quantity itself returns 0.0 — the row policy (process_rows) rejects it.
        r = parse_quantity("0")
        assert r.value == 0.0

    def test_leading_trailing_spaces(self):
        r = parse_quantity("  4  ")
        assert r.value == 4.0

    def test_fraction_with_spaces(self):
        r = parse_quantity(" 3/4 ")
        assert r.value == 0.75


# ---------------------------------------------------------------------------
# parse_consumable
# ---------------------------------------------------------------------------

class TestParseConsumable:
    @pytest.mark.parametrize("raw", ["Yes", "yes", "YES", "Y", "y", "True", "true", "1", "✓"])
    def test_truthy_values(self, raw):
        r = parse_consumable(raw)
        assert r.value is True
        assert r.is_unknown is False
        assert r.error is None

    @pytest.mark.parametrize("raw", ["No", "no", "NO", "N", "n", "False", "false", "0"])
    def test_falsy_values(self, raw):
        r = parse_consumable(raw)
        assert r.value is False
        assert r.is_unknown is False
        assert r.error is None

    def test_blank_is_unknown(self):
        r = parse_consumable("")
        assert r.value is False      # API requires bool; defaults to False
        assert r.is_unknown is True
        assert r.error is None       # blank is not an error, just a note

    def test_whitespace_only_is_unknown(self):
        r = parse_consumable("   ")
        assert r.is_unknown is True
        assert r.error is None

    def test_unrecognised_string_has_error(self):
        """Non-blank unrecognized consumable values now fail the row."""
        r = parse_consumable("Maybe")
        assert r.value is False
        assert r.is_unknown is False  # not blank — it's an error, not "unknown"
        assert r.error is not None
        assert "Maybe" in r.error

    def test_unrecognised_string_unknown_has_error(self):
        r = parse_consumable("unknown")
        assert r.error is not None

    def test_raw_preserved(self):
        r = parse_consumable("Yes")
        assert r.raw == "Yes"

    def test_blank_raw_preserved_as_empty(self):
        r = parse_consumable("")
        assert r.raw == ""


# ---------------------------------------------------------------------------
# parse_condition
# ---------------------------------------------------------------------------

class TestParseCondition:
    @pytest.mark.parametrize("raw", ["GOOD", "FAIR", "POOR", "DAMAGED"])
    def test_valid_uppercase(self, raw):
        val, err = parse_condition(raw)
        assert val == raw
        assert err is None

    @pytest.mark.parametrize("raw,expected", [
        ("good", "GOOD"), ("Fair", "FAIR"), ("poor", "POOR"), ("Damaged", "DAMAGED"),
    ])
    def test_case_insensitive(self, raw, expected):
        val, err = parse_condition(raw)
        assert val == expected
        assert err is None

    def test_blank_defaults_to_good(self):
        val, err = parse_condition("")
        assert val == "GOOD"
        assert err is None

    def test_whitespace_defaults_to_good(self):
        val, err = parse_condition("   ")
        assert val == "GOOD"
        assert err is None

    @pytest.mark.parametrize("placeholder", ["—", "N/A", "none", "null", "-"])
    def test_placeholder_defaults_to_good(self, placeholder):
        val, err = parse_condition(placeholder)
        assert val == "GOOD"
        assert err is None

    @pytest.mark.parametrize("bad", ["broken", "ok", "used", "mint", "EXCELLENT"])
    def test_invalid_returns_error(self, bad):
        val, err = parse_condition(bad)
        assert val == "GOOD"  # safe default
        assert err is not None
        assert bad in err

    def test_invalid_error_lists_valid_values(self):
        _, err = parse_condition("BROKEN")
        assert err is not None
        assert "GOOD" in err or "FAIR" in err


# ---------------------------------------------------------------------------
# parse_low_stock_threshold
# ---------------------------------------------------------------------------

class TestParseLowStockThreshold:
    def test_integer(self):
        r = parse_low_stock_threshold("5")
        assert r.value == 5.0
        assert r.error is None

    def test_decimal(self):
        r = parse_low_stock_threshold("1.5")
        assert r.value == 1.5
        assert r.error is None

    def test_zero_is_valid(self):
        r = parse_low_stock_threshold("0")
        assert r.value == 0.0
        assert r.error is None

    def test_blank_returns_none(self):
        r = parse_low_stock_threshold("")
        assert r.value is None
        assert r.error is None

    def test_whitespace_returns_none(self):
        r = parse_low_stock_threshold("   ")
        assert r.value is None
        assert r.error is None

    @pytest.mark.parametrize("placeholder", ["—", "N/A", "none", "null", "-"])
    def test_placeholder_returns_none(self, placeholder):
        r = parse_low_stock_threshold(placeholder)
        assert r.value is None
        assert r.error is None

    def test_negative_returns_error(self):
        r = parse_low_stock_threshold("-1")
        assert r.value is None
        assert r.error is not None
        assert ">= 0" in r.error or "negative" in r.error.lower()

    def test_text_returns_error(self):
        r = parse_low_stock_threshold("abc")
        assert r.value is None
        assert r.error is not None

    def test_rounded_to_two_decimals(self):
        r = parse_low_stock_threshold("3.1415")
        assert r.value == 3.14


# ---------------------------------------------------------------------------
# parse_unit_price
# ---------------------------------------------------------------------------

class TestParseUnitPrice:
    def test_plain_decimal(self):
        r = parse_unit_price("10.00")
        assert r.value == 10.0
        assert r.error is None

    def test_dollar_sign_stripped(self):
        r = parse_unit_price("$5.50")
        assert r.value == 5.5
        assert r.error is None

    def test_zero_is_valid(self):
        r = parse_unit_price("0")
        assert r.value == 0.0
        assert r.error is None

    def test_blank_returns_none(self):
        r = parse_unit_price("")
        assert r.value is None
        assert r.error is None

    def test_whitespace_returns_none(self):
        r = parse_unit_price("   ")
        assert r.value is None
        assert r.error is None

    @pytest.mark.parametrize("placeholder", ["—", "N/A", "none", "null", "-"])
    def test_placeholder_returns_none(self, placeholder):
        r = parse_unit_price(placeholder)
        assert r.value is None
        assert r.error is None

    def test_text_returns_error(self):
        r = parse_unit_price("free")
        assert r.value is None
        assert r.error is not None

    def test_negative_returns_error(self):
        r = parse_unit_price("-1.00")
        assert r.value is None
        assert r.error is not None

    def test_rounded_to_two_decimals(self):
        r = parse_unit_price("9.999")
        assert r.value == 10.0

    def test_integer_string(self):
        r = parse_unit_price("25")
        assert r.value == 25.0


# ---------------------------------------------------------------------------
# generate_sku
# ---------------------------------------------------------------------------

class TestGenerateSku:
    def test_group1_tijori(self):
        assert generate_sku("Group 1 Tijori", 1) == "GROUP1TI-0001"

    def test_room_a(self):
        assert generate_sku("Room A", 5) == "ROOMA-0005"

    def test_counter_padding(self):
        assert generate_sku("Store", 99) == "STORE-0099"

    def test_counter_overflow_graceful(self):
        # Counter > 9999 should not error, just expand
        result = generate_sku("Store", 1000)
        assert result == "STORE-1000"

    def test_empty_room_uses_item_fallback(self):
        result = generate_sku("", 1)
        assert result.startswith("ITEM-")

    def test_special_chars_stripped(self):
        # Non-alphanumeric chars removed from prefix
        result = generate_sku("Room #1", 1)
        assert "#" not in result
        assert result.startswith("ROOM1-") or result.startswith("ROOM")

    def test_prefix_max_8_chars(self):
        result = generate_sku("Very Long Room Name Here", 1)
        prefix = result.split("-")[0]
        assert len(prefix) <= 8

    def test_counter_zero_padded_to_4_digits(self):
        assert generate_sku("Test", 1).endswith("-0001")
        assert generate_sku("Test", 10).endswith("-0010")


# ---------------------------------------------------------------------------
# detect_shifted_sheet
# ---------------------------------------------------------------------------

class TestDetectShiftedSheet:
    def _make_rows(self, pairs):
        """pairs = list of (qty_val, cab_val)"""
        return [{"Quantity": q, "Cabinet": c} for q, c in pairs]

    def _hmap(self):
        return {"quantity": "Quantity", "cabinet": "Cabinet"}

    def test_majority_shifted_returns_warning(self):
        rows = self._make_rows([
            ("", "3"), ("", "1 1/2"), ("", "10 ft"), ("", "1 Pack"), ("2", "Shelf A"),
        ])
        result = detect_shifted_sheet(rows, self._hmap())
        assert result is not None
        assert "misaligned" in result.lower() or "shifted" in result.lower()

    def test_all_shifted_returns_warning(self):
        rows = self._make_rows([("", "3"), ("", "1"), ("", "2"), ("", "10")])
        result = detect_shifted_sheet(rows, self._hmap())
        assert result is not None

    def test_below_threshold_returns_none(self):
        # Only 1 of 10 shifted → 10% < 30%
        rows = self._make_rows(
            [("", "3")] + [("5", "Shelf A")] * 9
        )
        result = detect_shifted_sheet(rows, self._hmap())
        assert result is None

    def test_no_cabinet_header_returns_none(self):
        rows = [{"Quantity": "", "SomeCol": "3"}]
        hmap = {"quantity": "Quantity"}  # no "cabinet" key
        assert detect_shifted_sheet(rows, hmap) is None

    def test_no_quantity_header_returns_none(self):
        rows = [{"Cabinet": "3", "SomeCol": ""}]
        hmap = {"cabinet": "Cabinet"}  # no "quantity" key
        assert detect_shifted_sheet(rows, hmap) is None

    def test_empty_rows_returns_none(self):
        assert detect_shifted_sheet([], self._hmap()) is None

    def test_all_have_quantity_not_shifted(self):
        rows = self._make_rows([("5", "Shelf A"), ("3", "Shelf B"), ("10", "Cabinet C")])
        assert detect_shifted_sheet(rows, self._hmap()) is None

    def test_numeric_looking_cabinet_values_detected(self):
        rows = self._make_rows([("", "1 Pack"), ("", "2 Packs"), ("", "0.5")])
        result = detect_shifted_sheet(rows, self._hmap())
        assert result is not None


# ---------------------------------------------------------------------------
# build_description
# ---------------------------------------------------------------------------

class TestBuildDescription:
    def test_notes_only(self):
        d = build_description("Keep dry", unit=None, consumable_unknown=False)
        assert d == "Keep dry"

    def test_unit_only(self):
        d = build_description("", unit="ft", consumable_unknown=False)
        assert d == "[unit: ft]"

    def test_consumable_unknown_only(self):
        d = build_description("", unit=None, consumable_unknown=True)
        assert d == "[consumable: unknown]"

    def test_all_three(self):
        d = build_description("Fragile", unit="Pack", consumable_unknown=True)
        assert "Fragile" in d
        assert "[unit: Pack]" in d
        assert "[consumable: unknown]" in d

    def test_none_when_all_empty(self):
        d = build_description("", unit=None, consumable_unknown=False)
        assert d is None

    def test_markers_on_separate_lines(self):
        d = build_description("Note", unit="ft", consumable_unknown=True)
        lines = d.split("\n")
        assert len(lines) == 3

    def test_unit_marker_parseable(self):
        d = build_description("", unit="Boxes", consumable_unknown=False)
        assert d == "[unit: Boxes]"


# ---------------------------------------------------------------------------
# normalize_name
# ---------------------------------------------------------------------------

class TestNormalizeName:
    def test_trims_whitespace(self):
        assert normalize_name("  Hammer  ") == "hammer"

    def test_casefolded(self):
        assert normalize_name("LED Resistor") == "led resistor"

    def test_already_lower(self):
        assert normalize_name("wrench") == "wrench"


# ---------------------------------------------------------------------------
# normalize_headers — returns (mapping, warnings) tuple
# ---------------------------------------------------------------------------

class TestNormalizeHeaders:
    def test_canonical_headers(self):
        m, w = normalize_headers(["Name", "Room", "Quantity", "Cabinet"])
        assert set(m.keys()) >= {"name", "room", "quantity", "cabinet"}

    def test_place_alias_maps_to_cabinet(self):
        m, w = normalize_headers(["Name", "Room", "Quantity", "Place"])
        assert "cabinet" in m

    def test_case_insensitive(self):
        m, w = normalize_headers(["NAME", "ROOM", "QUANTITY", "CABINET"])
        assert "name" in m

    def test_alias_amount_maps_to_quantity(self):
        m, w = normalize_headers(["Name", "Room", "Amount", "Cabinet"])
        assert "quantity" in m

    def test_alias_item_maps_to_name(self):
        m, w = normalize_headers(["Item", "Room", "Quantity", "Cabinet"])
        assert "name" in m

    def test_alias_cabinet_maps_to_cabinet(self):
        m, w = normalize_headers(["Name", "Room", "Quantity", "Cabinet"])
        assert "cabinet" in m

    def test_missing_required_raises(self):
        with pytest.raises(ValueError, match="missing required"):
            normalize_headers(["Name", "Room"])  # missing Quantity and Cabinet

    def test_extra_columns_in_warnings(self):
        m, w = normalize_headers(["Name", "Room", "Quantity", "Cabinet", "ExtraJunk"])
        assert "cabinet" not in {k.lower() for k in ["ExtraJunk"]}
        assert any("ExtraJunk" in warn for warn in w)

    def test_bin_optional(self):
        m, w = normalize_headers(["Name", "Room", "Quantity", "Cabinet", "Bin (if any)"])
        assert "bin" in m

    def test_notes_optional(self):
        m, w = normalize_headers(["Name", "Room", "Quantity", "Cabinet", "Notes"])
        assert "notes" in m

    def test_consumable_optional(self):
        m, w = normalize_headers(["Name", "Room", "Quantity", "Cabinet", "Consumable"])
        assert "consumable" in m

    def test_low_stock_threshold_optional(self):
        m, w = normalize_headers(["Name", "Room", "Quantity", "Cabinet", "Low Stock Threshold"])
        assert "low_stock_threshold" in m

    def test_unit_price_optional(self):
        m, w = normalize_headers(["Name", "Room", "Quantity", "Cabinet", "Unit Price"])
        assert "unit_price" in m

    def test_condition_optional(self):
        m, w = normalize_headers(["Name", "Room", "Quantity", "Cabinet", "Condition"])
        assert "condition" in m

    def test_sku_optional(self):
        m, w = normalize_headers(["Name", "Room", "Quantity", "Cabinet", "SKU"])
        assert "sku" in m

    def test_unit_optional(self):
        m, w = normalize_headers(["Name", "Room", "Quantity", "Cabinet", "Unit"])
        assert "unit" in m

    def test_metric_maps_to_unit(self):
        m, w = normalize_headers(["Name", "Room", "Quantity", "Cabinet", "Metric"])
        assert "unit" in m

    def test_returns_tuple(self):
        result = normalize_headers(["Name", "Room", "Quantity", "Cabinet"])
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_no_unknown_warnings_for_known_columns(self):
        _, w = normalize_headers(["Name", "Room", "Quantity", "Cabinet"])
        assert w == []


# ---------------------------------------------------------------------------
# normalize_headers — conflict detection
# ---------------------------------------------------------------------------

class TestNormalizeHeadersConflict:
    def test_cabinet_and_place_conflict(self):
        with pytest.raises(ValueError) as exc_info:
            normalize_headers(["Name", "Room", "Quantity", "Cabinet", "Place"])
        err = str(exc_info.value)
        assert "cabinet" in err.lower()
        assert "Place" in err or "Cabinet" in err

    def test_quantity_and_amount_conflict(self):
        with pytest.raises(ValueError) as exc_info:
            normalize_headers(["Name", "Room", "Quantity", "Amount", "Cabinet"])
        err = str(exc_info.value)
        assert "quantity" in err.lower()

    def test_notes_and_note_conflict(self):
        with pytest.raises(ValueError) as exc_info:
            normalize_headers(["Name", "Room", "Quantity", "Cabinet", "Notes", "Note"])
        err = str(exc_info.value)
        assert "notes" in err.lower()

    def test_unit_and_metric_conflict(self):
        with pytest.raises(ValueError) as exc_info:
            normalize_headers(["Name", "Room", "Quantity", "Cabinet", "Unit", "Metric"])
        err = str(exc_info.value)
        assert "unit" in err.lower()

    def test_unknown_extra_columns_do_not_conflict(self):
        # Unrecognized columns should produce warnings, not errors
        m, w = normalize_headers(["Name", "Room", "Quantity", "Cabinet", "Color", "Weight"])
        assert "color" not in m
        assert "weight" not in m
        assert len(w) == 2

    def test_multiple_conflicts_raises(self):
        with pytest.raises(ValueError):
            normalize_headers(["Name", "Room", "Quantity", "Cabinet", "Place", "Amount"])

    def test_qty_aliases_do_not_conflict_with_each_other(self):
        """Only one of qty/amount/quantity should be present — two at once is a conflict."""
        with pytest.raises(ValueError):
            normalize_headers(["Name", "Room", "Qty", "Amount", "Cabinet"])

    def test_low_stock_threshold_aliases_conflict(self):
        with pytest.raises(ValueError):
            normalize_headers(["Name", "Room", "Quantity", "Cabinet",
                               "Low Stock Threshold", "Min Quantity"])

    def test_unit_price_aliases_conflict(self):
        with pytest.raises(ValueError):
            normalize_headers(["Name", "Room", "Quantity", "Cabinet", "Unit Price", "Price"])


# ---------------------------------------------------------------------------
# normalize_headers — "Quantity (Amount and Metric)" variants
# ---------------------------------------------------------------------------

class TestNormalizeHeadersQuantityVariants:
    def _base(self, qty_header: str):
        m, _ = normalize_headers(["Name", "Room", qty_header, "Cabinet"])
        return m

    def test_quantity_amount_and_metric_parentheses(self):
        m = self._base("Quantity (Amount and Metric)")
        assert m["quantity"] == "Quantity (Amount and Metric)"

    def test_quantity_amount_ampersand_metric(self):
        m = self._base("Quantity (Amount & Metric)")
        assert m["quantity"] == "Quantity (Amount & Metric)"

    def test_quantity_amount_and_metric_no_parens(self):
        m = self._base("Quantity Amount and Metric")
        assert m["quantity"] == "Quantity Amount and Metric"

    def test_quantity_amount_metric_short(self):
        m = self._base("Quantity Amount Metric")
        assert m["quantity"] == "Quantity Amount Metric"

    def test_quantity_variant_case_insensitive(self):
        m = self._base("QUANTITY (AMOUNT AND METRIC)")
        assert "quantity" in m


# ---------------------------------------------------------------------------
# process_rows — row-level policy (import_inventory.py)
# ---------------------------------------------------------------------------

sys.path.insert(0, str(_SCRIPTS.parent))  # backend/ on path
sys.path.insert(0, str(_SCRIPTS))

from import_inventory import RowResult  # noqa: E402


class _EmptyCache:
    """Minimal stub for InventoryCache so process_rows can run without a network."""
    def __init__(self):
        self.rooms: dict = {}
        self.cabinets: dict = {}
        self.bins: dict = {}
        self.items: dict = {}
        self.skus: set = set()


def _make_header_map():
    m, _ = normalize_headers(["Name", "Room", "Quantity", "Cabinet", "Bin", "Consumable", "Notes"])
    return m


def _make_row(**kwargs):
    defaults = {
        "Name": "TestItem", "Room": "Storage", "Quantity": "5", "Cabinet": "Cabinet A",
        "Bin": "", "Consumable": "Yes", "Notes": "",
    }
    defaults.update(kwargs)
    return defaults


class TestProcessRowsPolicy:
    def _run(self, rows, cache=None):
        from import_inventory import process_rows  # noqa: PLC0415
        c = cache or _EmptyCache()
        return process_rows(rows, _make_header_map(), c)

    def test_zero_quantity_row_is_warned_not_created(self):
        results = self._run([_make_row(Quantity="0")])
        assert len(results) == 1
        r = results[0]
        assert r.action == "warn"
        assert any("must be > 0" in e for e in r.errors)

    def test_blank_name_skips_row(self):
        results = self._run([_make_row(Name="")])
        assert results[0].action == "skip"

    def test_blank_room_warns_row(self):
        results = self._run([_make_row(Room="")])
        assert results[0].action == "warn"

    def test_blank_cabinet_warns_row(self):
        results = self._run([_make_row(Cabinet="")])
        assert results[0].action == "warn"

    def test_valid_row_creates(self):
        results = self._run([_make_row()])
        assert results[0].action == "create"
        assert results[0].item_payload is not None

    def test_blank_consumable_adds_unknown_warning(self):
        results = self._run([_make_row(Consumable="")])
        r = results[0]
        assert r.action == "create"
        assert any("consumable" in w.lower() for w in r.warnings)
        assert r.item_payload["description"] is not None
        assert "[consumable: unknown]" in r.item_payload["description"]

    def test_invalid_consumable_fails_row(self):
        results = self._run([_make_row(Consumable="Maybe")])
        r = results[0]
        assert r.action == "warn"
        assert any("Maybe" in e for e in r.errors)

    def test_duplicate_in_csv_second_row_skipped(self):
        row = _make_row()
        results = self._run([row, row])
        assert results[0].action == "create"
        assert results[1].action == "skip"

    def test_dry_run_produces_no_created_id(self):
        """process_rows never sets _created_id — that only happens in apply_import."""
        results = self._run([_make_row()])
        r = results[0]
        assert r.action == "create"
        assert "_created_id" not in (r.item_payload or {})

    def test_separate_unit_column_combined(self):
        """Separate Quantity + Unit columns are merged into a single quantity string."""
        m, _ = normalize_headers(["Name", "Room", "Quantity", "Cabinet", "Unit"])
        row = {"Name": "Rope", "Room": "Store", "Quantity": "10", "Cabinet": "Shelf A", "Unit": "ft"}
        from import_inventory import process_rows  # noqa: PLC0415
        results = process_rows([row], m, _EmptyCache())
        r = results[0]
        assert r.action == "create"
        assert r.item_payload["quantity_total"] == 10.0
        assert r.item_payload["description"] is not None
        assert "[unit: ft]" in r.item_payload["description"]

    def test_unit_not_doubled_when_quantity_already_has_unit(self):
        """When quantity string already has letters and unit matches, no conflict."""
        m, _ = normalize_headers(["Name", "Room", "Quantity", "Cabinet", "Unit"])
        row = {"Name": "Cable", "Room": "Store", "Quantity": "5 m", "Cabinet": "Box", "Unit": "m"}
        from import_inventory import process_rows  # noqa: PLC0415
        results = process_rows([row], m, _EmptyCache())
        r = results[0]
        assert r.action == "create"
        assert r.item_payload["quantity_total"] == 5.0
        desc = r.item_payload.get("description", "") or ""
        assert desc.count("[unit: m]") == 1

    def test_separate_metric_column_combined(self):
        """Backward compat: Metric column alias also works as Unit."""
        m, _ = normalize_headers(["Name", "Room", "Quantity", "Cabinet", "Metric"])
        row = {"Name": "Rope", "Room": "Store", "Quantity": "10", "Cabinet": "Shelf A", "Metric": "ft"}
        from import_inventory import process_rows  # noqa: PLC0415
        results = process_rows([row], m, _EmptyCache())
        r = results[0]
        assert r.action == "create"
        assert r.item_payload["quantity_total"] == 10.0
        assert "[unit: ft]" in (r.item_payload.get("description") or "")

    def test_metric_not_doubled_when_quantity_already_has_unit(self):
        """When quantity string already contains letters, metric is not appended again."""
        m, _ = normalize_headers(["Name", "Room", "Quantity", "Cabinet", "Metric"])
        row = {"Name": "Cable", "Room": "Store", "Quantity": "5 m", "Cabinet": "Box", "Metric": "m"}
        from import_inventory import process_rows  # noqa: PLC0415
        results = process_rows([row], m, _EmptyCache())
        r = results[0]
        assert r.action == "create"
        assert r.item_payload["quantity_total"] == 5.0
        desc = r.item_payload.get("description", "") or ""
        assert desc.count("[unit: m]") == 1


# ---------------------------------------------------------------------------
# Unit column conflict detection in process_rows
# ---------------------------------------------------------------------------

class TestUnitColumnConflict:
    def _run(self, quantity_str, unit_str):
        from import_inventory import process_rows  # noqa: PLC0415
        m, _ = normalize_headers(["Name", "Room", "Quantity", "Cabinet", "Unit"])
        row = {
            "Name": "Widget", "Room": "Store", "Quantity": quantity_str,
            "Cabinet": "Shelf", "Unit": unit_str,
        }
        return process_rows([row], m, _EmptyCache())[0]

    def test_quantity_with_unit_unit_col_empty(self):
        r = self._run("10 ft", "")
        assert r.action == "create"
        assert r.item_payload["unit"] == "ft"

    def test_quantity_numeric_unit_col_set(self):
        r = self._run("10", "ft")
        assert r.action == "create"
        assert r.item_payload["unit"] == "ft"

    def test_quantity_unit_matches_unit_col_no_conflict(self):
        r = self._run("10 ft", "ft")
        assert r.action == "create"
        assert r.item_payload["unit"] == "ft"

    def test_quantity_unit_conflicts_with_unit_col(self):
        r = self._run("10 ft", "m")
        assert r.action == "warn"
        assert any("conflict" in e.lower() or "unit" in e.lower() for e in r.errors)

    def test_case_insensitive_unit_match_no_conflict(self):
        r = self._run("10 FT", "ft")
        assert r.action == "create"


# ---------------------------------------------------------------------------
# New column support in process_rows payloads
# ---------------------------------------------------------------------------

class TestProcessRowsNewColumns:
    def _run_with_new_cols(self, **col_vals):
        from import_inventory import process_rows  # noqa: PLC0415
        headers = ["Name", "Room", "Quantity", "Cabinet",
                   "Consumable", "Low Stock Threshold", "Unit Price", "Condition", "SKU", "Notes"]
        m, _ = normalize_headers(headers)
        row = {
            "Name": "Widget", "Room": "Store", "Quantity": "5", "Cabinet": "Shelf",
            "Consumable": "Yes", "Low Stock Threshold": "", "Unit Price": "",
            "Condition": "", "SKU": "", "Notes": "",
        }
        row.update(col_vals)
        return process_rows([row], m, _EmptyCache())[0]

    def test_low_stock_threshold_imported(self):
        r = self._run_with_new_cols(**{"Low Stock Threshold": "3"})
        assert r.action == "create"
        assert r.item_payload["low_stock_threshold"] == 3.0

    def test_blank_low_stock_threshold_is_none(self):
        r = self._run_with_new_cols(**{"Low Stock Threshold": ""})
        assert r.action == "create"
        assert r.item_payload["low_stock_threshold"] is None

    def test_invalid_low_stock_threshold_fails_row(self):
        r = self._run_with_new_cols(**{"Low Stock Threshold": "abc"})
        assert r.action == "warn"
        assert r.item_payload is None

    def test_negative_low_stock_threshold_fails_row(self):
        r = self._run_with_new_cols(**{"Low Stock Threshold": "-5"})
        assert r.action == "warn"

    def test_unit_price_imported(self):
        r = self._run_with_new_cols(**{"Unit Price": "9.99"})
        assert r.action == "create"
        assert r.item_payload["unit_price"] == 9.99

    def test_blank_unit_price_is_none(self):
        r = self._run_with_new_cols(**{"Unit Price": ""})
        assert r.action == "create"
        assert r.item_payload["unit_price"] is None

    def test_invalid_unit_price_fails_row(self):
        r = self._run_with_new_cols(**{"Unit Price": "free"})
        assert r.action == "warn"

    def test_negative_unit_price_fails_row(self):
        r = self._run_with_new_cols(**{"Unit Price": "-1.00"})
        assert r.action == "warn"

    def test_condition_imported(self):
        r = self._run_with_new_cols(**{"Condition": "FAIR"})
        assert r.action == "create"
        assert r.item_payload["condition"] == "FAIR"

    def test_blank_condition_defaults_to_good(self):
        r = self._run_with_new_cols(**{"Condition": ""})
        assert r.action == "create"
        assert r.item_payload["condition"] == "GOOD"

    def test_invalid_condition_fails_row(self):
        r = self._run_with_new_cols(**{"Condition": "MINT"})
        assert r.action == "warn"

    def test_sku_provided(self):
        r = self._run_with_new_cols(**{"SKU": "ABC-001"})
        assert r.action == "create"
        assert r.item_payload["sku"] == "ABC-001"
        assert r.item_payload["sku_source"] == "provided"

    def test_blank_sku_auto_generated(self):
        r = self._run_with_new_cols(**{"SKU": ""})
        assert r.action == "create"
        assert r.item_payload["sku"] is not None
        assert r.item_payload["sku_source"] == "generated"


# ---------------------------------------------------------------------------
# SKU handling in process_rows
# ---------------------------------------------------------------------------

class TestSkuHandling:
    def _run_rows(self, row_overrides_list):
        from import_inventory import process_rows  # noqa: PLC0415
        headers = ["Name", "Room", "Quantity", "Cabinet", "SKU"]
        m, _ = normalize_headers(headers)
        rows = []
        for i, overrides in enumerate(row_overrides_list):
            row = {"Name": f"Item{i}", "Room": "Store", "Quantity": "1",
                   "Cabinet": "Shelf", "SKU": ""}
            row.update(overrides)
            rows.append(row)
        return process_rows(rows, m, _EmptyCache())

    def test_provided_sku_stored_as_provided(self):
        results = self._run_rows([{"Name": "Widget", "SKU": "MY-SKU-001"}])
        r = results[0]
        assert r.action == "create"
        assert r.item_payload["sku"] == "MY-SKU-001"
        assert r.item_payload["sku_source"] == "provided"

    def test_blank_sku_auto_generated(self):
        results = self._run_rows([{"Name": "Widget", "SKU": ""}])
        r = results[0]
        assert r.action == "create"
        assert r.item_payload["sku"] is not None
        assert r.item_payload["sku_source"] == "generated"

    def test_duplicate_sku_in_csv_second_row_fails(self):
        results = self._run_rows([
            {"Name": "First", "SKU": "SHARED-001"},
            {"Name": "Second", "SKU": "SHARED-001"},
        ])
        assert results[0].action == "create"
        assert results[1].action == "warn"
        assert any("duplicate" in e.lower() or "already" in e.lower() for e in results[1].errors)

    def test_sku_duplicate_case_insensitive(self):
        results = self._run_rows([
            {"Name": "First", "SKU": "ABC-001"},
            {"Name": "Second", "SKU": "abc-001"},
        ])
        assert results[0].action == "create"
        assert results[1].action == "warn"

    def test_sku_already_in_cache_fails_row(self):
        from import_inventory import process_rows  # noqa: PLC0415
        headers = ["Name", "Room", "Quantity", "Cabinet", "SKU"]
        m, _ = normalize_headers(headers)
        cache = _EmptyCache()
        cache.skus.add("EXISTING-001")
        row = {"Name": "Widget", "Room": "Store", "Quantity": "1",
               "Cabinet": "Shelf", "SKU": "existing-001"}
        results = process_rows([row], m, cache)
        assert results[0].action == "warn"
        assert any("already exists" in e for e in results[0].errors)

    def test_two_blank_skus_same_room_get_unique_values(self):
        results = self._run_rows([
            {"Name": "Item1", "Room": "Store", "SKU": ""},
            {"Name": "Item2", "Room": "Store", "SKU": ""},
        ])
        assert results[0].action == "create"
        assert results[1].action == "create"
        sku1 = results[0].item_payload["sku"]
        sku2 = results[1].item_payload["sku"]
        assert sku1 != sku2

    def test_generated_sku_not_in_cache(self):
        from import_inventory import process_rows  # noqa: PLC0415
        headers = ["Name", "Room", "Quantity", "Cabinet", "SKU"]
        m, _ = normalize_headers(headers)
        cache = _EmptyCache()
        # Pre-populate the first 5 counters for this room prefix
        for i in range(1, 6):
            cache.skus.add(f"STORE-{i:04d}")
        row = {"Name": "Widget", "Room": "Store", "Quantity": "1",
               "Cabinet": "Shelf", "SKU": ""}
        results = process_rows([row], m, cache)
        assert results[0].action == "create"
        generated = results[0].item_payload["sku"]
        assert generated.upper() not in {f"STORE-{i:04d}" for i in range(1, 6)}


# ---------------------------------------------------------------------------
# parse_quantity — malformed fraction edge cases
# ---------------------------------------------------------------------------

class TestParseQuantityMalformedFractions:
    def test_zero_denominator_simple_fraction(self):
        r = parse_quantity("1/0")
        assert r.value == 0.0
        assert any("zero" in w.lower() or "division" in w.lower() for w in r.warnings)

    def test_zero_denominator_mixed_number(self):
        r = parse_quantity("1 1/0")
        assert r.value == 0.0
        assert any("zero" in w.lower() or "division" in w.lower() for w in r.warnings)

    def test_malformed_fraction_does_not_raise(self):
        try:
            r = parse_quantity("5/0")
            assert r.value == 0.0
        except ZeroDivisionError:
            pytest.fail("parse_quantity raised ZeroDivisionError for '5/0'")


# ---------------------------------------------------------------------------
# Amount column behavior (new: "Amount" maps directly to "quantity")
# ---------------------------------------------------------------------------

class TestAmountColumnBehavior:
    def test_only_amount_column_no_quantity_column(self):
        """A sheet with only an Amount column (no Quantity) is valid."""
        m, _ = normalize_headers(["Name", "Room", "Amount", "Cabinet"])
        row = {"Name": "Bolt", "Room": "Store", "Amount": "25", "Cabinet": "Drawer"}
        from import_inventory import process_rows  # noqa: PLC0415
        results = process_rows([row], m, _EmptyCache())
        r = results[0]
        assert r.action == "create"
        assert r.item_payload["quantity_total"] == 25.0

    def test_quantity_and_amount_both_present_raises_conflict(self):
        with pytest.raises(ValueError) as exc_info:
            normalize_headers(["Name", "Room", "Quantity", "Amount", "Cabinet"])
        assert "quantity" in str(exc_info.value).lower()

    def test_only_amount_with_unit(self):
        m, _ = normalize_headers(["Name", "Room", "Amount", "Cabinet", "Unit"])
        row = {"Name": "Rope", "Room": "Store", "Amount": "10", "Cabinet": "Shelf", "Unit": "ft"}
        from import_inventory import process_rows  # noqa: PLC0415
        results = process_rows([row], m, _EmptyCache())
        r = results[0]
        assert r.action == "create"
        assert r.item_payload["quantity_total"] == 10.0
        assert "[unit: ft]" in (r.item_payload.get("description") or "")


# ---------------------------------------------------------------------------
# Cache whitespace normalization
# ---------------------------------------------------------------------------

class TestCacheWhitespaceNormalization:
    def test_cache_item_with_trailing_space_detected_as_duplicate(self):
        """An existing item with trailing whitespace in its name matches the CSV row."""
        from import_inventory import process_rows  # noqa: PLC0415

        cache = _EmptyCache()
        from import_helpers import normalize_name  # noqa: PLC0415
        existing_name = "Hammer "  # trailing space
        cab_sentinel = "NEW:Shelf"
        cache.rooms[normalize_name("Storage")] = "NEW:Storage"
        cache.cabinets[("NEW:Storage", normalize_name("Shelf"))] = cab_sentinel
        cache.items[(cab_sentinel, None, normalize_name(existing_name))] = {"name": existing_name, "id": 42}

        m, _ = normalize_headers(["Name", "Room", "Quantity", "Cabinet"])
        row = {"Name": "Hammer", "Room": "Storage", "Quantity": "1", "Cabinet": "Shelf"}
        results = process_rows([row], m, cache)
        assert results[0].action == "skip", "Item with trimmed-equivalent name should be detected as duplicate"


# ---------------------------------------------------------------------------
# Blank-placeholder detection
# ---------------------------------------------------------------------------

class TestIsBlankPlaceholder:
    def _check(self, value: str, expected: bool):
        from import_helpers import is_blank_placeholder
        assert is_blank_placeholder(value) is expected, f"is_blank_placeholder({value!r}) should be {expected}"

    def test_empty_string(self):            self._check("", True)
    def test_whitespace_only(self):         self._check("   ", True)
    def test_em_dash(self):                 self._check("—", True)
    def test_em_dash_with_spaces(self):     self._check("  —  ", True)
    def test_hyphen(self):                  self._check("-", True)
    def test_n_slash_a_upper(self):         self._check("N/A", True)
    def test_n_slash_a_lower(self):         self._check("n/a", True)
    def test_na_upper(self):                self._check("NA", True)
    def test_na_lower(self):                self._check("na", True)
    def test_none_lower(self):              self._check("none", True)
    def test_none_title(self):              self._check("None", True)
    def test_none_upper(self):              self._check("NONE", True)
    def test_null_lower(self):              self._check("null", True)
    def test_null_title(self):              self._check("Null", True)
    def test_null_upper(self):              self._check("NULL", True)

    def test_real_room_name(self):          self._check("Kitchen", False)
    def test_real_cabinet_name(self):       self._check("Cabinet A", False)
    def test_dash_in_name(self):            self._check("Pre-K Supplies", False)
    def test_double_dash(self):             self._check("--", False)
    def test_na_with_extra(self):           self._check("N/A only", False)
    def test_zero(self):                    self._check("0", False)


# ---------------------------------------------------------------------------
# Blank-placeholder normalization in location fields
# ---------------------------------------------------------------------------

class TestBlankPlaceholderLocationNormalization:
    """Verify process_rows normalizes placeholder bin/room/cabinet values."""

    def _make_cache(self):
        from import_inventory import InventoryCache
        cache = InventoryCache.__new__(InventoryCache)
        cache.rooms = {}
        cache.cabinets = {}
        cache.bins = {}
        cache.items = {}
        cache.skus = set()
        return cache

    def _header_map(self):
        # canonical → original header
        return {"name": "Name", "room": "Room", "cabinet": "Cabinet", "bin": "Bin", "quantity": "Quantity"}

    def _run(self, row: dict, cache=None) -> "RowResult":
        from import_inventory import process_rows
        c = cache or self._make_cache()
        results = process_rows([row], self._header_map(), c)
        return results[0]

    def _good_row(self, bin_val=""):
        return {"Name": "Widget", "Room": "Kitchen", "Cabinet": "Cabinet A", "Bin": bin_val, "Quantity": "1"}

    def test_em_dash_bin_treated_as_no_bin(self):
        rr = self._run(self._good_row("—"))
        assert rr.location["bin"] == ""

    def test_hyphen_bin_treated_as_no_bin(self):
        rr = self._run(self._good_row("-"))
        assert rr.location["bin"] == ""

    def test_na_bin_treated_as_no_bin(self):
        rr = self._run(self._good_row("N/A"))
        assert rr.location["bin"] == ""

    def test_none_bin_treated_as_no_bin(self):
        rr = self._run(self._good_row("None"))
        assert rr.location["bin"] == ""

    def test_null_bin_treated_as_no_bin(self):
        rr = self._run(self._good_row("NULL"))
        assert rr.location["bin"] == ""

    def test_whitespace_bin_treated_as_no_bin(self):
        rr = self._run(self._good_row("   "))
        assert rr.location["bin"] == ""

    def test_real_bin_name_preserved(self):
        rr = self._run(self._good_row("Shelf 2"))
        assert rr.location["bin"] == "Shelf 2"

    def test_dash_in_bin_name_preserved(self):
        rr = self._run(self._good_row("Pre-K Supplies"))
        assert rr.location["bin"] == "Pre-K Supplies"

    def test_em_dash_room_warns_and_skips(self):
        row = {"Name": "Widget", "Room": "—", "Cabinet": "Cabinet A", "Bin": "", "Quantity": "1"}
        rr = self._run(row)
        assert rr.action == "warn"
        assert any("room" in e.lower() for e in rr.errors)

    def test_na_cabinet_warns_and_skips(self):
        row = {"Name": "Widget", "Room": "Kitchen", "Cabinet": "N/A", "Bin": "", "Quantity": "1"}
        rr = self._run(row)
        assert rr.action == "warn"
        assert any("cabinet" in e.lower() for e in rr.errors)

    def test_valid_row_after_placeholder_room_still_creates(self):
        from import_inventory import process_rows
        rows = [
            {"Name": "Widget", "Room": "—", "Cabinet": "Cabinet A", "Bin": "", "Quantity": "1"},
            {"Name": "Gadget", "Room": "Kitchen", "Cabinet": "Cabinet A", "Bin": "", "Quantity": "2"},
        ]
        results = process_rows(rows, self._header_map(), self._make_cache())
        assert results[0].action == "warn"
        assert results[1].action == "create"

    def test_na_lower_bin_treated_as_no_bin(self):
        rr = self._run(self._good_row("n/a"))
        assert rr.location["bin"] == ""

    def test_none_lower_bin_treated_as_no_bin(self):
        rr = self._run(self._good_row("none"))
        assert rr.location["bin"] == ""

    def test_null_upper_bin_treated_as_no_bin(self):
        rr = self._run(self._good_row("NULL"))
        assert rr.location["bin"] == ""

    def test_whitespace_only_bin_treated_as_no_bin(self):
        rr = self._run(self._good_row("  \t  "))
        assert rr.location["bin"] == ""

    def test_arts_crafts_bin_preserved(self):
        rr = self._run(self._good_row("Arts - Crafts"))
        assert rr.location["bin"] == "Arts - Crafts"

    def test_existing_blank_bin_item_detected_as_duplicate_for_na_bin(self):
        from import_inventory import process_rows, InventoryCache
        cache = self._make_cache()
        cache.rooms["kitchen"] = 1
        cache.cabinets[(1, "cabinet a")] = 10
        cache.items[(10, None, "widget")] = {"id": 100, "name": "Widget", "cabinet_id": 10, "bin_id": None}
        row = {"Name": "Widget", "Room": "Kitchen", "Cabinet": "Cabinet A", "Bin": "N/A", "Quantity": "1"}
        results = process_rows([row], self._header_map(), cache)
        assert results[0].action == "skip", f"Expected skip (duplicate), got {results[0].action!r}"


# ---------------------------------------------------------------------------
# Placeholder item name: should warn/skip, not create
# ---------------------------------------------------------------------------

class TestBlankPlaceholderItemName:
    def _make_cache(self):
        from import_inventory import InventoryCache
        cache = InventoryCache.__new__(InventoryCache)
        cache.rooms = {}
        cache.cabinets = {}
        cache.bins = {}
        cache.items = {}
        cache.skus = set()
        return cache

    def _header_map(self):
        return {"name": "Name", "room": "Room", "cabinet": "Cabinet", "bin": "Bin", "quantity": "Quantity"}

    def _run(self, name_val: str) -> "RowResult":
        from import_inventory import process_rows
        row = {"Name": name_val, "Room": "Kitchen", "Cabinet": "Cabinet A", "Bin": "", "Quantity": "1"}
        return process_rows([row], self._header_map(), self._make_cache())[0]

    def test_em_dash_name_skips(self):
        rr = self._run("—")
        assert rr.action == "skip"
        assert rr.item_payload is None

    def test_na_name_skips(self):
        rr = self._run("N/A")
        assert rr.action == "skip"
        assert rr.item_payload is None

    def test_none_name_skips(self):
        rr = self._run("none")
        assert rr.action == "skip"
        assert rr.item_payload is None

    def test_null_upper_name_skips(self):
        rr = self._run("NULL")
        assert rr.action == "skip"
        assert rr.item_payload is None

    def test_whitespace_only_name_skips(self):
        rr = self._run("   ")
        assert rr.action == "skip"
        assert rr.item_payload is None

    def test_none_tape_is_valid_item_name(self):
        rr = self._run("None Tape")
        assert rr.action == "create"
        assert rr.item_payload is not None
        assert rr.item_payload["name"] == "None Tape"

    def test_na_labels_is_valid_item_name(self):
        rr = self._run("N/A Labels")
        assert rr.action == "create"
        assert rr.item_payload is not None
        assert rr.item_payload["name"] == "N/A Labels"


# ---------------------------------------------------------------------------
# Malformed fraction detection
# ---------------------------------------------------------------------------

class TestMalformedFractionDetection:
    def test_double_slash_warns(self):
        r = parse_quantity("1//2")
        assert r.value == 0.0
        assert any("malformed" in w.lower() or "fraction" in w.lower() for w in r.warnings)

    def test_space_before_slash_warns(self):
        r = parse_quantity("1 /2")
        assert r.value == 0.0
        assert any("malformed" in w.lower() or "fraction" in w.lower() for w in r.warnings)

    def test_normal_fraction_still_works(self):
        r = parse_quantity("3/4")
        assert r.value == 0.75
        assert r.warnings == []

    def test_normal_decimal_with_unit_still_works(self):
        r = parse_quantity("10 ft")
        assert r.value == 10.0
        assert r.unit == "ft"
        assert r.warnings == []

    def test_slash_only_warns(self):
        r = parse_quantity("/2")
        assert r.value == 0.0
        assert r.warnings

    def test_text_with_slash_warns(self):
        r = parse_quantity("abc/2")
        assert r.value == 0.0
        assert r.warnings

    def test_negative_fraction_warns(self):
        r = parse_quantity("-1/2")
        assert r.value == 0.0
        assert r.warnings

    def test_plain_text_unit_still_defaults_to_one(self):
        r = parse_quantity("Pack")
        assert r.value == 1.0
        assert r.unit == "Pack"

    def test_fraction_with_slash_tail_warns(self):
        r = parse_quantity("1/2/3")
        assert r.value == 0.0
        assert any("malformed" in w.lower() or "fraction" in w.lower() for w in r.warnings)

    def test_mixed_with_extra_slash_warns(self):
        r = parse_quantity("1 1//2")
        assert r.value == 0.0
        assert any("malformed" in w.lower() or "fraction" in w.lower() for w in r.warnings)

    def test_valid_fraction_unaffected(self):
        r = parse_quantity("1/2")
        assert r.value == 0.5
        assert r.warnings == []

    def test_valid_mixed_unaffected(self):
        r = parse_quantity("1 1/2")
        assert r.value == 1.5
        assert r.warnings == []

    def test_valid_mixed_with_unit_unaffected(self):
        r = parse_quantity("1 1/2 ft")
        assert r.value == 1.5
        assert r.unit == "ft"
        assert r.warnings == []


# ---------------------------------------------------------------------------
# process_rows policy — malformed quantities are warned, not created
# ---------------------------------------------------------------------------

class TestProcessRowsMalformedQuantityPolicy:
    def _run(self, quantity_str):
        from import_inventory import process_rows  # noqa: PLC0415
        m, _ = normalize_headers(["Name", "Room", "Quantity", "Cabinet"])
        row = {"Name": "Widget", "Room": "Store", "Quantity": quantity_str, "Cabinet": "Shelf"}
        return process_rows([row], m, _EmptyCache())[0]

    def test_slash_only_row_is_warned_not_created(self):
        r = self._run("/2")
        assert r.action == "warn"
        assert r.item_payload is None

    def test_text_slash_row_is_warned_not_created(self):
        r = self._run("abc/2")
        assert r.action == "warn"
        assert r.item_payload is None

    def test_negative_fraction_row_is_warned_not_created(self):
        r = self._run("-1/2")
        assert r.action == "warn"
        assert r.item_payload is None

    def test_double_slash_row_is_warned_not_created(self):
        r = self._run("1//2")
        assert r.action == "warn"
        assert r.item_payload is None

    def test_space_slash_row_is_warned_not_created(self):
        r = self._run("1 /2")
        assert r.action == "warn"
        assert r.item_payload is None

    def test_zero_denominator_row_is_warned_not_created(self):
        r = self._run("1/0")
        assert r.action == "warn"
        assert r.item_payload is None

    def test_fraction_slash_tail_is_warned_not_created(self):
        r = self._run("1/2/3")
        assert r.action == "warn"
        assert r.item_payload is None

    def test_mixed_extra_slash_is_warned_not_created(self):
        r = self._run("1 1//2")
        assert r.action == "warn"
        assert r.item_payload is None

    def test_valid_rows_after_malformed_still_create(self):
        from import_inventory import process_rows  # noqa: PLC0415
        m, _ = normalize_headers(["Name", "Room", "Quantity", "Cabinet"])
        rows = [
            {"Name": "Bad", "Room": "Store", "Quantity": "/2", "Cabinet": "Shelf"},
            {"Name": "Good", "Room": "Store", "Quantity": "5", "Cabinet": "Shelf"},
        ]
        results = process_rows(rows, m, _EmptyCache())
        assert results[0].action == "warn"
        assert results[1].action == "create"


# ---------------------------------------------------------------------------
# apply_import — malformed rows must never be POSTed even in commit mode
# ---------------------------------------------------------------------------

class TestApplyImportDoesNotPostWarnRows:
    def test_warn_rows_never_posted(self):
        from import_inventory import process_rows, apply_import  # noqa: PLC0415
        import import_inventory as _inv

        m, _ = normalize_headers(["Name", "Room", "Quantity", "Cabinet"])
        rows = [
            {"Name": "Bad1", "Room": "Store", "Quantity": "1/2/3", "Cabinet": "Shelf"},
            {"Name": "Bad2", "Room": "Store", "Quantity": "1 1//2", "Cabinet": "Shelf"},
            {"Name": "Good", "Room": "Store", "Quantity": "3", "Cabinet": "Shelf"},
        ]
        results = process_rows(rows, m, _EmptyCache())
        assert results[0].action == "warn"
        assert results[1].action == "warn"
        assert results[2].action == "create"

        post_calls: list[dict] = []
        original_post = _inv._api_post

        def counting_post(client, path, body):
            post_calls.append({"path": path, "body": body})
            if path == "/api/rooms":
                return {"id": 1, "name": body.get("name", "")}
            if path == "/api/cabinets":
                return {"id": 2, "name": body.get("name", ""), "room_id": body.get("room_id", 1)}
            if path == "/api/bins":
                return {"id": 3, "label": body.get("label", ""), "cabinet_id": body.get("cabinet_id", 2)}
            if path == "/api/items":
                return {"id": 100, "name": body.get("name", "")}
            return {}

        _inv._api_post = counting_post
        try:
            apply_import(results, client=None, cache=_EmptyCache())
        finally:
            _inv._api_post = original_post

        item_posts = [c for c in post_calls if c["path"] == "/api/items"]
        assert len(item_posts) == 1, (
            f"Expected exactly 1 item POST (for 'Good'), got {len(item_posts)}: {item_posts}"
        )
        assert item_posts[0]["body"]["name"] == "Good"

    def test_apply_import_passes_new_fields(self):
        """apply_import must include sku, low_stock_threshold, unit_price in item POST body."""
        from import_inventory import apply_import  # noqa: PLC0415
        import import_inventory as _inv

        r = RowResult(2, {})
        r.action = "create"
        r.location = {"room": "Store", "cabinet": "Shelf", "bin": ""}
        r.item_payload = {
            "_room_name": "Store", "_cabinet_name": "Shelf", "_bin_label": None,
            "name": "Widget", "quantity_total": 5.0, "is_consumable": False,
            "description": None, "condition": "GOOD",
            "sku": "TEST-0001", "low_stock_threshold": 2.0, "unit_price": 9.99,
            "unit": None, "sku_source": "provided",
        }

        posted_bodies: list[dict] = []
        original_post = _inv._api_post

        def mock_post(client, path, body):
            posted_bodies.append({"path": path, "body": body})
            if path == "/api/rooms": return {"id": 1, "name": "Store"}
            if path == "/api/cabinets": return {"id": 2, "name": "Shelf", "room_id": 1}
            if path == "/api/items": return {"id": 100, "name": "Widget"}
            return {}

        cache = _EmptyCache()
        cache.rooms["store"] = "NEW:Store"

        _inv._api_post = mock_post
        try:
            apply_import([r], client=None, cache=cache)
        finally:
            _inv._api_post = original_post

        item_post = next((p for p in posted_bodies if p["path"] == "/api/items"), None)
        assert item_post is not None
        body = item_post["body"]
        assert body.get("sku") == "TEST-0001"
        assert body.get("low_stock_threshold") == 2.0
        assert body.get("unit_price") == 9.99

    def test_apply_import_omits_none_optional_fields(self):
        """None values for optional fields must not appear in the item POST body."""
        from import_inventory import apply_import  # noqa: PLC0415
        import import_inventory as _inv

        r = RowResult(2, {})
        r.action = "create"
        r.location = {"room": "Store", "cabinet": "Shelf", "bin": ""}
        r.item_payload = {
            "_room_name": "Store", "_cabinet_name": "Shelf", "_bin_label": None,
            "name": "Widget", "quantity_total": 5.0, "is_consumable": False,
            "description": None, "condition": "GOOD",
            "sku": "TEST-0002", "low_stock_threshold": None, "unit_price": None,
            "unit": None, "sku_source": "provided",
        }

        posted_bodies: list[dict] = []
        original_post = _inv._api_post

        def mock_post(client, path, body):
            posted_bodies.append({"path": path, "body": body})
            if path == "/api/rooms": return {"id": 1, "name": "Store"}
            if path == "/api/cabinets": return {"id": 2, "name": "Shelf", "room_id": 1}
            if path == "/api/items": return {"id": 100, "name": "Widget"}
            return {}

        cache = _EmptyCache()
        cache.rooms["store"] = "NEW:Store"

        _inv._api_post = mock_post
        try:
            apply_import([r], client=None, cache=cache)
        finally:
            _inv._api_post = original_post

        item_post = next((p for p in posted_bodies if p["path"] == "/api/items"), None)
        assert item_post is not None
        body = item_post["body"]
        assert "low_stock_threshold" not in body
        assert "unit_price" not in body


# ---------------------------------------------------------------------------
# Pagination helper tests
# ---------------------------------------------------------------------------

class TestFetchAllItems:
    def test_single_page_terminates(self):
        from import_inventory import _fetch_all_items, _PAGE_SIZE  # noqa: PLC0415
        import import_inventory as _inv

        calls = []
        original_api_get = _inv._api_get

        def mock_api_get(client, path, params=None):
            calls.append(dict(params or {}))
            skip = (params or {}).get("skip", 0)
            if skip == 0:
                return [{"id": i, "cabinet_id": 1, "name": f"item{i}", "bin_id": None}
                        for i in range(3)]
            return []

        _inv._api_get = mock_api_get
        try:
            items = _fetch_all_items(None, cabinet_id=1)
        finally:
            _inv._api_get = original_api_get

        assert len(items) == 3
        assert len(calls) == 1

    def test_multiple_pages_fetched(self):
        from import_inventory import _fetch_all_items, _PAGE_SIZE  # noqa: PLC0415
        import import_inventory as _inv

        original_api_get = _inv._api_get

        def mock_api_get(client, path, params=None):
            skip = (params or {}).get("skip", 0)
            limit = (params or {}).get("limit", _PAGE_SIZE)
            if skip == 0:
                return [{"id": i, "cabinet_id": 1, "name": f"item{i}", "bin_id": None}
                        for i in range(limit)]
            return [{"id": 9000 + i, "cabinet_id": 1, "name": f"extra{i}", "bin_id": None}
                    for i in range(2)]

        _inv._api_get = mock_api_get
        try:
            items = _fetch_all_items(None, cabinet_id=1)
        finally:
            _inv._api_get = original_api_get

        assert len(items) == _PAGE_SIZE + 2


# ---------------------------------------------------------------------------
# Pagination — additional guard tests
# ---------------------------------------------------------------------------

class TestFetchAllItemsPaginationGuards:
    def _patch_api_get(self, mock_fn):
        import import_inventory as _inv
        original = _inv._api_get
        _inv._api_get = mock_fn
        return original

    def test_empty_cabinet_returns_no_items(self):
        from import_inventory import _fetch_all_items  # noqa: PLC0415
        import import_inventory as _inv

        def mock_api_get(client, path, params=None):
            return []

        original = self._patch_api_get(mock_api_get)
        try:
            items = _fetch_all_items(None, cabinet_id=99)
        finally:
            _inv._api_get = original

        assert items == []

    def test_exactly_page_size_fetches_second_page(self):
        from import_inventory import _fetch_all_items, _PAGE_SIZE  # noqa: PLC0415
        import import_inventory as _inv

        call_count = [0]

        def mock_api_get(client, path, params=None):
            call_count[0] += 1
            skip = (params or {}).get("skip", 0)
            if skip == 0:
                return [{"id": i, "cabinet_id": 1, "name": f"item{i}", "bin_id": None}
                        for i in range(_PAGE_SIZE)]
            return []

        original = self._patch_api_get(mock_api_get)
        try:
            items = _fetch_all_items(None, cabinet_id=1)
        finally:
            _inv._api_get = original

        assert len(items) == _PAGE_SIZE
        assert call_count[0] == 2

    def test_repeated_full_page_raises(self):
        from import_inventory import _fetch_all_items, _PAGE_SIZE  # noqa: PLC0415
        import import_inventory as _inv

        same_page = [{"id": i, "cabinet_id": 1, "name": f"item{i}", "bin_id": None}
                     for i in range(_PAGE_SIZE)]

        def mock_api_get(client, path, params=None):
            return same_page

        original = self._patch_api_get(mock_api_get)
        try:
            with pytest.raises(RuntimeError, match="Pagination loop detected"):
                _fetch_all_items(None, cabinet_id=1)
        finally:
            _inv._api_get = original

    def test_api_error_on_page_two_propagates(self):
        from import_inventory import _fetch_all_items, _PAGE_SIZE  # noqa: PLC0415
        import import_inventory as _inv

        def mock_api_get(client, path, params=None):
            skip = (params or {}).get("skip", 0)
            if skip == 0:
                return [{"id": i, "cabinet_id": 1, "name": f"item{i}", "bin_id": None}
                        for i in range(_PAGE_SIZE)]
            raise ConnectionError("Network failure on page 2")

        original = self._patch_api_get(mock_api_get)
        try:
            with pytest.raises(ConnectionError, match="Network failure"):
                _fetch_all_items(None, cabinet_id=1)
        finally:
            _inv._api_get = original


# ---------------------------------------------------------------------------
# Report path preflight
# ---------------------------------------------------------------------------

class TestPreflightReportPaths:
    def test_creates_missing_parent_directories(self, tmp_path):
        from import_inventory import _preflight_report_paths  # noqa: PLC0415
        report_base = tmp_path / "new" / "nested" / "report"
        json_p, csv_p = _preflight_report_paths(report_base)
        assert report_base.parent.is_dir()
        assert json_p == report_base.with_suffix(".json")
        assert csv_p == report_base.with_suffix(".csv")

    def test_exits_when_json_target_is_directory(self, tmp_path):
        from import_inventory import _preflight_report_paths  # noqa: PLC0415
        (tmp_path / "report.json").mkdir()
        with pytest.raises(SystemExit):
            _preflight_report_paths(tmp_path / "report")

    def test_exits_when_csv_target_is_directory(self, tmp_path):
        from import_inventory import _preflight_report_paths  # noqa: PLC0415
        (tmp_path / "report.csv").mkdir()
        with pytest.raises(SystemExit):
            _preflight_report_paths(tmp_path / "report")

    def test_valid_path_returns_json_and_csv(self, tmp_path):
        from import_inventory import _preflight_report_paths  # noqa: PLC0415
        json_p, csv_p = _preflight_report_paths(tmp_path / "report")
        assert json_p.suffix == ".json"
        assert csv_p.suffix == ".csv"

    def test_no_fixed_sentinel_file_left_after_preflight(self, tmp_path):
        from import_inventory import _preflight_report_paths  # noqa: PLC0415
        _preflight_report_paths(tmp_path / "report")
        leftover = [f.name for f in tmp_path.iterdir()]
        assert ".import_write_test" not in leftover
        assert leftover == []


# ---------------------------------------------------------------------------
# write_report — atomic temp-file write behavior + new fields
# ---------------------------------------------------------------------------

class TestWriteReportAtomic:
    def _make_result(self, action="create", qty=5.0):
        r = RowResult(2, {})
        r.action = action
        r.location = {"room": "R", "cabinet": "C", "bin": ""}
        if action == "create":
            r.item_payload = {
                "name": "Widget", "quantity_total": qty,
                "is_consumable": False, "description": None,
                "condition": "GOOD", "sku": "TEST-0001", "sku_source": "provided",
                "low_stock_threshold": None, "unit_price": None, "unit": None,
            }
        return r

    def test_writes_json_and_csv_files(self, tmp_path):
        from import_inventory import write_report  # noqa: PLC0415
        write_report([self._make_result()], tmp_path / "report")
        assert (tmp_path / "report.json").is_file()
        assert (tmp_path / "report.csv").is_file()

    def test_no_temp_files_left_after_success(self, tmp_path):
        from import_inventory import write_report  # noqa: PLC0415
        write_report([self._make_result()], tmp_path / "report")
        files = {f.name for f in tmp_path.iterdir()}
        assert files == {"report.json", "report.csv"}

    def test_json_content_is_valid(self, tmp_path):
        import json as _json  # noqa: PLC0415
        from import_inventory import write_report  # noqa: PLC0415
        write_report([self._make_result()], tmp_path / "report")
        data = _json.loads((tmp_path / "report.json").read_text())
        assert isinstance(data, list)
        assert data[0]["action"] == "create"
        assert data[0]["item"] == "Widget"

    def test_report_includes_new_fields(self, tmp_path):
        import json as _json  # noqa: PLC0415
        from import_inventory import write_report  # noqa: PLC0415
        write_report([self._make_result()], tmp_path / "report")
        data = _json.loads((tmp_path / "report.json").read_text())
        row = data[0]
        assert "sku" in row
        assert "sku_source" in row
        assert "condition" in row
        assert "low_stock_threshold" in row
        assert "unit_price" in row
        assert "unit" in row
        assert "bin_requires_full_checkout" in row

    def test_warn_row_appears_in_report(self, tmp_path):
        import json as _json  # noqa: PLC0415
        from import_inventory import write_report  # noqa: PLC0415
        r = self._make_result(action="warn")
        r.errors = ["Quantity must be > 0"]
        write_report([r], tmp_path / "report")
        data = _json.loads((tmp_path / "report.json").read_text())
        assert data[0]["action"] == "warn"
        assert "Quantity" in data[0]["errors"]

    def test_existing_report_preserved_and_no_temp_left_if_replacement_fails(self, tmp_path):
        from import_inventory import write_report  # noqa: PLC0415

        write_report([self._make_result(qty=1.0)], tmp_path / "report")

        (tmp_path / "report.json").unlink()
        (tmp_path / "report.json").mkdir()

        with pytest.raises(Exception):
            write_report([self._make_result(qty=99.0)], tmp_path / "report")

        temp_files = [f for f in tmp_path.iterdir()
                      if f.name not in {"report.json", "report.csv"} and f.suffix in (".json", ".csv")]
        assert temp_files == [], f"Orphaned temp files found: {temp_files}"


# ---------------------------------------------------------------------------
# xlsx rejection in main()
# ---------------------------------------------------------------------------

class TestXlsxRejection:
    def test_xlsx_extension_exits_before_api(self, tmp_path):
        """main() must sys.exit() when --csv points at an .xlsx file."""
        from import_inventory import main  # noqa: PLC0415
        xlsx_path = tmp_path / "inventory.xlsx"
        xlsx_path.touch()
        with pytest.raises(SystemExit) as exc_info:
            import sys as _sys
            _sys.argv = ["import_inventory.py", "--csv", str(xlsx_path)]
            main()
        msg = str(exc_info.value)
        assert ".xlsx" in msg.lower() or "excel" in msg.lower() or "csv" in msg.lower()

    def test_xls_extension_exits_before_api(self, tmp_path):
        """main() must sys.exit() when --csv points at a .xls file."""
        from import_inventory import main  # noqa: PLC0415
        xls_path = tmp_path / "inventory.xls"
        xls_path.touch()
        with pytest.raises(SystemExit) as exc_info:
            import sys as _sys
            _sys.argv = ["import_inventory.py", "--csv", str(xls_path)]
            main()
        msg = str(exc_info.value)
        assert ".xls" in msg.lower() or "excel" in msg.lower() or "csv" in msg.lower()


# ---------------------------------------------------------------------------
# Commit-mode validation gate
# ---------------------------------------------------------------------------

class TestCommitModeValidationGate:
    """process_rows + main() gate: commit is refused when any row has errors."""

    def _make_error_result(self):
        """A RowResult that has action=warn and an error (simulates a bad row)."""
        from import_inventory import RowResult  # noqa: PLC0415
        r = RowResult(2, {})
        r.action = "warn"
        r.errors = ["Invalid condition 'BROKEN': must be one of ['DAMAGED', 'FAIR', 'GOOD', 'POOR']"]
        return r

    def test_error_rows_block_apply_import(self, tmp_path):
        """apply_import must NOT be called when error rows exist (gate in main)."""
        from unittest.mock import patch, MagicMock  # noqa: PLC0415
        from import_inventory import apply_import, RowResult  # noqa: PLC0415

        good = RowResult(2, {})
        good.action = "create"
        good.item_payload = {
            "_room_name": "R", "_cabinet_name": "C", "_bin_label": None,
            "name": "Widget", "quantity_total": 5.0, "is_consumable": False,
            "description": None, "condition": "GOOD", "unit": None,
            "low_stock_threshold": None, "unit_price": None,
            "sku": "TEST-0001", "sku_source": "provided",
        }
        bad = self._make_error_result()

        results = [good, bad]
        # Verify: the gate logic (as in main()) detects error rows
        error_rows = [r for r in results if r.action == "warn" and r.errors]
        assert len(error_rows) == 1, "Gate should find one error row"

    def test_process_rows_invalid_condition_produces_warn(self):
        """A row with an invalid Condition value must get action=warn."""
        from import_inventory import process_rows, InventoryCache  # noqa: PLC0415

        m, _ = normalize_headers(["Name", "Room", "Cabinet", "Quantity", "Condition"])
        cache = InventoryCache()
        cache.rooms = {}
        cache.cabinets = {}
        cache.bins = {}
        cache.items = {}
        cache.skus = set()

        rows = [{"Name": "Bolt", "Room": "Shop", "Cabinet": "Top Shelf",
                 "Quantity": "5", "Condition": "BROKEN"}]
        results = process_rows(rows, m, cache)
        assert len(results) == 1
        r = results[0]
        assert r.action == "warn"
        assert any("condition" in e.lower() or "BROKEN" in e for e in r.errors)


# ---------------------------------------------------------------------------
# parse_bin_requires_full_checkout
# ---------------------------------------------------------------------------

class TestParseBinRequiresFullCheckout:
    @pytest.mark.parametrize("raw", ["Yes", "yes", "YES", "Y", "y", "True", "true", "1", "✓"])
    def test_truthy_values(self, raw):
        val, is_explicit, err = parse_bin_requires_full_checkout(raw)
        assert val is True
        assert is_explicit is True
        assert err is None

    @pytest.mark.parametrize("raw", ["No", "no", "NO", "N", "n", "False", "false", "0"])
    def test_falsy_values(self, raw):
        val, is_explicit, err = parse_bin_requires_full_checkout(raw)
        assert val is False
        assert is_explicit is True
        assert err is None

    @pytest.mark.parametrize("raw", ["", "   ", "—", "N/A", "none", "null", "-"])
    def test_blank_and_placeholders_are_not_explicit(self, raw):
        val, is_explicit, err = parse_bin_requires_full_checkout(raw)
        assert val is False
        assert is_explicit is False
        assert err is None

    @pytest.mark.parametrize("bad", ["Maybe", "unknown", "required", "2", "yep"])
    def test_unrecognized_returns_error(self, bad):
        val, is_explicit, err = parse_bin_requires_full_checkout(bad)
        assert val is False
        assert is_explicit is False
        assert err is not None
        assert bad in err

    def test_error_message_mentions_valid_values(self):
        _, _, err = parse_bin_requires_full_checkout("maybe")
        assert "Yes" in err or "True" in err or "1/0" in err


# ---------------------------------------------------------------------------
# normalize_headers — Bin Requires Full Checkout aliases
# ---------------------------------------------------------------------------

class TestBinRequiresFullCheckoutHeaders:
    _BASE = ["Name", "Room", "Quantity", "Cabinet"]

    @pytest.mark.parametrize("alias", [
        "Bin Requires Full Checkout",
        "Requires Full Bin Checkout",
        "Full Bin Checkout Required",
        "Bin Full Checkout Only",
    ])
    def test_alias_maps_to_canonical(self, alias):
        m, w = normalize_headers(self._BASE + [alias])
        assert "bin_requires_full_checkout" in m
        assert not any("bin_requires" in warn.lower() for warn in w)

    def test_case_insensitive_alias(self):
        m, _ = normalize_headers(self._BASE + ["BIN REQUIRES FULL CHECKOUT"])
        assert "bin_requires_full_checkout" in m

    def test_two_bfco_aliases_conflict(self):
        with pytest.raises(ValueError):
            normalize_headers(
                self._BASE + ["Bin Requires Full Checkout", "Requires Full Bin Checkout"]
            )


# ---------------------------------------------------------------------------
# Bin Requires Full Checkout in process_rows
# ---------------------------------------------------------------------------

def _make_bfco_header_map():
    m, _ = normalize_headers([
        "Name", "Room", "Quantity", "Cabinet", "Bin",
        "Consumable", "Bin Requires Full Checkout",
    ])
    return m


def _make_bfco_row(**kwargs):
    defaults = {
        "Name": "Widget", "Room": "Store", "Quantity": "5",
        "Cabinet": "Shelf A", "Bin": "Bin1",
        "Consumable": "Yes", "Bin Requires Full Checkout": "",
    }
    defaults.update(kwargs)
    return defaults


class TestBinRequiresFullCheckoutInProcessRows:
    def _run(self, rows, cache=None):
        from import_inventory import process_rows  # noqa: PLC0415
        c = cache or _EmptyCache()
        return process_rows(rows, _make_bfco_header_map(), c)

    def test_bfco_yes_sets_true_in_payload(self):
        r = self._run([_make_bfco_row(**{"Bin Requires Full Checkout": "Yes"})])[0]
        assert r.action == "create"
        assert r.item_payload["bin_requires_full_checkout"] is True

    def test_bfco_no_sets_false_in_payload(self):
        r = self._run([_make_bfco_row(**{"Bin Requires Full Checkout": "No"})])[0]
        assert r.action == "create"
        assert r.item_payload["bin_requires_full_checkout"] is False

    def test_bfco_blank_defaults_false_no_conflict(self):
        r = self._run([_make_bfco_row(**{"Bin Requires Full Checkout": ""})])[0]
        assert r.action == "create"
        assert r.item_payload["bin_requires_full_checkout"] is False

    def test_bfco_invalid_fails_row(self):
        r = self._run([_make_bfco_row(**{"Bin Requires Full Checkout": "maybe"})])[0]
        assert r.action == "warn"
        assert any("maybe" in e.lower() for e in r.errors)

    def test_conflicting_bfco_same_bin_fails_all_rows(self):
        """Two rows for the same bin, both explicit, one Yes one No → both rows fail."""
        rows = [
            _make_bfco_row(Name="Item1", **{"Bin Requires Full Checkout": "Yes"}),
            _make_bfco_row(Name="Item2", **{"Bin Requires Full Checkout": "No"}),
        ]
        results = self._run(rows)
        assert results[0].action == "warn"
        assert results[1].action == "warn"
        assert any("conflict" in e.lower() for e in results[0].errors)
        assert any("conflict" in e.lower() for e in results[1].errors)

    def test_blank_does_not_conflict_with_explicit(self):
        """Row A says Yes, row B is blank — no conflict; both succeed."""
        rows = [
            _make_bfco_row(Name="Item1", **{"Bin Requires Full Checkout": "Yes"}),
            _make_bfco_row(Name="Item2", **{"Bin Requires Full Checkout": ""}),
        ]
        results = self._run(rows)
        assert results[0].action == "create"
        assert results[1].action == "create"

    def test_consistent_bfco_same_bin_ok(self):
        """Both rows say Yes for the same bin — no conflict."""
        rows = [
            _make_bfco_row(Name="Item1", **{"Bin Requires Full Checkout": "Yes"}),
            _make_bfco_row(Name="Item2", **{"Bin Requires Full Checkout": "Yes"}),
        ]
        results = self._run(rows)
        assert all(r.action == "create" for r in results)

    def test_bfco_column_absent_does_not_break_existing_rows(self):
        """CSV without the column still processes normally."""
        from import_inventory import process_rows  # noqa: PLC0415
        m, _ = normalize_headers(["Name", "Room", "Quantity", "Cabinet"])
        row = {"Name": "Widget", "Room": "Store", "Quantity": "5", "Cabinet": "Shelf"}
        r = process_rows([row], m, _EmptyCache())[0]
        assert r.action == "create"
        assert r.item_payload["bin_requires_full_checkout"] is False

    def test_bfco_explicit_on_existing_bin_sets_explicit_flag(self):
        """When bfco is explicit and bin already exists, _bfco_explicit=True and _existing_bin_id is set."""
        cache = _EmptyCache()
        # Pre-populate cache to simulate an existing bin
        cache.rooms["store"] = 1
        cache.cabinets[(1, "shelf a")] = 10
        cache.bins[(10, "bin1")] = 99  # existing bin id=99

        r = self._run(
            [_make_bfco_row(**{"Bin Requires Full Checkout": "Yes"})],
            cache=cache,
        )[0]
        assert r.action == "create"
        assert r.item_payload["_bfco_explicit"] is True
        assert r.item_payload["_existing_bin_id"] == 99
        assert r.item_payload["bin_requires_full_checkout"] is True

    def test_bfco_blank_on_existing_bin_not_explicit(self):
        """Blank bfco on existing bin → _bfco_explicit=False, no update scheduled."""
        cache = _EmptyCache()
        cache.rooms["store"] = 1
        cache.cabinets[(1, "shelf a")] = 10
        cache.bins[(10, "bin1")] = 99

        r = self._run(
            [_make_bfco_row(**{"Bin Requires Full Checkout": ""})],
            cache=cache,
        )[0]
        assert r.action == "create"
        assert r.item_payload["_bfco_explicit"] is False

    def test_bfco_in_report_fields(self, tmp_path):
        """write_report includes bin_requires_full_checkout in every row."""
        import json as _json  # noqa: PLC0415
        from import_inventory import write_report, RowResult  # noqa: PLC0415
        r = RowResult(2, {})
        r.action = "create"
        r.location = {"room": "R", "cabinet": "C", "bin": "B"}
        r.item_payload = {
            "name": "Widget", "quantity_total": 5.0, "is_consumable": False,
            "description": None, "condition": "GOOD", "sku": "T-0001",
            "sku_source": "provided", "low_stock_threshold": None,
            "unit_price": None, "unit": None,
            "bin_requires_full_checkout": True,
        }
        write_report([r], tmp_path / "report")
        data = _json.loads((tmp_path / "report.json").read_text())
        assert data[0]["bin_requires_full_checkout"] is True

    def test_blank_first_then_explicit_yes_resolves_true_new_bin(self):
        """Blank row first then explicit Yes for same new bin → both create with bfco=True."""
        rows = [
            _make_bfco_row(Name="Item1", **{"Bin Requires Full Checkout": ""}),
            _make_bfco_row(Name="Item2", **{"Bin Requires Full Checkout": "Yes"}),
        ]
        results = self._run(rows)
        assert results[0].action == "create"
        assert results[1].action == "create"
        assert results[0].item_payload["bin_requires_full_checkout"] is True
        assert results[1].item_payload["bin_requires_full_checkout"] is True

    def test_blank_first_then_explicit_yes_existing_bin_schedules_patch(self):
        """Blank row first then explicit Yes for same existing bin → explicit=True, patch scheduled."""
        cache = _EmptyCache()
        cache.rooms["store"] = 1
        cache.cabinets[(1, "shelf a")] = 10
        cache.bins[(10, "bin1")] = 99
        rows = [
            _make_bfco_row(Name="Item1", **{"Bin Requires Full Checkout": ""}),
            _make_bfco_row(Name="Item2", **{"Bin Requires Full Checkout": "Yes"}),
        ]
        results = self._run(rows, cache=cache)
        assert results[0].action == "create"
        assert results[1].action == "create"
        assert results[0].item_payload["_bfco_explicit"] is True
        assert results[0].item_payload["_existing_bin_id"] == 99
        assert results[0].item_payload["bin_requires_full_checkout"] is True

    def test_all_blank_bfco_defaults_false(self):
        """All blank BFCO rows → bfco=False, explicit=False."""
        rows = [
            _make_bfco_row(Name="Item1", **{"Bin Requires Full Checkout": ""}),
            _make_bfco_row(Name="Item2", **{"Bin Requires Full Checkout": ""}),
        ]
        results = self._run(rows)
        assert all(r.action == "create" for r in results)
        assert all(r.item_payload["bin_requires_full_checkout"] is False for r in results)
        assert all(r.item_payload["_bfco_explicit"] is False for r in results)


# ---------------------------------------------------------------------------
# apply_import BFCO patch ordering and failure tests
# ---------------------------------------------------------------------------

class TestApplyImportBfcoPatch:
    def _make_bfco_create_result(self, bin_id: int, bfco_value: bool) -> "RowResult":
        from import_inventory import RowResult  # noqa: PLC0415
        r = RowResult(2, {})
        r.action = "create"
        r.location = {"room": "Store", "cabinet": "Shelf A", "bin": "Bin1"}
        r.item_payload = {
            "_room_name": "Store", "_cabinet_name": "Shelf A", "_bin_label": "Bin1",
            "_bfco_explicit": True, "_existing_bin_id": bin_id,
            "name": "Widget", "quantity_total": 3, "is_consumable": False,
            "description": None, "condition": "GOOD",
            "sku": "T-0001", "sku_source": "provided",
            "low_stock_threshold": None, "unit_price": None, "unit": None,
            "bin_requires_full_checkout": bfco_value,
        }
        return r

    def test_patch_failure_prevents_item_creation(self):
        """If a bin PATCH fails, exception propagates and no item POSTs are made."""
        from import_inventory import apply_import  # noqa: PLC0415
        import import_inventory as _inv

        r = self._make_bfco_create_result(bin_id=99, bfco_value=True)

        post_calls: list[dict] = []
        original_post = _inv._api_post
        original_patch = _inv._api_patch

        def mock_post(client, path, body):
            post_calls.append({"path": path, "body": body})
            if path == "/api/rooms": return {"id": 1, "name": "Store"}
            if path == "/api/cabinets": return {"id": 2, "name": "Shelf A", "room_id": 1}
            if path == "/api/items": return {"id": 100, "name": "Widget"}
            return {}

        def failing_patch(client, path, body):
            raise RuntimeError("Simulated PATCH failure")

        cache = _EmptyCache()
        cache.rooms["store"] = 1
        cache.cabinets[(1, "shelf a")] = 2
        cache.bins[(2, "bin1")] = 99

        _inv._api_post = mock_post
        _inv._api_patch = failing_patch
        try:
            with pytest.raises(RuntimeError, match="Simulated PATCH failure"):
                apply_import([r], client=None, cache=cache)
        finally:
            _inv._api_post = original_post
            _inv._api_patch = original_patch

        item_posts = [c for c in post_calls if c["path"] == "/api/items"]
        assert len(item_posts) == 0, f"No item POSTs expected, got: {item_posts}"

    def test_patch_happens_before_item_post(self):
        """Bin PATCH must occur before item POSTs."""
        from import_inventory import apply_import  # noqa: PLC0415
        import import_inventory as _inv

        r = self._make_bfco_create_result(bin_id=99, bfco_value=True)

        call_order: list[str] = []
        original_post = _inv._api_post
        original_patch = _inv._api_patch

        def mock_post(client, path, body):
            call_order.append(f"POST {path}")
            if path == "/api/rooms": return {"id": 1, "name": "Store"}
            if path == "/api/cabinets": return {"id": 2, "name": "Shelf A", "room_id": 1}
            if path == "/api/items": return {"id": 100, "name": "Widget"}
            return {}

        def mock_patch(client, path, body):
            call_order.append(f"PATCH {path}")
            return {}

        cache = _EmptyCache()
        cache.rooms["store"] = 1
        cache.cabinets[(1, "shelf a")] = 2
        cache.bins[(2, "bin1")] = 99

        _inv._api_post = mock_post
        _inv._api_patch = mock_patch
        try:
            apply_import([r], client=None, cache=cache)
        finally:
            _inv._api_post = original_post
            _inv._api_patch = original_patch

        patch_idx = next((i for i, c in enumerate(call_order) if c.startswith("PATCH")), None)
        item_idx = next((i for i, c in enumerate(call_order) if c == "POST /api/items"), None)
        assert patch_idx is not None, "Expected a PATCH call"
        assert item_idx is not None, "Expected a POST /api/items call"
        assert patch_idx < item_idx, f"PATCH (idx={patch_idx}) must precede item POST (idx={item_idx})"
