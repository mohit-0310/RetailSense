from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from retailsense.config import DEFAULT_PREPARED_DIR


def validate(prepared_dir: Path) -> None:
    signals_path = prepared_dir / "item_store_signals.parquet"
    daily_path = prepared_dir / "daily_sales_tail.parquet"
    weekly_path = prepared_dir / "weekly_context.parquet"
    for path in [signals_path, daily_path, weekly_path]:
        if not path.exists():
            raise SystemExit(f"Missing prepared artifact: {path}")

    signals = pd.read_parquet(signals_path)
    daily = pd.read_parquet(daily_path, columns=["item_id", "store_id", "d", "units"])
    weekly = pd.read_parquet(weekly_path, columns=["item_id", "store_id", "wm_yr_wk", "units", "sell_price"])

    required = [
        "item_id",
        "store_id",
        "priority",
        "trend_label",
        "recommended_action",
        "recent_28_units",
        "baseline_28_units",
        "severity_score",
    ]
    missing = [col for col in required if col not in signals.columns]
    if missing:
        raise SystemExit(f"Signals missing columns: {missing}")

    priorities = signals["priority"].value_counts().to_dict()
    if not all(priorities.get(key, 0) > 0 for key in ["high", "medium", "low"]):
        raise SystemExit(f"Expected all priorities to be present, got {priorities}")

    if signals[["recent_28_units", "baseline_28_units", "severity_score"]].isna().any().any():
        raise SystemExit("Signals contain missing numeric values.")

    if signals["recent_event_days"].max() > 28 or signals["recent_snap_days"].max() > 28:
        raise SystemExit("Calendar context is counting more than 28 recent days.")

    action_order = {
        "review_replenishment": 0,
        "markdown_review": 1,
        "demand_drop_review": 2,
        "price_watch": 3,
        "monitor": 4,
        "no_urgent_action": 5,
    }
    high = signals[signals["priority"].eq("high")].copy()
    high["action_rank"] = high["recommended_action"].map(action_order).fillna(9)
    high = high.sort_values(["action_rank", "severity_score"], ascending=[True, False]).head(5)
    print("Prepared data looks usable.")
    print(f"Signals: {len(signals):,}; daily rows: {len(daily):,}; weekly rows: {len(weekly):,}")
    print("Priority distribution:", priorities)
    print("Sample high-priority rows:")
    print(high[["item_id", "store_id", "trend_label", "recommended_action", "recent_28_units", "baseline_28_units"]].to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate RetailSense prepared artifacts.")
    parser.add_argument("--prepared-dir", type=Path, default=DEFAULT_PREPARED_DIR)
    args = parser.parse_args()
    validate(args.prepared_dir)


if __name__ == "__main__":
    main()
