from __future__ import annotations

import os
import asyncio

from retailsense import agent_tools
from retailsense.config import settings


AGENT_INSTRUCTIONS = """
You are RetailSense, a retail inventory decision support agent.
Use the provided tools to retrieve prepared M5 retail facts before answering.
For questions about available stores, totals, queue counts, or overall status,
use the overview or store-list tools. For questions about a specific item-store,
use the item inspection and weekly context tools.
Write concise business language. Do not claim inventory-on-hand, purchase orders,
supplier lead times, or automatic price changes because the M5 demo data does not
contain those fields. Recommendations are human review prompts only.
"""


async def ask_retailsense(question: str, item_id: str | None = None, store_id: str | None = None) -> dict[str, str]:
    if not settings.openai_api_key or not settings.use_openai_agents:
        return {
            "answer": agent_tools.deterministic_answer(question, item_id=item_id, store_id=store_id),
            "mode": "local-fallback",
        }

    try:
        from agents import Agent, Runner, function_tool

        overview_tool = function_tool(agent_tools.get_retail_review_overview)
        stores_tool = function_tool(agent_tools.list_stores)
        list_tool = function_tool(agent_tools.list_priority_recommendations)
        inspect_tool = function_tool(agent_tools.inspect_item_signal)
        weekly_tool = function_tool(agent_tools.fetch_item_weekly_context)
        price_tool = function_tool(agent_tools.analyze_price_opportunity)

        demand_agent = Agent(
            name="Demand Monitoring Agent",
            instructions="Review recent demand, baseline demand, and trend labels from tool facts.",
            model=settings.openai_model,
            tools=[inspect_tool, weekly_tool],
        )
        event_agent = Agent(
            name="Event Context Agent",
            instructions="Review event, weekend, and SNAP context. Do not overstate causality.",
            model=settings.openai_model,
            tools=[inspect_tool, weekly_tool],
        )
        price_agent = Agent(
            name="Price Impact Agent",
            instructions="Review price movement and historical price response from tool facts.",
            model=settings.openai_model,
            tools=[inspect_tool, price_tool],
        )
        orchestrator = Agent(
            name="RetailSense Orchestrator Agent",
            instructions=AGENT_INSTRUCTIONS,
            model=settings.openai_model,
            tools=[overview_tool, stores_tool, list_tool, inspect_tool, weekly_tool, price_tool],
            handoffs=[demand_agent, event_agent, price_agent],
        )

        prompt = question
        if item_id and store_id:
            prompt += f"\nContext item-store: {item_id} at {store_id}."
        result = await asyncio.wait_for(
            Runner.run(orchestrator, prompt),
            timeout=settings.agent_timeout_seconds,
        )
        return {"answer": result.final_output, "mode": "openai-agents-sdk"}
    except Exception as exc:
        if os.getenv("RETAILSENSE_RAISE_AGENT_ERRORS") == "1":
            raise
        answer = agent_tools.deterministic_answer(question, item_id=item_id, store_id=store_id)
        return {
            "answer": f"{answer}\n\nAgent fallback note: OpenAI agent call was unavailable ({exc}).",
            "mode": "local-fallback",
        }
