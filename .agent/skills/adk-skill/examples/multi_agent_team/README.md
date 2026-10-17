# Multi-Agent Orchestration Team

Demonstrates:
- Multiple specialized `Agent` instances
- Wrapping child agents using `AgentTool`
- Configuring `propagate_grounding_metadata=True`
- Configuring `skip_summarization=True`
- Coordination and delegation workflows

## Testing in ADK Web
ADK Web provides a visual trace diagram of sub-agent calls:
```bash
adk web --port 8000
```
Open `http://localhost:8000`, select `project_lead`, and ask:
> *"Explain how quantum computing affects modern cryptography and summarize key recommendations."*
Observe the execution graph as `project_lead` calls `tech_researcher`, then invokes `exec_summarizer`.
