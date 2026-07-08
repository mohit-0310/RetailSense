from __future__ import annotations

import pytest

from retailsense.repository import PreparedDataMissingError, RetailSenseRepository


def test_high_priority_queue_pages_when_prepared_data_exists() -> None:
    repo = RetailSenseRepository()
    try:
        page = repo.list_priority_recommendations(priority="high", page=1, page_size=15)
    except PreparedDataMissingError:
        pytest.skip("Prepared data has not been generated yet.")

    assert page["priority"] == "high"
    assert page["page_size"] == 15
    assert page["total_items"] >= len(page["items"])
    assert len(page["items"]) <= 15


def test_item_detail_contains_business_explanation_when_data_exists() -> None:
    repo = RetailSenseRepository()
    try:
        page = repo.list_priority_recommendations(priority="high", page=1, page_size=1)
    except PreparedDataMissingError:
        pytest.skip("Prepared data has not been generated yet.")

    item = page["items"][0]
    detail = repo.inspect_item_signal(item["item_id"], item["store_id"])
    assert detail["explanation"]["recommendation"]
    assert "daily_sales" in detail
