"""
Multi-Agent Orchestration Example: Research and Executive Summary Team
Demonstrates hierarchical delegation using AgentTool with grounding metadata propagation.
"""

from google.adk.agents.llm_agent import Agent
from google.adk.tools import AgentTool


# 1. Specialist: Technical Researcher
researcher = Agent(
    model="gemini-flash-latest",
    name="tech_researcher",
    description="Researches complex software engineering and architectural topics.",
    instruction=(
        "You are an expert technical researcher. "
        "Provide thorough, technical breakdowns citing specific tools and trade-offs."
    ),
)

# 2. Specialist: Executive Summarizer
summarizer = Agent(
    model="gemini-flash-latest",
    name="exec_summarizer",
    description="Translates complex technical findings into concise executive bullet points.",
    instruction=(
        "You are an executive summarizer. "
        "Take detailed technical input and distill it into 3-5 high-impact bullet points."
    ),
)

# 3. Wrap specialists into AgentTools
research_tool = AgentTool(
    agent=researcher,
    propagate_grounding_metadata=True,  # Ensure citations bubble up
)

summary_tool = AgentTool(
    agent=summarizer,
    skip_summarization=True,  # Output from summarizer is already concise
)

# 4. Lead Coordinator Agent
root_agent = Agent(
    model="gemini-flash-latest",
    name="project_lead",
    description="Coordinates research and executive briefing for engineering leadership.",
    instruction=(
        "You are the project lead. When asked about complex technical concepts, "
        "first delegate to 'tech_researcher' to gather facts. "
        "Then pass those findings to 'exec_summarizer' to produce the final briefing. "
        "Deliver the synthesized output to the user."
    ),
    tools=[research_tool, summary_tool],
)
