from __future__ import annotations

import json
import re
from typing import Any

from retailsense.repository import default_repository


def get_retail_review_overview() -> str:
    data = default_repository.overview()
    return json.dumps(data, default=str)


def list_stores() -> str:
    data = default_repository.store_options()
    return json.dumps(data, default=str)


def list_priority_recommendations(priority: str = "high", page: int = 1, store_id: str | None = None) -> str:
    data = default_repository.list_priority_recommendations(
        priority=priority,
        page=page,
        page_size=15,
        store_id=store_id,
    )
    return json.dumps(data, default=str)


def inspect_item_signal(item_id: str, store_id: str) -> str:
    data = default_repository.inspect_item_signal(item_id=item_id, store_id=store_id)
    compact = {
        key: data.get(key)
        for key in [
            "item_id",
            "store_id",
            "priority",
            "trend_label",
            "recommended_action",
            "recent_28_units",
            "baseline_28_units",
            "latest_sell_price",
            "recent_event_days",
            "recent_snap_days",
            "price_response_label",
            "explanation",
        ]
    }
    return json.dumps(compact, default=str)


def fetch_item_weekly_context(item_id: str, store_id: str) -> str:
    data = default_repository.fetch_item_weekly_context(item_id=item_id, store_id=store_id)
    return json.dumps(data, default=str)


def analyze_price_opportunity(item_id: str, store_id: str) -> str:
    data = default_repository.analyze_price_opportunity(item_id=item_id, store_id=store_id)
    return json.dumps(data, default=str)


def deterministic_answer(question: str, item_id: str | None = None, store_id: str | None = None) -> str:
    lower = question.lower()
    if item_id and store_id:
        item = default_repository.inspect_item_signal(item_id=item_id, store_id=store_id)
    elif "compare" in lower and "high" in lower and "medium" in lower:
        overview = default_repository.overview()
        priorities = overview["priorities"]
        return (
            f"The high-priority queue has {priorities['high']:,} item-store rows that should be reviewed first, "
            f"while the medium-priority queue has {priorities['medium']:,} rows with visible but less urgent signals."
        )
    elif "store" in lower and ("list" in lower or "which" in lower or "available" in lower):
        stores = [store["store_id"] for store in default_repository.store_options()]
        return "RetailSense has prepared review data for these stores: " + ", ".join(stores) + "."
    elif match := re.search(r"\b(CA|TX|WI)_\d\b", question):
        store = match.group(0)
        priority = "medium" if "medium" in lower else "low" if "low" in lower else "high"
        queue = default_repository.list_priority_recommendations(
            priority=priority,
            page=1,
            page_size=3,
            store_id=store,
        )
        if not queue["items"]:
            return f"I do not see {priority}-priority review items for {store} in the prepared data."
        items = ", ".join(f"{row['item_id']} ({row['recommended_action'].replace('_', ' ')})" for row in queue["items"])
        return f"For {store}, the first {priority}-priority review items are {items}."
    elif "top" in lower or "high" in lower or "priority" in lower:
        queue = default_repository.list_priority_recommendations(priority="high", page=1, page_size=1)
        if not queue["items"]:
            return "I do not see any high-priority review item in the prepared data."
        top = queue["items"][0]
        item = default_repository.inspect_item_signal(top["item_id"], top["store_id"])
    else:
        overview = default_repository.overview()
        priorities = overview["priorities"]
        return (
            "RetailSense has prepared "
            f"{overview['total_item_store_rows']:,} item-store review rows. "
            f"The queue currently has {priorities['high']:,} high, "
            f"{priorities['medium']:,} medium, and {priorities['low']:,} low priority rows."
        )

    explanation: dict[str, Any] = item["explanation"]
    return (
        f"{item['item_id']} at {item['store_id']} is marked {item['priority']} priority. "
        f"{explanation['demand']} {explanation['event']} {explanation['price']} "
        f"{explanation['recommendation']}"
    )
