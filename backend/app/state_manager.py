# app/state_manager.py
"""
Simple in-memory state manager for conversations.
In production, replace this with a persistent store like Redis or a database.
"""

# call_sid -> conversation_history
CONVERSATION_STATE = {}


def save_state(call_sid: str, history: list):
  """Saves the conversation history for a given call SID."""
  CONVERSATION_STATE[call_sid] = history
  print(f"STATE: Saved state for {call_sid}. History length: {len(history)}")


def load_state(call_sid: str) -> list | None:
  """Loads the conversation history for a given call SID."""
  print(f"STATE: Loaded state for {call_sid}")
  return CONVERSATION_STATE.get(call_sid)


def clear_state(call_sid: str):
  """Clears the state for a completed or failed call."""
  if call_sid in CONVERSATION_STATE:
    del CONVERSATION_STATE[call_sid]
    print(f"STATE: Cleared state for {call_sid}")
