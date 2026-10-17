# Tools and Model Context Protocol (MCP) in ADK

ADK supports standard Python function tools, custom tools, and Model Context Protocol (MCP) server integrations.

## 1. Function Tools

Functions passed to `tools=[...]` must adhere to:
- **Type Annotations**: Explicit type hints on arguments and return types.
- **Docstrings**: Formatted docstrings explaining the purpose of the tool and each parameter. ADK parses these directly to construct the model's tool schema.
- **Context Injection**: If the function needs access to session state or agent context, declare a parameter of type `ToolContext`. ADK injects it automatically without exposing it to the LLM.

```python
from google.adk.tools.tool_context import ToolContext

def search_database(query: str, context: ToolContext, limit: int = 5) -> dict:
    """Searches the database for matching articles.

    Args:
        query: The search keywords.
        limit: Maximum results to return.
    """
    # Context access
    user_id = context.session.user_id
    # State update
    context.state["temp:last_query"] = query
    return {"results": [{"id": 1, "title": f"Result for {query}"}]}
```

## 2. MCP Tools (`McpToolset`)

ADK integrates seamlessly with Model Context Protocol (MCP) servers using `McpToolset`.

### Local Stdio Subprocess (Development)
```python
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

filesystem_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "./workspace"],
        ),
        timeout=10,
    ),
    tool_filter=["read_file", "list_directory"],  # Expose only needed actions
)
```

### Remote Streamable HTTP / SSE (Production / Cloud Run)
```python
import os
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

mcp_toolset = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url="https://api.example.com/mcp",
        headers={
            "Authorization": f"Bearer {os.getenv('MCP_AUTH_TOKEN')}",
            "Content-Type": "application/json",
        },
        timeout=5,
        sse_read_timeout=300,
    )
)
```

### Dynamic Environment Detection Pattern
```python
import os
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StdioConnectionParams,
    StreamableHTTPConnectionParams,
)
from mcp import StdioServerParameters

if os.getenv("K_SERVICE"):
    # Running in Cloud Run / container
    toolset = McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=os.getenv("REMOTE_MCP_URL"),
            headers={"Authorization": f"Bearer {os.getenv('MCP_AUTH_TOKEN')}"},
        )
    )
else:
    # Local dev via stdio
    toolset = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem", "./data"],
            )
        )
    )
```

## 3. Accessing MCP Resources

MCP servers can expose read-only data resources (files, documents, db tables):
- Enable `use_mcp_resources=True` on `McpToolset` to equip the agent with `LoadMcpResourceTool` dynamically.
- Programmatically list and read resources:
  ```python
  resources = await toolset.list_resources()
  content = await toolset.read_resource(resources[0])
  ```
