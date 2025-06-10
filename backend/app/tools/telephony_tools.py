"""
This module defines the ADK-compliant Tool for telephony actions.
It serves as a schema for the LlmAgent's reasoning. The methods here
are NOT executed directly by the Runner in this architecture; instead,
the workflow intercepts the agent's intent to use them.
"""

from absl import logging


def conclude_call(final_statement: str) -> None:
  """Ends the live phone call with a polite final statement.

  Args:
      final_statement: The last thing the agent should say before hanging up.

  Returns:
      A string indicating that the call hangup process will be initiated.
  """
  logging.info("TOOL: The LLM has formed the intent to call 'conclude_call'.")
