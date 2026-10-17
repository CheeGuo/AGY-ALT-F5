#!/usr/bin/env python3
"""
ADK Agent Project Scaffolder
Creates starter ADK agent directories and boilerplates according to Google ADK patterns.

Usage:
    py ./scripts/scaffold_agent.py --name my_agent --type basic
    py ./scripts/scaffold_agent.py --name maps_agent --type mcp
    py ./scripts/scaffold_agent.py --name team_agent --type multi-agent
"""

import argparse
import sys
from pathlib import Path

BASIC_AGENT_CODE = '''"""
{name} - Google Agent Development Kit (ADK) Agent
"""
import os
from google.adk.agents.llm_agent import Agent

# Tool definition with type hints and docstring (ADK reads docstrings for tool parameters)
def get_status(service_name: str) -> dict:
    """Returns the operational status of a given internal service.

    Args:
        service_name: The identifier of the service to inspect.
    """
    return {"service": service_name, "status": "healthy", "latency_ms": 24}


root_agent = Agent(
    model="gemini-flash-latest",
    name="{name}",
    description="A helpful assistant capable of monitoring service health.",
    instruction="You are a helpful monitoring assistant. Use the 'get_status' tool when users inquire about service health.",
    tools=[get_status],
)
'''

MCP_AGENT_CODE = '''"""
{name} - ADK Agent with Model Context Protocol (MCP) Integration
"""
import os
from google.adk.agents.llm_agent import Agent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

# Initialize MCP Toolset (e.g., local subprocess or Streamable HTTP in production)
mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "./data"],
        ),
        timeout=10,
    )
)

root_agent = Agent(
    model="gemini-flash-latest",
    name="{name}",
    description="An agent equipped with MCP tools for filesystem access.",
    instruction="Assist users with file management and analysis using the provided MCP tools.",
    tools=[mcp_toolset],
)
'''

MULTI_AGENT_CODE = '''"""
{name} - ADK Multi-Agent Coordinator Team
"""
from google.adk.agents.llm_agent import Agent
from google.adk.tools import AgentTool

# Specialized Sub-Agent 1: Research Specialist
research_agent = Agent(
    model="gemini-flash-latest",
    name="research_specialist",
    description="Researches topics in detail and provides comprehensive facts.",
    instruction="You are a deep-dive research specialist. Provide structured factual information.",
)

# Specialized Sub-Agent 2: Summarization Specialist
summary_agent = Agent(
    model="gemini-flash-latest",
    name="summary_specialist",
    description="Synthesizes and distills complex material into brief executive summaries.",
    instruction="Summarize provided findings into clear, concise key takeaways.",
)

# Wrap sub-agents into AgentTools with metadata propagation
research_tool = AgentTool(
    agent=research_agent,
    propagate_grounding_metadata=True,
)
summary_tool = AgentTool(
    agent=summary_agent,
    skip_summarization=False,
)

# Central Coordinator Root Agent
root_agent = Agent(
    model="gemini-flash-latest",
    name="{name}",
    description="Coordinator managing research and executive synthesis tasks.",
    instruction=(
        "You are the lead coordinator. When asked to research a topic, delegate to "
        "'research_specialist'. When asked to condense or format conclusions, use 'summary_specialist'."
    ),
    tools=[research_tool, summary_tool],
)
'''

ENV_TEMPLATE = '''# Google Gemini API Key (get from https://aistudio.google.com/app/apikey)
GOOGLE_API_KEY="YOUR_GEMINI_API_KEY"

# Or configure Google Cloud Vertex AI:
# GOOGLE_GENAI_USE_VERTEXAI="TRUE"
# GOOGLE_CLOUD_PROJECT="your-project-id"
# GOOGLE_CLOUD_LOCATION="us-central1"
'''

README_TEMPLATE = """# {name}

Built with [Google Agent Development Kit (ADK)](https://adk.dev/).

## Prerequisites
- Python 3.10+
- `pip install google-adk`

## Setup
1. Copy `.env.example` to `.env` and configure `GOOGLE_API_KEY`.
2. Run the agent via CLI:
   ```bash
   adk run {name}
   ```
3. Or launch the web inspection interface:
   ```bash
   adk web --port 8000
   ```
"""


def scaffold(name: str, agent_type: str, output_dir: Path) -> Path:
    target_dir = output_dir / name
    target_dir.mkdir(parents=True, exist_ok=True)

    if agent_type == "mcp":
        code = MCP_AGENT_CODE.format(name=name)
    elif agent_type == "multi-agent":
        code = MULTI_AGENT_CODE.format(name=name)
    else:
        code = BASIC_AGENT_CODE.format(name=name)

    (target_dir / "agent.py").write_text(code, encoding="utf-8")
    (target_dir / "__init__.py").write_text('"""Agent package initialization."""\\n', encoding="utf-8")
    (target_dir / ".env.example").write_text(ENV_TEMPLATE, encoding="utf-8")
    (target_dir / "README.md").write_text(README_TEMPLATE.format(name=name), encoding="utf-8")

    print(f"[+] Scaffolding complete for '{name}' (type: {agent_type}) at {target_dir}")
    print(f"    - agent.py")
    print(f"    - __init__.py")
    print(f"    - .env.example")
    print(f"    - README.md")
    return target_dir


def main():
    parser = argparse.ArgumentParser(
        description="Scaffold a new Google Agent Development Kit (ADK) agent project.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--name", required=True, help="Agent folder name and root agent identifier")
    parser.add_argument(
        "--type",
        choices=["basic", "mcp", "multi-agent"],
        default="basic",
        help="Architecture template to scaffold",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Target parent directory where the agent folder will be created",
    )
    args = parser.parse_args()

    scaffold(args.name, args.type, Path(args.output_dir))


if __name__ == "__main__":
    main()
