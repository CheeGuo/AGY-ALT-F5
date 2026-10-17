---
name: adk-skill
description: >-
  Develop, scaffold, inspect, and deploy AI agents using Google Agent Development Kit (ADK / adk-python).
  Use this skill whenever creating or modifying ADK agents, implementing custom function tools,
  integrating Model Context Protocol (MCP) toolsets, architecting multi-agent delegation teams with AgentTool,
  managing session state, or configuring ADK execution runtimes and debugging tools.
---

# Google Agent Development Kit (ADK) Skill

This skill guides the construction, testing, and deployment of production-grade AI agents built with the [Google Agent Development Kit (ADK)](https://adk.dev/).

All documentation in this skill is dynamically synchronized with the official ADK documentation source specified in [google/adk-python llms-full.txt](https://github.com/google/adk-python/blob/main/llms-full.txt).

---

## ⚠️ Mandatory Initialization: Run at Each Start

> [!IMPORTANT]
> **At each start of working with this skill**, you **MUST** run the documentation synchronization script to ensure local reference docs reflect the latest upstream releases and API patterns from the canonical ADK repository.

Execute the updater script using your preferred runtime:

```bash
# Python (recommended, cross-platform)
py ./scripts/update_docs.py
# or: python ./scripts/update_docs.py

# PowerShell (Windows / PowerShell Core)
./scripts/update_docs.ps1

# Bash (Linux / macOS)
./scripts/update_docs.sh
```

The script resolves the canonical pointer from `https://raw.githubusercontent.com/google/adk-python/main/llms-full.txt` (which targets `https://adk.dev/llms-full.txt` and `https://adk.dev/llms.txt`) and downloads updates to [references/llms-full.txt](./references/llms-full.txt) and [references/llms.txt](./references/llms.txt).

---

## Architecture Decision Tree

Use this decision tree to determine the optimal agent structure:

```
Task Requirement
 ├── Simple single-turn question answering
 │    └── Single Agent (`Agent` with instruction and model)
 ├── Dynamic data retrieval / API actions
 │    ├── Custom internal logic or local databases?
 │    │    └── Function Tools (Python functions with typing + docstrings)
 │    └── Existing protocol server (Filesystem, GitHub, Postgres)?
 │         └── MCP Toolset (`McpToolset` via Stdio or Streamable HTTP)
 ├── Multi-step or specialized role segregation
 │    ├── Deep research + executive summary / auditing?
 │    │    └── Multi-Agent Delegation (`AgentTool` wrapping sub-agents)
 │    └── Cross-organization / distributed microservices?
 │         └── Agent2Agent (A2A) Protocol
 └── Stateful conversations
      ├── Temporary within-turn scratchpad?
      │    └── Use `temp:` key prefix in `context.state`
      └── Persistent across sessions?
           └── DatabaseSessionService / VertexAiSessionService
```

---

## Step-by-Step Development Workflow

### Step 1: Synchronize Reference Documentation
Run `./scripts/update_docs.py` as detailed in the mandatory initialization section.

### Step 2: Scaffold Project Structure
To create a standard ADK directory structure, either run the official CLI or use the included scaffolding script:

```bash
# Option A: Using the included reusable scaffolder
py ./scripts/scaffold_agent.py --name my_agent --type basic
# Types available: 'basic', 'mcp', 'multi-agent'

# Option B: Using the official ADK CLI
adk create my_agent
```

An ADK agent package requires:
- `__init__.py`: Package marker.
- `agent.py`: Exports `root_agent` (an instance of `Agent` or `LlmAgent`).
- `.env`: Environment variables (`GOOGLE_API_KEY`, etc.).

### Step 3: Implement Tools
When creating tools for ADK:
1. **Type Annotations**: Always annotate all parameters and the return value.
2. **Detailed Docstring**: ADK parses the docstring to construct parameter schemas for the LLM.
3. **Context Injection**: To access session state or user info, include a parameter with type `ToolContext`. ADK injects it automatically without exposing it in the model's tool schema.

```python
from google.adk.tools.tool_context import ToolContext

def calculate_quote(item_id: str, quantity: int, context: ToolContext) -> dict:
    """Calculates total price quote for items.

    Args:
        item_id: Unique inventory identifier.
        quantity: Number of units requested.
    """
    # Safe state mutation
    context.state["temp:last_item"] = item_id
    return {"item_id": item_id, "total_price": quantity * 25.0}
```

### Step 4: Configure MCP Toolsets
For MCP integration, configure environment-aware transports:
- **Local Development**: `StdioConnectionParams` launching subprocesses.
- **Production / Cloud Run**: `StreamableHTTPConnectionParams` with bearer token auth.
- **Scoping**: Always specify `tool_filter=[...]` on `McpToolset` to minimize model prompt surface.

See [references/tools_and_mcp.md](./references/tools_and_mcp.md) for complete snippets.

### Step 5: Multi-Agent Teams with `AgentTool`
To delegate to specialized sub-agents:
1. Define specialized sub-agents with narrow instructions.
2. Wrap each sub-agent in an `AgentTool`.
3. Set `propagate_grounding_metadata=True` if citations from search tools should bubble up to the user.
4. Pass the `AgentTool` instances to the parent coordinator's `tools=[...]`.

See [examples/multi_agent_team/agent.py](./examples/multi_agent_team/agent.py).

### Step 6: Test and Debug
Interact with the agent during development:

```bash
# Interactive CLI session
adk run my_agent

# Visual web debugger (inspect call stacks, tool execution, and session state)
adk web --port 8000
```

> [!TIP]
> Run `adk web` from the **parent directory** containing the agent package folder.

---

## State Management Rules

1. **Never directly modify `session.state` outside of managed contexts.** Direct mutation like `session.state['k'] = v` bypasses event logging and fails to persist in databases.
2. **Mutate state within `ToolContext` or `CallbackContext`**:
   - `context.state["key"] = value` automatically generates a `state_delta` on the event.
3. **Use standard key prefixes**:
   - `temp:`: Ephemeral in-memory state for intermediate calculations.
   - `user:`: User profile state persisting across sessions.
   - `app:`: Shared application-level state.
   - No prefix: Standard persistent session state.

See [references/state_and_sessions.md](./references/state_and_sessions.md) for details.

---

## Executable Helper Scripts

Encapsulate operational commands using the helper scripts in `./scripts/`. Run with `--help` for available arguments:

- **[scripts/update_docs.py](./scripts/update_docs.py)**: Updates `llms-full.txt` and `llms.txt` from canonical repo pointer.
- **[scripts/scaffold_agent.py](./scripts/scaffold_agent.py)**: Generates starter agent project templates.
- **[scripts/update_docs.ps1](./scripts/update_docs.ps1)**: PowerShell updater.
- **[scripts/update_docs.sh](./scripts/update_docs.sh)**: Bash updater.

---

## Included Reference Materials

- **[references/llms-full.txt](./references/llms-full.txt)**: Full upstream documentation generated by ADK.
- **[references/llms.txt](./references/llms.txt)**: Index of all documentation topics and URLs.
- **[references/quickstart.md](./references/quickstart.md)**: Fast-track agent setup guide.
- **[references/tools_and_mcp.md](./references/tools_and_mcp.md)**: Function tools, MCP toolsets, and transports.
- **[references/state_and_sessions.md](./references/state_and_sessions.md)**: Session services, state prefixes, and event deltas.
- **[references/multi_agent_patterns.md](./references/multi_agent_patterns.md)**: Sub-agents, `AgentTool`, and A2A.

## Ready-to-Run Examples

- **[examples/basic_agent/](./examples/basic_agent/)**: Single agent with custom typed tools.
- **[examples/tools_and_mcp_agent/](./examples/tools_and_mcp_agent/)**: Hybrid agent combining stateful tools and MCP server.
- **[examples/multi_agent_team/](./examples/multi_agent_team/)**: Hierarchical coordinator and specialist agents.

## Starter Templates & Configs

- **[resources/env.template](./resources/env.template)**: Environment configuration for Gemini API and Vertex AI.
- **[resources/agent_manifest_template.py](./resources/agent_manifest_template.py)**: Clean starter template.
- **[resources/mcp_config.example.json](./resources/mcp_config.example.json)**: MCP server configuration for IDE docs lookup.
