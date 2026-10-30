"""Tests for catalog loader (catch-001)."""

import json
from pathlib import Path
import pytest

from jobcatcher.catalog import Board, load_catalog


def test_fixture_config_expected_board_list(tmp_path: Path):
    """catch-001: Unit: fixture config -> expected board list."""
    catalog_content = {
        "companies": [
            {
                "name": "Stripe",
                "greenhouse": [{"slug": "stripe", "verified": True}],
                "ashby": [],
                "lever": [],
            },
            {
                "name": "Replicate",
                "greenhouse": [],
                "ashby": [{"slug": "replicate"}],
                "lever": [],
            },
            {
                "name": "CRED",
                "greenhouse": [],
                "ashby": [],
                "lever": [{"slug": "cred"}],
            },
        ]
    }
    cat_file = tmp_path / "watchlist_sources.json"
    cat_file.write_text(json.dumps(catalog_content), encoding="utf-8")

    boards = load_catalog(cat_file)
    assert len(boards) == 3
    assert boards[0] == Board(company="Stripe", platform="greenhouse", slug="stripe")
    assert boards[1] == Board(company="Replicate", platform="ashby", slug="replicate")
    assert boards[2] == Board(company="CRED", platform="lever", slug="cred")


def test_missing_optional_xobin_file_is_fine(tmp_path: Path):
    """catch-001: Unit: missing optional xobin file is fine."""
    cat_file = tmp_path / "watchlist_sources.json"
    cat_file.write_text(
        json.dumps({
            "companies": [
                {"name": "PhonePe", "greenhouse": [{"slug": "phonepe"}]}
            ]
        }),
        encoding="utf-8",
    )
    # Ensure no xobin file exists in tmp_path
    assert not (tmp_path / "xobin_sources.json").exists()

    boards = load_catalog(cat_file)
    assert len(boards) == 1
    assert boards[0] == Board(company="PhonePe", platform="greenhouse", slug="phonepe")


def test_malformed_main_config_raises_clear_error(tmp_path: Path):
    """catch-001: Unit: malformed main config raises a clear error."""
    # Test case 1: Not valid JSON
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{ incomplete json ...", encoding="utf-8")
    with pytest.raises(ValueError, match="Malformed main catalog JSON"):
        load_catalog(bad_json)

    # Test case 2: Missing 'companies' list
    bad_schema = tmp_path / "bad_schema.json"
    bad_schema.write_text(json.dumps({"invalid_key": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing 'companies' list"):
        load_catalog(bad_schema)

    # Test case 3: Nonexistent file raises FileNotFoundError
    with pytest.raises(FileNotFoundError, match="Main catalog file not found"):
        load_catalog(tmp_path / "nonexistent.json")


def test_merge_xobin_and_deduplication(tmp_path: Path):
    """Test merging xobin catalog when present and deduplication."""
    main_cat = tmp_path / "watchlist_sources.json"
    main_cat.write_text(
        json.dumps({
            "companies": [
                {"name": "Stripe", "greenhouse": [{"slug": "stripe"}]},
                {"name": "Swiggy", "lever": [{"slug": "swiggy"}]},
            ]
        }),
        encoding="utf-8",
    )

    xobin_cat = tmp_path / "xobin_sources.json"
    xobin_cat.write_text(
        json.dumps({
            "companies": [
                # Duplicate entry
                {"name": "Stripe", "greenhouse": [{"slug": "stripe"}]},
                # New entry
                {"name": "Zepto", "ashby": [{"slug": "zepto"}]},
            ]
        }),
        encoding="utf-8",
    )

    boards = load_catalog(main_cat, secondary_path=xobin_cat)
    assert len(boards) == 3
    assert boards[0] == Board(company="Stripe", platform="greenhouse", slug="stripe")
    assert boards[1] == Board(company="Swiggy", platform="lever", slug="swiggy")
    assert boards[2] == Board(company="Zepto", platform="ashby", slug="zepto")
