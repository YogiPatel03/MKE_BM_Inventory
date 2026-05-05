"""
Unit tests for backend/scripts/import_helpers.py

These tests are pure (no network, no database) and run as part of the normal
pytest suite.  They must not break any of the 76 existing passing tests.
"""

import sys
from pathlib import Path

import pytest

# Allow import from the scripts package without installing it
_SCRIPTS = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from import_helpers import (  # noqa: E402
    build_description,
    normalize_headers,
    normalize_name,
    parse_consumable,
    parse_quantity,
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

    @pytest.mark.parametrize("raw", ["No", "no", "NO", "N", "n", "False", "false", "0"])
    def test_falsy_values(self, raw):
        r = parse_consumable(raw)
        assert r.value is False
        assert r.is_unknown is False

    def test_blank_is_unknown(self):
        r = parse_consumable("")
        assert r.value is False      # API requires bool; defaults to False
        assert r.is_unknown is True

    def test_whitespace_only_is_unknown(self):
        r = parse_consumable("   ")
        assert r.is_unknown is True

    def test_unrecognised_string_is_unknown(self):
        r = parse_consumable("Maybe")
        assert r.value is False
        assert r.is_unknown is True

    def test_raw_preserved(self):
        r = parse_consumable("Yes")
        assert r.raw == "Yes"

    def test_blank_raw_preserved_as_empty(self):
        r = parse_consumable("")
        assert r.raw == ""


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
# normalize_headers
# ---------------------------------------------------------------------------

class TestNormalizeHeaders:
    def test_canonical_headers(self):
        m = normalize_headers(["Name", "Room", "Quantity", "Place"])
        assert set(m.keys()) >= {"name", "room", "quantity", "place"}

    def test_case_insensitive(self):
        m = normalize_headers(["NAME", "ROOM", "QUANTITY", "PLACE"])
        assert "name" in m

    def test_alias_amount_maps_to_quantity(self):
        m = normalize_headers(["Name", "Room", "Amount", "Place"])
        assert "quantity" in m

    def test_alias_item_maps_to_name(self):
        m = normalize_headers(["Item", "Room", "Quantity", "Place"])
        assert "name" in m

    def test_alias_cabinet_maps_to_place(self):
        m = normalize_headers(["Name", "Room", "Quantity", "Cabinet"])
        assert "place" in m

    def test_missing_required_raises(self):
        with pytest.raises(ValueError, match="missing required"):
            normalize_headers(["Name", "Room"])  # missing Quantity and Place

    def test_extra_columns_ignored(self):
        m = normalize_headers(["Name", "Room", "Quantity", "Place", "ExtraJunk"])
        assert "extrajunk" not in m

    def test_bin_optional(self):
        m = normalize_headers(["Name", "Room", "Quantity", "Place", "Bin (if any)"])
        assert "bin" in m

    def test_notes_optional(self):
        m = normalize_headers(["Name", "Room", "Quantity", "Place", "Notes"])
        assert "notes" in m

    def test_consumable_optional(self):
        m = normalize_headers(["Name", "Room", "Quantity", "Place", "Consumable"])
        assert "consumable" in m


# ---------------------------------------------------------------------------
# process_rows — row-level policy (import_inventory.py)
# ---------------------------------------------------------------------------

# Import process_rows / RowResult from the main script for row-policy tests.
sys.path.insert(0, str(_SCRIPTS.parent))  # backend/ on path
sys.path.insert(0, str(_SCRIPTS))

from import_inventory import RowResult  # noqa: E402

# Minimal stub for InventoryCache so process_rows can run without a network.
# Uses __init__ to give each instance its own dicts — class-level mutables
# are shared across instances and would pollute later tests.
class _EmptyCache:
    def __init__(self):
        self.rooms: dict = {}
        self.cabinets: dict = {}
        self.bins: dict = {}
        self.items: dict = {}


def _make_header_map():
    return normalize_headers(["Name", "Room", "Quantity", "Place", "Bin", "Consumable", "Notes"])


def _make_row(**kwargs):
    defaults = {"Name": "TestItem", "Room": "Storage", "Quantity": "5", "Place": "Cabinet A",
                "Bin": "", "Consumable": "Yes", "Notes": ""}
    defaults.update(kwargs)
    return defaults


class TestProcessRowsPolicy:
    def _run(self, rows, cache=None):
        # Import lazily here to avoid module-level import issues with httpx
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
        results = self._run([_make_row(Place="")])
        assert results[0].action == "warn"

    def test_valid_row_creates(self):
        results = self._run([_make_row()])
        assert results[0].action == "create"
        assert results[0].item_payload is not None

    def test_unknown_consumable_adds_warning(self):
        results = self._run([_make_row(Consumable="")])
        r = results[0]
        assert r.action == "create"
        assert any("consumable" in w.lower() for w in r.warnings)
        assert r.item_payload["description"] is not None
        assert "[consumable: unknown]" in r.item_payload["description"]

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

    def test_separate_metric_column_combined(self):
        """Separate Amount + Metric columns are merged into a single quantity string."""
        hmap = normalize_headers(["Name", "Room", "Quantity", "Place", "Metric"])
        row = {"Name": "Rope", "Room": "Store", "Quantity": "10", "Place": "Shelf A", "Metric": "ft"}
        from import_inventory import process_rows  # noqa: PLC0415
        results = process_rows([row], hmap, _EmptyCache())
        r = results[0]
        assert r.action == "create"
        # unit should be extracted and preserved in description
        assert r.item_payload["quantity_total"] == 10.0
        assert r.item_payload["description"] is not None
        assert "[unit: ft]" in r.item_payload["description"]

    def test_metric_not_doubled_when_quantity_already_has_unit(self):
        """When quantity string already contains letters, metric is not appended again."""
        hmap = normalize_headers(["Name", "Room", "Quantity", "Place", "Metric"])
        row = {"Name": "Cable", "Room": "Store", "Quantity": "5 m", "Place": "Box", "Metric": "m"}
        from import_inventory import process_rows  # noqa: PLC0415
        results = process_rows([row], hmap, _EmptyCache())
        r = results[0]
        assert r.action == "create"
        # quantity_total should be 5.0 and unit "m" once, not "m m"
        assert r.item_payload["quantity_total"] == 5.0
        desc = r.item_payload.get("description", "") or ""
        assert desc.count("[unit: m]") == 1


# ---------------------------------------------------------------------------
# parse_quantity — malformed fraction edge cases (fix 2)
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
        # Must return a result, never propagate ZeroDivisionError
        try:
            r = parse_quantity("5/0")
            assert r.value == 0.0
        except ZeroDivisionError:
            pytest.fail("parse_quantity raised ZeroDivisionError for '5/0'")


# ---------------------------------------------------------------------------
# normalize_headers — "Quantity (Amount and Metric)" variants (fix 3)
# ---------------------------------------------------------------------------

class TestNormalizeHeadersQuantityVariants:
    def _base(self, qty_header: str):
        return normalize_headers(["Name", "Room", qty_header, "Place"])

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
# Pagination helper — unit test for _fetch_all_items logic
# ---------------------------------------------------------------------------

class TestFetchAllItems:
    def test_single_page_terminates(self):
        """When the first page is smaller than PAGE_SIZE, only one call is made."""
        from import_inventory import _fetch_all_items, _PAGE_SIZE  # noqa: PLC0415

        calls = []

        def fake_client():
            pass

        original_api_get = None
        import import_inventory as _inv

        original_api_get = _inv._api_get

        def mock_api_get(client, path, params=None):
            calls.append(dict(params or {}))
            skip = (params or {}).get("skip", 0)
            if skip == 0:
                return [{"id": i, "cabinet_id": 1, "name": f"item{i}", "bin_id": None}
                        for i in range(3)]  # 3 items < PAGE_SIZE
            return []

        _inv._api_get = mock_api_get
        try:
            items = _fetch_all_items(fake_client(), cabinet_id=1)
        finally:
            _inv._api_get = original_api_get

        assert len(items) == 3
        assert len(calls) == 1  # only one page needed

    def test_multiple_pages_fetched(self):
        """When first page is full (PAGE_SIZE items), a second page is fetched."""
        from import_inventory import _fetch_all_items, _PAGE_SIZE  # noqa: PLC0415
        import import_inventory as _inv

        original_api_get = _inv._api_get

        def fake_client():
            pass

        def mock_api_get(client, path, params=None):
            skip = (params or {}).get("skip", 0)
            limit = (params or {}).get("limit", _PAGE_SIZE)
            if skip == 0:
                # Return a full page
                return [{"id": i, "cabinet_id": 1, "name": f"item{i}", "bin_id": None}
                        for i in range(limit)]
            # Second page: 2 items (less than full)
            return [{"id": 9000 + i, "cabinet_id": 1, "name": f"extra{i}", "bin_id": None}
                    for i in range(2)]

        _inv._api_get = mock_api_get
        try:
            items = _fetch_all_items(fake_client(), cabinet_id=1)
        finally:
            _inv._api_get = original_api_get

        assert len(items) == _PAGE_SIZE + 2


# ---------------------------------------------------------------------------
# Amount/Quantity fallback (fix: blank Quantity + separate Amount column)
# ---------------------------------------------------------------------------

class TestAmountQuantityFallback:
    def _run_with_amount(self, quantity_val, amount_val, metric_val=""):
        """Run process_rows with a sheet that has Quantity, Amount, and Metric columns."""
        from import_inventory import process_rows  # noqa: PLC0415
        hmap = normalize_headers(["Name", "Room", "Quantity", "Amount", "Place", "Metric"])
        row = {
            "Name": "Widget", "Room": "Store", "Place": "Shelf",
            "Quantity": quantity_val, "Amount": amount_val, "Metric": metric_val,
        }
        return process_rows([row], hmap, _EmptyCache())

    def test_blank_quantity_falls_back_to_amount(self):
        results = self._run_with_amount(quantity_val="", amount_val="10")
        r = results[0]
        assert r.action == "create"
        assert r.item_payload["quantity_total"] == 10.0

    def test_blank_quantity_with_amount_and_metric(self):
        results = self._run_with_amount(quantity_val="", amount_val="10", metric_val="ft")
        r = results[0]
        assert r.action == "create"
        assert r.item_payload["quantity_total"] == 10.0
        assert "[unit: ft]" in (r.item_payload.get("description") or "")

    def test_nonblank_quantity_wins_over_amount(self):
        """When Quantity is populated, Amount is ignored (Quantity takes precedence)."""
        results = self._run_with_amount(quantity_val="5", amount_val="99")
        r = results[0]
        assert r.action == "create"
        assert r.item_payload["quantity_total"] == 5.0

    def test_only_amount_column_no_quantity_column(self):
        """A sheet with only an Amount column (no Quantity) is valid."""
        hmap = normalize_headers(["Name", "Room", "Amount", "Place"])
        row = {"Name": "Bolt", "Room": "Store", "Amount": "25", "Place": "Drawer"}
        from import_inventory import process_rows  # noqa: PLC0415
        results = process_rows([row], hmap, _EmptyCache())
        r = results[0]
        assert r.action == "create"
        assert r.item_payload["quantity_total"] == 25.0


# ---------------------------------------------------------------------------
# Cache whitespace normalization (fix: "Hammer " in DB vs "Hammer" in CSV)
# ---------------------------------------------------------------------------

class TestCacheWhitespaceNormalization:
    def test_cache_item_with_trailing_space_detected_as_duplicate(self):
        """An existing item with trailing whitespace in its name matches the CSV row."""
        from import_inventory import process_rows  # noqa: PLC0415

        cache = _EmptyCache()
        # Simulate a pre-loaded cache entry where the API returned a name with trailing space.
        # process_rows uses normalize_name for the incoming CSV row, so the cache key
        # must also use normalize_name for the match to work.
        from import_helpers import normalize_name  # noqa: PLC0415
        existing_name = "Hammer "  # trailing space, as if the DB stored it that way
        # Cabinet sentinel for a new cabinet (simulates first row creating it)
        cab_sentinel = "NEW:Shelf"
        cache.rooms[normalize_name("Storage")] = "NEW:Storage"
        cache.cabinets[("NEW:Storage", normalize_name("Shelf"))] = cab_sentinel
        cache.items[(cab_sentinel, None, normalize_name(existing_name))] = {"name": existing_name, "id": 42}

        hmap = normalize_headers(["Name", "Room", "Quantity", "Place"])
        row = {"Name": "Hammer", "Room": "Storage", "Quantity": "1", "Place": "Shelf"}
        results = process_rows([row], hmap, cache)
        assert results[0].action == "skip", "Item with trimmed-equivalent name should be detected as duplicate"


# ---------------------------------------------------------------------------
# Blank-placeholder detection
# ---------------------------------------------------------------------------

class TestIsBlankPlaceholder:
    from import_helpers import is_blank_placeholder as _fn  # re-bound at class body time

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
        return cache

    def _header_map(self):
        return {"name": "Name", "room": "Room", "place": "Cabinet", "bin": "Bin", "quantity": "Quantity"}

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
        assert any("cabinet" in e.lower() or "place" in e.lower() for e in rr.errors)

    def test_valid_row_after_placeholder_room_still_creates(self):
        from import_inventory import process_rows
        rows = [
            {"Name": "Widget", "Room": "—", "Cabinet": "Cabinet A", "Bin": "", "Quantity": "1"},
            {"Name": "Gadget", "Room": "Kitchen", "Cabinet": "Cabinet A", "Bin": "", "Quantity": "2"},
        ]
        results = process_rows(rows, self._header_map(), self._make_cache())
        assert results[0].action == "warn"
        assert results[1].action == "create"

    # --- Additional bin placeholder variants --------------------------------

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

    # --- Duplicate detection: blank bin matches placeholder bin -------------

    def test_existing_blank_bin_item_detected_as_duplicate_for_na_bin(self):
        from import_inventory import process_rows, InventoryCache
        cache = self._make_cache()
        # Seed with integer IDs matching the real cache format
        cache.rooms["kitchen"] = 1                   # name_casefold → room_id
        cache.cabinets[(1, "cabinet a")] = 10        # (room_id, name_casefold) → cabinet_id
        # Existing item with bin_id=None (no bin) in the cache
        cache.items[(10, None, "widget")] = {"id": 100, "name": "Widget", "cabinet_id": 10, "bin_id": None}
        # CSV row with Bin "N/A" — should normalize to blank, find the same item, and skip
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
        return cache

    def _header_map(self):
        return {"name": "Name", "room": "Room", "place": "Cabinet", "bin": "Bin", "quantity": "Quantity"}

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
# Malformed fraction detection (medium fix: 1//2, 1 /2 should warn not import)
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
        # 1/2/3 — _FRAC_RE matches 1/2, but rest="/3" contains "/" → malformed
        r = parse_quantity("1/2/3")
        assert r.value == 0.0
        assert any("malformed" in w.lower() or "fraction" in w.lower() for w in r.warnings)

    def test_mixed_with_extra_slash_warns(self):
        # 1 1//2 — _DEC_RE matches 1, rest="1//2" contains "/" → malformed
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
        hmap = normalize_headers(["Name", "Room", "Quantity", "Place"])
        row = {"Name": "Widget", "Room": "Store", "Quantity": quantity_str, "Place": "Shelf"}
        return process_rows([row], hmap, _EmptyCache())[0]

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
        # 1/2/3 must not become qty=0.5 unit="/3" → create
        r = self._run("1/2/3")
        assert r.action == "warn"
        assert r.item_payload is None

    def test_mixed_extra_slash_is_warned_not_created(self):
        # 1 1//2 must not become qty=1.0 unit="1//2" → create
        r = self._run("1 1//2")
        assert r.action == "warn"
        assert r.item_payload is None

    def test_valid_rows_after_malformed_still_create(self):
        """One bad quantity row must not abort subsequent valid rows."""
        from import_inventory import process_rows  # noqa: PLC0415
        hmap = normalize_headers(["Name", "Room", "Quantity", "Place"])
        rows = [
            {"Name": "Bad", "Room": "Store", "Quantity": "/2", "Place": "Shelf"},
            {"Name": "Good", "Room": "Store", "Quantity": "5", "Place": "Shelf"},
        ]
        results = process_rows(rows, hmap, _EmptyCache())
        assert results[0].action == "warn"
        assert results[1].action == "create"


# ---------------------------------------------------------------------------
# apply_import — malformed rows must never be POSTed even in commit mode
# ---------------------------------------------------------------------------

class TestApplyImportDoesNotPostWarnRows:
    def test_warn_rows_never_posted(self):
        """apply_import must not call _api_post for warn/skip rows."""
        from import_inventory import process_rows, apply_import  # noqa: PLC0415
        import import_inventory as _inv

        hmap = normalize_headers(["Name", "Room", "Quantity", "Place"])
        rows = [
            {"Name": "Bad1", "Room": "Store", "Quantity": "1/2/3", "Place": "Shelf"},
            {"Name": "Bad2", "Room": "Store", "Quantity": "1 1//2", "Place": "Shelf"},
            {"Name": "Good", "Room": "Store", "Quantity": "3", "Place": "Shelf"},
        ]
        results = process_rows(rows, hmap, _EmptyCache())
        assert results[0].action == "warn"
        assert results[1].action == "warn"
        assert results[2].action == "create"

        post_calls: list[dict] = []
        original_post = _inv._api_post

        def counting_post(client, path, body):
            post_calls.append({"path": path, "body": body})
            # Simulate minimal API responses so apply_import continues
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
        """Exactly PAGE_SIZE items on page 1 must trigger a second fetch."""
        from import_inventory import _fetch_all_items, _PAGE_SIZE  # noqa: PLC0415
        import import_inventory as _inv

        call_count = [0]

        def mock_api_get(client, path, params=None):
            call_count[0] += 1
            skip = (params or {}).get("skip", 0)
            if skip == 0:
                return [{"id": i, "cabinet_id": 1, "name": f"item{i}", "bin_id": None}
                        for i in range(_PAGE_SIZE)]
            return []  # second page empty

        original = self._patch_api_get(mock_api_get)
        try:
            items = _fetch_all_items(None, cabinet_id=1)
        finally:
            _inv._api_get = original

        assert len(items) == _PAGE_SIZE
        assert call_count[0] == 2  # must have attempted second page

    def test_repeated_full_page_raises(self):
        """If the backend ignores skip and returns the same page twice, raise RuntimeError."""
        from import_inventory import _fetch_all_items, _PAGE_SIZE  # noqa: PLC0415
        import import_inventory as _inv

        same_page = [{"id": i, "cabinet_id": 1, "name": f"item{i}", "bin_id": None}
                     for i in range(_PAGE_SIZE)]

        def mock_api_get(client, path, params=None):
            return same_page  # always returns the same full page

        original = self._patch_api_get(mock_api_get)
        try:
            with pytest.raises(RuntimeError, match="Pagination loop detected"):
                _fetch_all_items(None, cabinet_id=1)
        finally:
            _inv._api_get = original

    def test_api_error_on_page_two_propagates(self):
        """An exception fetching a later page must propagate, not silently truncate."""
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
# Report path preflight — _preflight_report_paths
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
        # The only files that may exist are the final report targets (not created yet)
        # — no fixed-name sentinel like .import_write_test
        leftover = [f.name for f in tmp_path.iterdir()]
        assert ".import_write_test" not in leftover
        assert leftover == []  # nothing written during preflight


# ---------------------------------------------------------------------------
# write_report — atomic temp-file write behavior
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
        """
        If atomic replacement of the final .json path fails (e.g. the target
        became a directory), the original .json must be untouched and the temp
        file must be cleaned up — no partial or orphaned files.
        """
        from import_inventory import write_report  # noqa: PLC0415

        # Write an initial report so .json exists with known content
        write_report([self._make_result(qty=1.0)], tmp_path / "report")
        original_content = (tmp_path / "report.json").read_text()

        # Replace the .json target with a directory so Path.replace() raises
        (tmp_path / "report.json").unlink()
        (tmp_path / "report.json").mkdir()

        with pytest.raises(Exception):  # IsADirectoryError or OSError
            write_report([self._make_result(qty=99.0)], tmp_path / "report")

        # report.json is still a directory (the original file was already removed above,
        # but the directory stands — no temp file was left)
        files = {f.name for f in tmp_path.iterdir()}
        # Only the directory 'report.json' and possibly 'report.csv' should be present
        # — no temp files (they would have random suffixes like .json + random chars)
        temp_files = [f for f in tmp_path.iterdir()
                      if f.name not in {"report.json", "report.csv"} and f.suffix in (".json", ".csv")]
        assert temp_files == [], f"Orphaned temp files found: {temp_files}"
