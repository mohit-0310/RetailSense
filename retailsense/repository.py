from __future__ import annotations

import json
import math
from functools import cached_property
from pathlib import Path
from typing import Any

import pandas as pd

from retailsense.config import DEFAULT_PREPARED_DIR
from retailsense.text import ACTION_LABELS, TREND_LABELS, build_business_explanation


PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
ACTION_ORDER = {
    "review_replenishment": 0,
    "markdown_review": 1,
    "demand_drop_review": 2,
    "price_watch": 3,
    "monitor": 4,
    "no_urgent_action": 5,
}


class PreparedDataMissingError(RuntimeError):
    pass


class RetailSenseRepository:
    def __init__(self, prepared_dir: Path | str = DEFAULT_PREPARED_DIR):
        self.prepared_dir = Path(prepared_dir)

    def _require(self, name: str) -> Path:
        path = self.prepared_dir / name
        if not path.exists():
            raise PreparedDataMissingError(
                f"Prepared artifact is missing: {path}. Run scripts/prepare_m5_data.py first."
            )
        return path

    @cached_property
    def signals(self) -> pd.DataFrame:
        df = pd.read_parquet(self._require("item_store_signals.parquet"))
        df["priority_rank"] = df["priority"].map(PRIORITY_ORDER).fillna(9)
        df["action_rank"] = df["recommended_action"].map(ACTION_ORDER).fillna(9)
        return df.sort_values(
            ["priority_rank", "action_rank", "severity_score"],
            ascending=[True, True, False],
        )

    @cached_property
    def daily_sales(self) -> pd.DataFrame:
        return pd.read_parquet(self._require("daily_sales_tail.parquet"))

    @cached_property
    def weekly_context(self) -> pd.DataFrame:
        return pd.read_parquet(self._require("weekly_context.parquet"))

    @cached_property
    def prep_summary(self) -> dict[str, Any]:
        path = self._require("prep_summary.json")
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        return data[0] if data else {}

    def overview(self) -> dict[str, Any]:
        df = self.signals
        priorities = df["priority"].value_counts().to_dict()
        actions = df["recommended_action"].value_counts().head(6).to_dict()
        return {
            "total_item_store_rows": int(len(df)),
            "priorities": {key: int(priorities.get(key, 0)) for key in ["high", "medium", "low"]},
            "top_actions": {ACTION_LABELS.get(k, k): int(v) for k, v in actions.items()},
            "stores": self.store_options(),
            "prep_summary": self.prep_summary,
        }

    def store_options(self) -> list[dict[str, Any]]:
        counts = self.signals.groupby("store_id").size().reset_index(name="items")
        return counts.sort_values("store_id").to_dict(orient="records")

    def list_priority_recommendations(
        self,
        priority: str = "high",
        page: int = 1,
        page_size: int = 15,
        store_id: str | None = None,
    ) -> dict[str, Any]:
        priority = priority.lower()
        page = max(1, page)
        page_size = min(max(1, page_size), 50)
        df = self.signals[self.signals["priority"].str.lower().eq(priority)]
        if store_id:
            df = df[df["store_id"].eq(store_id)]
        total = int(len(df))
        total_pages = max(1, math.ceil(total / page_size))
        page = min(page, total_pages)
        start = (page - 1) * page_size
        page_df = df.iloc[start : start + page_size]
        return {
            "items": [self._summary(row) for _, row in page_df.iterrows()],
            "priority": priority,
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        }

    def inspect_item_signal(self, item_id: str, store_id: str) -> dict[str, Any]:
        match = self.signals[
            self.signals["item_id"].eq(item_id) & self.signals["store_id"].eq(store_id)
        ]
        if match.empty:
            raise KeyError(f"No item-store signal found for {item_id} at {store_id}.")
        row = match.iloc[0].to_dict()
        row["trend_display"] = TREND_LABELS.get(row["trend_label"], row["trend_label"])
        row["action_display"] = ACTION_LABELS.get(row["recommended_action"], row["recommended_action"])
        row["explanation"] = build_business_explanation(row)
        row["daily_sales"] = self.fetch_item_daily_sales(item_id, store_id)
        row["weekly_context"] = self.fetch_item_weekly_context(item_id, store_id)
        return _clean(row)

    def fetch_item_daily_sales(self, item_id: str, store_id: str) -> list[dict[str, Any]]:
        df = self.daily_sales[
            self.daily_sales["item_id"].eq(item_id) & self.daily_sales["store_id"].eq(store_id)
        ].sort_values("date")
        cols = ["date", "units", "has_event", "snap_day", "weekday"]
        out = df[cols].copy()
        out["date"] = out["date"].dt.strftime("%Y-%m-%d")
        return _clean(out.to_dict(orient="records"))

    def fetch_item_weekly_context(self, item_id: str, store_id: str) -> list[dict[str, Any]]:
        df = self.weekly_context[
            self.weekly_context["item_id"].eq(item_id) & self.weekly_context["store_id"].eq(store_id)
        ].sort_values("wm_yr_wk")
        if df.empty:
            return []
        out = df[
            ["wm_yr_wk", "week_start", "week_end", "units", "sell_price", "event_days", "snap_days"]
        ].copy()
        out["week_start"] = out["week_start"].dt.strftime("%Y-%m-%d")
        out["week_end"] = out["week_end"].dt.strftime("%Y-%m-%d")
        return _clean(out.to_dict(orient="records"))

    def analyze_price_opportunity(self, item_id: str, store_id: str) -> dict[str, Any]:
        row = self.inspect_item_signal(item_id, store_id)
        return {
            "item_id": item_id,
            "store_id": store_id,
            "latest_sell_price": row.get("latest_sell_price"),
            "price_change_12w_pct": row.get("price_change_12w_pct"),
            "price_response_label": row.get("price_response_label"),
            "lower_price_week_avg_units": row.get("lower_price_week_avg_units"),
            "regular_price_week_avg_units": row.get("regular_price_week_avg_units"),
        }

    def _summary(self, row: pd.Series) -> dict[str, Any]:
        data = row.to_dict()
        return _clean(
            {
                "item_id": data["item_id"],
                "store_id": data["store_id"],
                "state_id": data["state_id"],
                "cat_id": data["cat_id"],
                "dept_id": data["dept_id"],
                "priority": data["priority"],
                "trend_label": data["trend_label"],
                "recommended_action": data["recommended_action"],
                "short_reason": data["short_reason"],
                "severity_score": round(float(data["severity_score"]), 2),
            }
        )


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _clean(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


default_repository = RetailSenseRepository()
