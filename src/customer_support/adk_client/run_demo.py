"""Run Google ADK + MCP customer support demo scenarios with Phoenix tracing."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from phoenix.otel import register

from customer_support.adk_client.agent import get_mcp_tool, root_agent

DEMO_CUSTOMER_ID = "cust_1001"
DEMO_ORDER_ID = "ord_5001"
PHOENIX_PROJECT_NAME = "mcp-customer-support-demo"


def init_phoenix() -> None:
    """Enable Phoenix/OpenInference tracing with Phoenix-aware defaults."""
    register(project_name=PHOENIX_PROJECT_NAME, batch=True, auto_instrument=True)


def payload(result: dict[str, Any]) -> Any:
    """Extract concise structured output from an ADK MCP tool result."""
    structured = result.get("structuredContent", result)
    if isinstance(structured, dict) and set(structured) == {"result"}:
        return structured["result"]
    return structured


def print_section(title: str) -> None:
    print(f"\n=== {title} ===")


def part_to_dict(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True, mode="json")
    return value


def make_tool_context(name: str) -> SimpleNamespace:
    """Minimal context for direct MCP tool calls in the retry demo."""
    return SimpleNamespace(
        tool_confirmation=None,
        _invocation_context=None,
        function_call_id=f"demo-{name}",
        request_confirmation=lambda **_: None,
        render_ui_widget=lambda *_args, **_kwargs: None,
    )


async def call_mcp_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Call one MCP tool through ADK's MCP toolset."""
    toolset = get_mcp_tool()
    try:
        tools = {tool.name: tool for tool in await toolset.get_tools()}
        return await tools[name].run_async(
            args=args,
            tool_context=make_tool_context(name),
        )
    finally:
        await toolset.close()


async def print_audit_logs() -> None:
    logs = payload(await call_mcp_tool("get_audit_logs", {}))
    print("Audit logs:")
    for entry in logs:
        print(f"- {entry['action']} {entry['request_id']} {entry['status']} ${entry['amount']}")


async def run_agent_scenario(
    *,
    session_id: str,
    user_query: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Run the real ADK agent and collect final text plus tool results."""
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name="customer_support_demo",
        user_id="demo_user",
        session_id=session_id,
    )
    runner = Runner(
        agent=root_agent,
        app_name="customer_support_demo",
        session_service=session_service,
    )
    message = types.Content(
        role="user",
        parts=[
            types.Part(
                text=(
                    f"{user_query}\n\n"
                    "Demo context for this customer interaction: "
                    f"customer_id={DEMO_CUSTOMER_ID}, order_id={DEMO_ORDER_ID}."
                )
            )
        ],
    )

    final_response = ""
    tool_results: list[dict[str, Any]] = []
    async for event in runner.run_async(
        user_id="demo_user",
        session_id=session_id,
        new_message=message,
    ):
        if not event.content or not event.content.parts:
            continue
        for part in event.content.parts:
            if getattr(part, "function_call", None):
                call = part.function_call
                tool_results.append(
                    {
                        "type": "call",
                        "name": call.name,
                        "args": part_to_dict(call.args),
                    }
                )
            if getattr(part, "function_response", None):
                response = part.function_response
                tool_results.append(
                    {
                        "type": "response",
                        "name": response.name,
                        "response": part_to_dict(response.response),
                    }
                )
        if event.is_final_response():
            final_response = "".join(
                part.text or ""
                for part in event.content.parts
                if getattr(part, "text", None)
            ).strip()

    return final_response, tool_results


def print_tool_results(tool_results: list[dict[str, Any]]) -> None:
    print("Relevant tool/action results:")
    for item in tool_results:
        if item["type"] == "call":
            print(f"- call {item['name']}: {item['args']}")
        else:
            print(f"- result {item['name']}: {item['response']}")


async def scenario_store_credit() -> None:
    user_query = "My headphones are broken. I want to return them."
    print_section("Scenario 1: Store Credit First")
    print(f"User query: {user_query}")

    final_response, tool_results = await run_agent_scenario(
        session_id="scenario_store_credit",
        user_query=user_query,
    )

    print(f"Agent final response: {final_response}")
    print_tool_results(tool_results)
    await print_audit_logs()


async def scenario_refund() -> None:
    user_query = "My headphones are broken. I want my money back."
    print_section("Scenario 2: Explicit Refund Request")
    print(f"User query: {user_query}")

    final_response, tool_results = await run_agent_scenario(
        session_id="scenario_refund",
        user_query=user_query,
    )

    print(f"Agent final response: {final_response}")
    print_tool_results(tool_results)
    await print_audit_logs()


async def scenario_idempotent_retry() -> None:
    print_section("Scenario 3: Idempotent Refund Retry")
    request_id = str(uuid4())
    request = {
        "request": {
            "request_id": request_id,
            "customer_id": DEMO_CUSTOMER_ID,
            "order_id": DEMO_ORDER_ID,
            "amount": 15.0,
            "reason": "Retry safety demonstration.",
        }
    }

    first = payload(await call_mcp_tool("refund_payment", request))
    second = payload(await call_mcp_tool("refund_payment", request))

    print(f"User query: Please retry my refund request. request_id={request_id}")
    print(f"First refund_payment result: {first}")
    print(f"Second refund_payment result: {second}")
    print(f"Tool/action result: duplicate response reused = {first == second}")
    print(
        "Agent final response: I retried the refund safely with the same request "
        "ID, and no duplicate refund was created."
    )
    await print_audit_logs()


async def main() -> None:
    init_phoenix()
    await scenario_store_credit()
    await scenario_refund()
    await scenario_idempotent_retry()


if __name__ == "__main__":
    asyncio.run(main())
