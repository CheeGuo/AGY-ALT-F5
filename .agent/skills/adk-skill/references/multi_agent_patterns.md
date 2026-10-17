# Multi-Agent Orchestration and Patterns in ADK

ADK supports hierarchical multi-agent architectures, specialist delegation, and the Agent2Agent (A2A) protocol.

## 1. Hierarchical Delegation via `AgentTool`

Wrap a specialized sub-agent in an `AgentTool` so a supervisor/root agent can call it as a tool:

```python
from google.adk.agents.llm_agent import Agent
from google.adk.tools import AgentTool

# 1. Specialized child agent
code_auditor = Agent(
    model="gemini-flash-latest",
    name="code_auditor",
    description="Analyzes Python code for security flaws and performance bottlenecks.",
    instruction="Examine provided code thoroughly and list all vulnerabilities.",
)

# 2. Wrap into AgentTool
auditor_tool = AgentTool(
    agent=code_auditor,
    propagate_grounding_metadata=True,  # Keeps citations/grounding intact up to root
    skip_summarization=False,           # Summarize sub-agent output before returning to root
    include_plugins=True,               # Inherit tracing and telemetry plugins from parent runner
)

# 3. Root coordinator
root_agent = Agent(
    model="gemini-flash-latest",
    name="tech_lead",
    description="Coordinates engineering analysis and review.",
    instruction="Delegate deep security and performance audits to 'code_auditor'.",
    tools=[auditor_tool],
)
```

## 2. Key Parameters of `AgentTool`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `agent` | `Agent` | Required | The child agent instance to execute. |
| `propagate_grounding_metadata` | `bool` | `False` | Forwards citations, grounding metadata, and search sources up to the parent session state. |
| `skip_summarization` | `bool` | `False` | If `True`, returns raw agent response without extra summarization step. |
| `include_plugins` | `bool` | `True` | If `False`, isolates the sub-agent from parent plugins (traces, telemetry). |

## 3. Agent2Agent (A2A) Protocol

ADK supports cross-agent communication protocols enabling agents across distributed systems or different runtimes to collaborate using standard A2A envelopes and event streaming.
See `references/llms-full.txt` (section: "ADK with Agent2Agent (A2A) Protocol") for quickstart consuming and exposing A2A endpoints in Python.
