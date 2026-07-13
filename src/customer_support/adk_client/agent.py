"""Google ADK agent connected to the Customer Support MCP server over HTTP."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.agents.context import Context
from google.adk.models.llm_response import LlmResponse
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.mcp_tool import MCPToolset, StreamableHTTPConnectionParams
from google.genai import types

from customer_support.adk_client.prompts import CUSTOMER_SUPPORT_AGENT_INSTRUCTION
from phoenix.otel import register


load_dotenv()

GPT_OSS_API_BASE = "http://10.0.10.51:8000/v1"
GPT_OSS_MODEL = "openai/openai/gpt-oss-20b"
OPENAI_MODEL = "openai/gpt-4o-mini"
CUSTOMER_SUPPORT_MCP_URL = "http://127.0.0.1:9000/mcp"

MCP_TOOL_NAMES = [
    "lookup_customer",
    "lookup_order",
    "add_store_credit",
    "refund_payment",
    "get_audit_logs",
]


def get_mcp_tool() -> MCPToolset:
    """Create the MCP toolset using the notebook's Streamable HTTP pattern."""
    return MCPToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=CUSTOMER_SUPPORT_MCP_URL,
            timeout=10.0,
            sse_read_timeout=300.0,
        ),
        tool_filter=MCP_TOOL_NAMES,
    )


def sanitize_gpt_oss_tool_names(
    callback_context: Context, llm_response: LlmResponse, **_kwargs: object
) -> LlmResponse | None:
    """Strip GPT OSS Harmony channel suffixes from ADK tool-call names."""
    if not llm_response.content or not llm_response.content.parts:
        return None

    changed = False
    valid_tool_names = set(MCP_TOOL_NAMES)
    for part in llm_response.content.parts:
        function_call = getattr(part, "function_call", None)
        if not function_call or not function_call.name:
            continue

        clean_name = function_call.name.split("<|channel|>", maxsplit=1)[0]
        if clean_name != function_call.name and clean_name in valid_tool_names:
            function_call.name = clean_name
            changed = True

    return llm_response if changed else None


def has_openai_key() -> bool:
    """Return True when a real OpenAI API key is configured."""
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def get_model(model: str | None = None) -> LiteLlm:
    """Use GPT-4o mini when OPENAI_API_KEY is set; otherwise use local GPT OSS."""
    if has_openai_key():
        return LiteLlm(
            model=model or OPENAI_MODEL,
            api_key=os.environ["OPENAI_API_KEY"],
        )

    return LiteLlm(
        model=model or GPT_OSS_MODEL,
        api_base=GPT_OSS_API_BASE,
        api_key="not-needed",
    )

# Configure the Phoenix tracer
tracer_provider = register(
  project_name="mcp-customer-support-demo", # Default is 'default'
  auto_instrument=True # Auto-instrument your app based on installed OI dependencies
)

root_agent = LlmAgent(
    name="customer_support_mcp_agent",
    model=get_model(),
    description="Customer support agent that resolves return issues through MCP tools.",
    instruction=CUSTOMER_SUPPORT_AGENT_INSTRUCTION,
    tools=[get_mcp_tool()],
    generate_content_config=types.GenerateContentConfig(temperature=0.0),
    after_model_callback=sanitize_gpt_oss_tool_names,
    output_key="customer_support_response",
)
