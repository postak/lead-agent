"""This module defines the ADK-compliant Tool for telephony actions."""

from absl import logging


def conclude_call(final_statement: str) -> None:
  """Ends the live phone call with a polite final statement.

  Args:
      final_statement: The last thing the agent should say before hanging up.
  """
  del final_statement  # Unused.
  logging.info("TOOL: The LLM has formed the intent to call 'conclude_call'.")
