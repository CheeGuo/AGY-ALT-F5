# MCP-Integrated ADK Agent

Demonstrates:
- Dynamic environment selection (`K_SERVICE` for Cloud Run vs Stdio for local dev)
- Tool filtering to limit exposed actions
- Stateful function tools using `ToolContext`

## Local Run
Ensure Node.js is installed (for `@modelcontextprotocol/server-filesystem` via `npx`):
```bash
adk run tools_and_mcp_agent
```
