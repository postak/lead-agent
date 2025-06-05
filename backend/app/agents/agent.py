"""Defines the ADK-native Agent for lead qualification."""

import os
from absl import logging

from google.adk import agents

from app.tools import lead_tools
from app.tools import telephony_tools


_MODEL = "gemini-2.0-flash-exp"  # "gemini-2.0-flash-live-001"


def load_prompt_from_file() -> str:
  """Loads the agent's system prompt from the text file."""
  try:
    prompt_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "prompts",
        "qualification_agent_prompt.txt",
    )
    with open(prompt_path, "r") as f:
      return f.read()
  except FileNotFoundError:
    logging.error("AGENT: Prompt file not found. Using a default prompt.")
    return "You are a helpful assistant."


root_agent = agents.Agent(
    name="Alex",
    description=(
        "A conversational agent that qualifies leads over the phone by asking"
        " questions based on the BANT framework."
    ),
    model=_MODEL,
    instruction=load_prompt_from_file(),
    tools=[
        lead_tools.build_lead_quality_record,
        telephony_tools.conclude_call,
    ],
)

logging.info("AGENT: Declarative LlmAgent '%s' defined.", root_agent.name)
