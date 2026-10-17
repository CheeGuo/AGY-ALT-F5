"""
ADK Agent Manifest Template
Canonical starting template for developing agents with Google Agent Development Kit.
"""

import os
from google.adk.agents.llm_agent import Agent
from google.adk.tools.tool_context import ToolContext

# --- Tool Definitions ---

def sample_tool(param1: str, context: ToolContext) -> dict:
    """Describe what this tool does clearly.

    Args:
        param1: Explanation of this parameter.
        context: Automatically injected session and state context (hidden from LLM).
    """
    # Optional state access / mutation
    context.state["temp:last_param"] = param1
    return {
        "status": "success",
        "result": f"Processed {param1}",
    }


# --- Root Agent Definition ---
# The runtime requires an exported variable named 'root_agent'

root_agent = Agent(
    model="gemini-flash-latest",
    name="starter_agent",
    description="A concise summary of agent purpose.",
    instruction=(
        "You are an AI assistant built with Google ADK. "
        "Use the tools provided to answer user queries accurately."
    ),
    tools=[sample_tool],
)
