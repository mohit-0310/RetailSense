from __future__ import annotations


ACTION_LABELS = {
    "review_replenishment": "Review replenishment",
    "markdown_review": "Review markdown",
    "demand_drop_review": "Review demand drop",
    "price_watch": "Price watch",
    "monitor": "Monitor",
    "no_urgent_action": "No urgent action",
}

TREND_LABELS = {
    "rising_unusually": "Rising faster than usual",
    "falling_unusually": "Falling below usual movement",
    "rising_watch": "Rising watch",
    "falling_watch": "Falling watch",
    "stable": "Stable",
    "stable_low_activity": "Low activity",
}


def action_label(action: str) -> str:
    return ACTION_LABELS.get(action, action.replace("_", " ").title())


def trend_label(trend: str) -> str:
    return TREND_LABELS.get(trend, trend.replace("_", " ").title())


def build_short_reason(row: dict) -> str:
    trend = trend_label(str(row.get("trend_label", ""))).lower()
    action = action_label(str(row.get("recommended_action", ""))).lower()
    if row.get("trend_label") == "stable_low_activity":
        return "Low recent movement. Keep on the normal watch list."
    return f"{trend}; {action} is the next review step."


def build_business_explanation(row: dict) -> dict[str, str]:
    recent = int(row.get("recent_28_units", 0))
    baseline = float(row.get("baseline_28_units", 0))
    action = action_label(str(row.get("recommended_action", "")))
    trend = trend_label(str(row.get("trend_label", "")))
    event_days = int(row.get("recent_event_days", 0))
    snap_days = int(row.get("recent_snap_days", 0))
    price_label = str(row.get("price_response_label", "no_clear_markdown_signal"))

    demand = (
        f"{trend}. Recent 28-day movement is {recent} units versus a comparable "
        f"baseline of {baseline:.1f} units."
    )
    if event_days or snap_days:
        event = (
            f"The recent window includes {event_days} event day(s) and {snap_days} "
            "SNAP day(s), so calendar context should be checked before acting."
        )
    else:
        event = "No major event or SNAP concentration is visible in the recent window."

    if price_label == "lower_price_weeks_moved_better":
        price = "Lower-price weeks historically moved better, so markdown review may be useful."
    elif price_label == "recent_price_increased":
        price = "The latest price is above the recent baseline, so price watch is sensible."
    elif price_label == "recent_price_decreased":
        price = "The latest price is below the recent baseline; monitor whether movement improves."
    else:
        price = "Price history does not show a strong standalone signal."

    recommendation = (
        f"{action}. Treat this as a human review prompt, not an automatic order or price change."
    )
    return {
        "demand": demand,
        "event": event,
        "price": price,
        "recommendation": recommendation,
    }
