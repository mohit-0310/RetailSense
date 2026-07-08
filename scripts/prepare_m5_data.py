from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from retailsense.config import RAW_DATA_DIR, DEFAULT_PREPARED_DIR
from retailsense.signal_engine import BASELINE_DAYS, RECENT_DAYS, TAIL_DAYS, finalize_signals


META_COLS = ["id", "item_id", "dept_id", "cat_id", "store_id", "state_id"]


def _sales_day_columns(sales_path: Path) -> list[str]:
    with sales_path.open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    return [col for col in header if col.startswith("d_")]


def _load_sales_tail(raw_dir: Path) -> tuple[pd.DataFrame, list[str]]:
    sales_path = raw_dir / "sales_train_validation.csv"
    day_cols = _sales_day_columns(sales_path)
    tail_cols = day_cols[-TAIL_DAYS:]
    usecols = META_COLS + tail_cols
    sales = pd.read_csv(sales_path, usecols=usecols)
    for col in tail_cols:
        sales[col] = pd.to_numeric(sales[col], downcast="integer")
    return sales, tail_cols


def _load_calendar(raw_dir: Path) -> pd.DataFrame:
    calendar = pd.read_csv(raw_dir / "calendar.csv")
    calendar["date"] = pd.to_datetime(calendar["date"])
    for col in ["event_name_1", "event_type_1", "event_name_2", "event_type_2"]:
        calendar[col] = calendar[col].fillna("")
    calendar["has_event"] = (
        calendar["event_name_1"].ne("") | calendar["event_name_2"].ne("")
    )
    calendar["is_weekend"] = calendar["weekday"].isin(["Saturday", "Sunday"])
    return calendar


def _daily_tail(sales: pd.DataFrame, calendar: pd.DataFrame, tail_cols: list[str]) -> pd.DataFrame:
    id_cols = META_COLS
    daily = sales[id_cols + tail_cols].melt(
        id_vars=id_cols,
        value_vars=tail_cols,
        var_name="d",
        value_name="units",
    )
    calendar_cols = [
        "d",
        "date",
        "wm_yr_wk",
        "weekday",
        "has_event",
        "is_weekend",
        "snap_CA",
        "snap_TX",
        "snap_WI",
    ]
    daily = daily.merge(calendar[calendar_cols], on="d", how="left")
    daily["snap_day"] = 0
    for state in ["CA", "TX", "WI"]:
        daily.loc[daily["state_id"].eq(state), "snap_day"] = daily.loc[
            daily["state_id"].eq(state), f"snap_{state}"
        ]
    daily["snap_day"] = daily["snap_day"].astype("int8")
    return daily.drop(columns=["snap_CA", "snap_TX", "snap_WI"])


def _weekly_price_context(raw_dir: Path, daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    week_order = sorted(daily["wm_yr_wk"].dropna().unique())
    context_weeks = week_order[-16:]
    recent_price_weeks = week_order[-4:]
    baseline_price_weeks = week_order[-16:-4]

    weekly_sales = (
        daily.groupby(["item_id", "store_id", "wm_yr_wk"], as_index=False)
        .agg(
            units=("units", "sum"),
            week_start=("date", "min"),
            week_end=("date", "max"),
            event_days=("has_event", "sum"),
            snap_days=("snap_day", "sum"),
        )
    )
    weekly_sales = weekly_sales[weekly_sales["wm_yr_wk"].isin(context_weeks)]

    prices = pd.read_csv(
        raw_dir / "sell_prices.csv",
        dtype={"store_id": "string", "item_id": "string", "wm_yr_wk": "int32", "sell_price": "float32"},
    )
    prices = prices[prices["wm_yr_wk"].isin(context_weeks)]
    weekly = weekly_sales.merge(prices, on=["store_id", "item_id", "wm_yr_wk"], how="left")

    recent_prices = (
        weekly[weekly["wm_yr_wk"].isin(recent_price_weeks)]
        .groupby(["item_id", "store_id"], as_index=False)
        .agg(recent_price_avg=("sell_price", "mean"))
    )
    baseline_prices = (
        weekly[weekly["wm_yr_wk"].isin(baseline_price_weeks)]
        .groupby(["item_id", "store_id"], as_index=False)
        .agg(baseline_price_avg=("sell_price", "mean"))
    )
    latest_prices = (
        weekly.sort_values("wm_yr_wk")
        .groupby(["item_id", "store_id"], as_index=False)
        .tail(1)[["item_id", "store_id", "sell_price"]]
        .rename(columns={"sell_price": "latest_sell_price"})
    )

    response_rows = []
    for (item_id, store_id), group in weekly.dropna(subset=["sell_price"]).groupby(["item_id", "store_id"]):
        median_price = group["sell_price"].median()
        lower = group[group["sell_price"] < median_price]
        regular = group[group["sell_price"] >= median_price]
        lower_avg = float(lower["units"].mean()) if len(lower) else 0.0
        regular_avg = float(regular["units"].mean()) if len(regular) else 0.0
        label = "no_clear_markdown_signal"
        if len(lower) >= 2 and len(regular) >= 2 and lower_avg >= regular_avg * 1.2 and lower_avg >= 1:
            label = "lower_price_weeks_moved_better"
        response_rows.append(
            {
                "item_id": item_id,
                "store_id": store_id,
                "lower_price_week_avg_units": round(lower_avg, 2),
                "regular_price_week_avg_units": round(regular_avg, 2),
                "price_response_label": label,
            }
        )
    price_response = pd.DataFrame(response_rows)

    price_context = latest_prices.merge(recent_prices, on=["item_id", "store_id"], how="outer")
    price_context = price_context.merge(baseline_prices, on=["item_id", "store_id"], how="outer")
    price_context = price_context.merge(price_response, on=["item_id", "store_id"], how="outer")
    price_context["price_change_12w_pct"] = (
        (price_context["recent_price_avg"] - price_context["baseline_price_avg"])
        / price_context["baseline_price_avg"]
        * 100
    ).round(2)

    price_context["price_response_label"] = price_context["price_response_label"].fillna(
        "no_clear_markdown_signal"
    )
    price_context.loc[
        price_context["price_response_label"].eq("no_clear_markdown_signal")
        & (price_context["price_change_12w_pct"] >= 5),
        "price_response_label",
    ] = "recent_price_increased"
    price_context.loc[
        price_context["price_response_label"].eq("no_clear_markdown_signal")
        & (price_context["price_change_12w_pct"] <= -5),
        "price_response_label",
    ] = "recent_price_decreased"

    return weekly, price_context


def _build_signals(
    sales: pd.DataFrame,
    daily: pd.DataFrame,
    price_context: pd.DataFrame,
    tail_cols: list[str],
) -> pd.DataFrame:
    baseline_cols = tail_cols[:BASELINE_DAYS]
    recent_cols = tail_cols[BASELINE_DAYS:]
    last_7_cols = tail_cols[-7:]
    prior_7_cols = tail_cols[-14:-7]

    signals = sales[META_COLS].copy()
    signals["recent_28_units"] = sales[recent_cols].sum(axis=1)
    signals["baseline_84_units"] = sales[baseline_cols].sum(axis=1)
    signals["baseline_28_units"] = (signals["baseline_84_units"] / 3).round(2)
    signals["last_7_units"] = sales[last_7_cols].sum(axis=1)
    signals["prior_7_units"] = sales[prior_7_cols].sum(axis=1)

    recent_days = set(recent_cols)
    recent_calendar = daily[daily["d"].isin(recent_days)].drop_duplicates(["state_id", "d"])
    context = (
        recent_calendar.groupby(["state_id"], as_index=False)
        .agg(
            recent_event_days=("has_event", "sum"),
            recent_snap_days=("snap_day", "sum"),
            recent_weekend_days=("is_weekend", "sum"),
        )
        .drop_duplicates("state_id")
    )
    signals = signals.merge(context, on="state_id", how="left")
    signals = signals.merge(price_context, on=["item_id", "store_id"], how="left")

    fill_zero = [
        "recent_event_days",
        "recent_snap_days",
        "recent_weekend_days",
        "latest_sell_price",
        "recent_price_avg",
        "baseline_price_avg",
        "price_change_12w_pct",
        "lower_price_week_avg_units",
        "regular_price_week_avg_units",
    ]
    for col in fill_zero:
        signals[col] = signals[col].fillna(0)
    signals["price_response_label"] = signals["price_response_label"].fillna("no_clear_markdown_signal")
    return finalize_signals(signals)


def prepare(raw_dir: Path, prepared_dir: Path) -> None:
    prepared_dir.mkdir(parents=True, exist_ok=True)
    sales, tail_cols = _load_sales_tail(raw_dir)
    calendar = _load_calendar(raw_dir)
    daily = _daily_tail(sales, calendar, tail_cols)
    weekly, price_context = _weekly_price_context(raw_dir, daily)
    signals = _build_signals(sales, daily, price_context, tail_cols)

    calendar.to_parquet(prepared_dir / "calendar.parquet", index=False)
    daily.to_parquet(prepared_dir / "daily_sales_tail.parquet", index=False)
    weekly.to_parquet(prepared_dir / "weekly_context.parquet", index=False)
    signals.to_parquet(prepared_dir / "item_store_signals.parquet", index=False)
    sales[META_COLS].to_parquet(prepared_dir / "item_lookup.parquet", index=False)

    summary = {
        "item_store_rows": len(signals),
        "daily_tail_rows": len(daily),
        "weekly_context_rows": len(weekly),
        "high_priority": int(signals["priority"].eq("high").sum()),
        "medium_priority": int(signals["priority"].eq("medium").sum()),
        "low_priority": int(signals["priority"].eq("low").sum()),
        "latest_sales_day": tail_cols[-1],
    }
    pd.DataFrame([summary]).to_json(prepared_dir / "prep_summary.json", orient="records", indent=2)
    print(summary)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare RetailSense artifacts from the M5 dataset.")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DATA_DIR)
    parser.add_argument("--prepared-dir", type=Path, default=DEFAULT_PREPARED_DIR)
    args = parser.parse_args()
    prepare(args.raw_dir, args.prepared_dir)


if __name__ == "__main__":
    main()
