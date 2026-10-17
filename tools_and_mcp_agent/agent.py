"""
ADK Agent Example with Model Context Protocol (MCP) Integration
Demonstrates environment-aware MCP configuration and stateful tool interactions.
"""

import os
from google.adk.agents.llm_agent import Agent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StdioConnectionParams,
    StreamableHTTPConnectionParams,
)
from google.adk.tools.tool_context import ToolContext
from mcp import StdioServerParameters


# Custom helper function tool that tracks execution count in session state
def log_user_action(action_name: str, context: ToolContext) -> dict:
    """Logs user actions into session state with timestamp.

    Args:
        action_name: Description of the action taken.
    """
    count = context.state.get("action_count", 0) + 1
    context.state["action_count"] = count
    context.state["temp:last_action"] = action_name
    return {"status": "logged", "total_actions": count}


# Configure MCP Toolset based on deployment environment
if os.getenv("K_SERVICE"):
    # Running in Cloud Run / container: use Streamable HTTP
    mcp_toolset = McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=os.getenv("REMOTE_MCP_URL", "https://api.example.com/mcp"),
            headers={"Authorization": f"Bearer {os.getenv('MCP_AUTH_TOKEN', '')}"},
            timeout=5,
            sse_read_timeout=300,
        )
    )
else:
    # Running in Local Dev: use stdio subprocess
    mcp_toolset = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem", "./data"],
            ),
            timeout=10,
        ),
        tool_filter=["read_file", "list_directory"],
    )

root_agent = Agent(
    model="gemini-flash-latest",
    name="filesystem_assistant",
    description="Inspects files using MCP and tracks interaction history.",
    instruction=(
        "You are an assistant with filesystem inspection capabilities via MCP. "
        "Log important user actions with 'log_user_action'. "
        "Use MCP file tools to list or read files when requested."
    ),
    tools=[mcp_toolset, log_user_action],
)
