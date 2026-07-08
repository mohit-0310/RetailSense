from __future__ import annotations

import math

import pandas as pd

from retailsense.text import build_short_reason


RECENT_DAYS = 28
BASELINE_DAYS = 84
TAIL_DAYS = RECENT_DAYS + BASELINE_DAYS


def classify_trends(signals: pd.DataFrame) -> pd.DataFrame:
    df = signals.copy()
    recent = df["recent_28_units"].astype(float)
    baseline = df["baseline_28_units"].astype(float)
    last_7 = df["last_7_units"].astype(float)
    prior_7 = df["prior_7_units"].astype(float)

    rising = (recent >= baseline.mul(1.45).add(4)) & ((recent - baseline) >= 5)
    falling = (baseline >= 8) & (recent <= baseline.mul(0.55).add(1)) & ((baseline - recent) >= 5)
    rising_watch = (recent >= baseline.mul(1.2).add(3)) & (last_7 >= prior_7.mul(1.15).add(1))
    falling_watch = (baseline >= 5) & (recent <= baseline.mul(0.75).add(1))
    low = (recent < 3) & (baseline < 3)

    df["trend_label"] = "stable"
    df.loc[rising_watch, "trend_label"] = "rising_watch"
    df.loc[falling_watch, "trend_label"] = "falling_watch"
    df.loc[rising, "trend_label"] = "rising_unusually"
    df.loc[falling, "trend_label"] = "falling_unusually"
    df.loc[low, "trend_label"] = "stable_low_activity"
    return df


def add_priority(signals: pd.DataFrame) -> pd.DataFrame:
    df = signals.copy()
    recent = df["recent_28_units"].astype(float)
    baseline = df["baseline_28_units"].astype(float)
    ratio = (recent + 1) / (baseline + 1)
    delta = (recent - baseline).abs()
    activity = recent + baseline

    trend_bonus = df["trend_label"].map(
        {
            "rising_unusually": 24,
            "falling_unusually": 22,
            "rising_watch": 12,
            "falling_watch": 10,
            "stable": 2,
            "stable_low_activity": 0,
        }
    ).fillna(0)
    price_bonus = df["price_response_label"].eq("lower_price_weeks_moved_better").astype(int) * 5
    event_bonus = ((df["recent_event_days"] > 0) | (df["recent_snap_days"] >= 8)).astype(int) * 3

    df["severity_score"] = (
        ratio.map(lambda v: abs(math.log(float(v))) * 12)
        + delta.clip(upper=120) * 0.45
        + activity.map(lambda v: math.log1p(float(v)) * 2.8)
        + trend_bonus
        + price_bonus
        + event_bonus
    ).round(2)

    reviewable = ~df["trend_label"].eq("stable_low_activity")
    high_cut = df.loc[reviewable, "severity_score"].quantile(0.92)
    med_cut = df.loc[reviewable, "severity_score"].quantile(0.68)

    df["priority"] = "low"
    df.loc[reviewable & (df["severity_score"] >= med_cut), "priority"] = "medium"
    df.loc[reviewable & (df["severity_score"] >= high_cut), "priority"] = "high"
    return df


def recommend_actions(signals: pd.DataFrame) -> pd.DataFrame:
    df = signals.copy()
    df["recommended_action"] = "monitor"

    rising = df["trend_label"].isin(["rising_unusually", "rising_watch"])
    falling = df["trend_label"].isin(["falling_unusually", "falling_watch"])
    markdown_signal = df["price_response_label"].eq("lower_price_weeks_moved_better")
    price_up = df["price_response_label"].eq("recent_price_increased")

    df.loc[rising & df["trend_label"].eq("rising_unusually"), "recommended_action"] = "review_replenishment"
    df.loc[rising & price_up & ~df["trend_label"].eq("rising_unusually"), "recommended_action"] = "price_watch"
    df.loc[falling, "recommended_action"] = "demand_drop_review"
    df.loc[falling & markdown_signal, "recommended_action"] = "markdown_review"
    df.loc[df["trend_label"].eq("stable_low_activity"), "recommended_action"] = "no_urgent_action"
    return df


def finalize_signals(signals: pd.DataFrame) -> pd.DataFrame:
    df = classify_trends(signals)
    df = recommend_actions(df)
    df = add_priority(df)
    df["short_reason"] = df.apply(lambda row: build_short_reason(row.to_dict()), axis=1)
    return df.sort_values(["priority", "severity_score"], ascending=[True, False])
