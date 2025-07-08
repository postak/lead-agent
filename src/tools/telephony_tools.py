"""This module defines the ADK-compliant Tool for telephony actions."""

import logging

async def conclude_call(final_statement: str) -> dict[str, str]:
  """Creates a signal for the program to end the live phone call.

  This function does not actually end the call, but when the agent
  invokes this function the program triggers the phone call
  termination outside of the agent context.

  Args:
      final_statement: The last thing the agent should say before hanging up.

  Returns:
    The status of the function execution.
  """
  logging.info(
      "TOOL: The LLM has formed the intent to call "
      " 'conclude_call' with final statement %s.",
      final_statement,
  )
  return {"status": "success"}
