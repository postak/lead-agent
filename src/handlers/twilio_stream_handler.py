"""Manages a single Twilio Media Stream WebSocket connection and conversation."""

import asyncio
from contextlib import suppress  # For ignoring CancelledError during cleanup
import json
from typing import Any, AsyncIterable

import base64
import logging
import fastapi
from google.adk import agents
from google.adk import runners
from google.adk import sessions
from google.adk.agents import run_config as run_config_lib
from google.adk.events import event as event_lib
from google.genai import types
from src.config import settings
from src.core import utils
from src.services import telephony_service as telephony_service_lib


InMemoryRunner = runners.InMemoryRunner
Event = event_lib.Event
RunConfig = run_config_lib.RunConfig
StreamingMode = run_config_lib.StreamingMode
LiveRequestQueue = agents.LiveRequestQueue
WebSocket = fastapi.WebSocket
WebSocketDisconnect = fastapi.WebSocketDisconnect
AgentSession = sessions.Session
TelephonyService = telephony_service_lib.TwilioTelephonyService

_SPEECH_CONFIG = types.SpeechConfig(
    voice_config=types.VoiceConfig(
        # Puck, Charon, Kore, Fenrir, Aoede, Leda, Orus, and Zephyr
        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
    )
)

_RUN_CONFIG = RunConfig(
    streaming_mode=StreamingMode.BIDI,
    response_modalities=["AUDIO"],
    speech_config=_SPEECH_CONFIG,
    realtime_input_config=types.RealtimeInputConfig(
      automatic_activity_detection=types.AutomaticActivityDetection(
          disabled=False,
          start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
          end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
          prefix_padding_ms=20,
          silence_duration_ms=100,
      )),
    output_audio_transcription=types.AudioTranscriptionConfig(),
    input_audio_transcription=types.AudioTranscriptionConfig(),
)


class TwilioAgentStream:
  """Manages a single Twilio Media Stream WebSocket connection and conversation."""

  def __init__(
      self,
      websocket: WebSocket,
      agent_runner: InMemoryRunner,
      telephony_service: TelephonyService,
  ):
    """Initialize the handler with the WebSocket and agent runner."""
    self.websocket = websocket
    self.agent_runner = agent_runner
    self.app_name = settings.APP_NAME
    self.telephony_service = telephony_service

    self.initial_prompt_sent_to_agent = False
    self.terminate_call = False

    self.lead_info: dict[str, Any] = {}
    self.stream_sid: str = ""
    self.call_sid: str = ""
    self.agent_session: AgentSession | None = None
    self.live_events: AsyncIterable[Event | None] | None = None
    self.live_request_queue: LiveRequestQueue | None = None
    logging.info("TwilioStreamHandler initialized.")

  async def _get_managed_agent_session(self, session_id: str) -> AgentSession:
    """Retrieves the session.

    Args:
      session_id: The session ID.

    Returns:
      A Session object.
    """
    managed_session = await self.agent_runner.session_service.get_session(
        session_id=session_id, app_name=self.app_name, user_id=session_id
    )
    if managed_session:
      return managed_session

    return await self.agent_runner.session_service.create_session(
        session_id=session_id,
        app_name=self.app_name,
        user_id=session_id,
    )

  async def start_agent_session(
      self,
      session_id: str,
  ) -> None:
    """Starts a live, streaming agent session for a given session_id.

    Args:
      session_id: The session ID to start the agent session for.

    Returns:
      A tuple containing the live events stream and the request queue.
    """
    session = await self._get_managed_agent_session(session_id=session_id)
    self.live_request_queue = LiveRequestQueue()
    self.live_events = self.agent_runner.run_live(
        session=session,
        live_request_queue=self.live_request_queue,
        run_config=_RUN_CONFIG,
    )
    logging.info("AGENT: Agent is running...")

  def _terminate_call_after_turn(self, event: Event) -> bool:
    """Check if the agent requested to terminate the call."""
    tool_calls = event.get_function_calls()
    if event.actions and tool_calls:
      for tool_call in tool_calls:
        logging.info("AGENT: called tool: %s", tool_call.name)
        if tool_call.name == "conclude_call":
          self.terminate_call = True

  async def agent_to_twilio_messaging(
      self,
  ) -> None:
    """Messages the agent's responses to Twilio."""
    logging.debug(
        "AGENT->TWILIO: Messaging task started for stream %s (CallSid: %s)",
        self.stream_sid,
        self.call_sid,
    )

    turn_counter: int = 0

    try:
      while True:
        async for event in self.live_events:
          self._terminate_call_after_turn(event)
          if event.turn_complete:
            if self.terminate_call:
              logging.info(
                  "AGENT->TWILIO: Terminating call %s as per agent's request"
                  " (conclude_call).",
                  self.call_sid,
              )
              await self.telephony_service.end_call(self.call_sid)
              await self.websocket.close(
                  code=1000, reason="Agent ended call via tool"
              )
              break

            message = {
                "event": "mark",
                "streamSid": self.stream_sid,
                "mark": {"name": f"turn_{turn_counter}_complete"},
            }
            await self.websocket.send_json(message)
            turn_counter += 1
            logging.info("AGENT->TWILIO: Turn %s complete.", turn_counter)

          if hasattr(event, "interrupted") and event.interrupted:
            message = {
                "event": "clear",
                "streamSid": self.stream_sid,
            }
            logging.info(
                "AGENT->TWILIO: Agent interrupted, clearing stream %s.",
                self.stream_sid,
            )
            await self.websocket.send_json(message)

          part = (
              event.content and event.content.parts and event.content.parts[0]
          )
          if not part or event.author == "user":
            continue            

          is_audio = part.inline_data and part.inline_data.mime_type.startswith(
              "audio/pcm"
          )
          if is_audio:
            pcm_audio_data_bytes = part.inline_data and part.inline_data.data
            mulaw_audio = utils.convert_pcm_audio_to_mulaw(pcm_audio_data_bytes)
            # Send the μ-law audio to Twilio
            message = {
                "event": "media",
                "streamSid": self.stream_sid,
                "media": {"payload": mulaw_audio},
            }
            await self.websocket.send_json(message)
            logging.debug(
                "AGENT->TWILIO: Sent %d bytes of agent audio (8kHz μ-law) to"
                " stream %s.",
                len(mulaw_audio),
                self.stream_sid,
            )

    except Exception as e:  # pylint: disable=broad-exception-caught
      logging.exception(
          "Error in agent_to_twilio_messaging for stream %s: %s."
          " Attempting to end call...",
          self.stream_sid,
          e,
      )

  def send_initial_prompt_to_agent(self):
    """Sends the initial prompt to the agent."""
    if not self.initial_prompt_sent_to_agent:
      initial_prompt = (
          "The phone call has just been answered. Your goal is to qualify the"
          f" lead. The lead's info is: {json.dumps(self.lead_info)}. Please"
          f" begin by confirming that you are speaking to {self.lead_info.get('first_name')}."
      )
      content = types.Content(
          role="user", parts=[types.Part.from_text(text=initial_prompt)]
      )
      self.live_request_queue.send_content(content=content)
      self.initial_prompt_sent_to_agent = True
      logging.info(
          "TWILIO->AGENT: Initial prompt sent to agent for CallSid %s.",
          self.call_sid,
      )

  async def twilio_to_agent_messaging(
      self,
  ) -> None:
    """Listens for messages from Twilio and sends them to the agent."""
    logging.debug(
        "TWILIO->AGENT: Messaging listener task started for CallSid %s,"
        " StreamSid %s.",
        self.call_sid,
        self.stream_sid,
    )
    try:
      self.send_initial_prompt_to_agent()
      while True:
        message = await self.websocket.receive_json()
        if not message:
          logging.info("TWILIO->AGENT: Received empty message.")
          continue
        event_type = message.get("event")

        if event_type == "start" or event_type == "connected":
          logging.warning(
              "TWILIO->AGENT: Received unexpected '%s' event after initial"
              " setup for CallSid %s.",
              event_type,
              self.call_sid,
          )

        if event_type == "media":
          payload =  message["media"]["payload"]
          pcm_audio = utils.convert_mulaw_audio_to_pcm(
              payload
          )
          self.live_request_queue.send_realtime(
              types.Blob(data=pcm_audio, mime_type="audio/pcm;rate=24000")
          )

        if event_type in ("stop",  "closed"):
          logging.info(
              "TWILIO->AGENT: Twilio stream stopped or client ended call."
          )
          self.live_request_queue.close()
          break
    except Exception as e:  # pylint: disable=broad-exception-caught
      logging.exception(
          "TWILIO->AGENT: Error in twilio_to_agent_messaging for CallSid"
          " %s: %s",
          self.call_sid,
          e,
      )

  async def manage_stream(self):
    """Main method that manages WebSocket session."""
    try:
      while True:
        initial_message_json = await self.websocket.receive_text()
        message = json.loads(initial_message_json)
        event_type = message.get("event")
        if event_type != "start":
          continue  # Keep running the loop until "start" event.
        self.stream_sid = message["start"]["streamSid"]
        self.call_sid = message["start"]["callSid"]
        custom_params = message["start"].get("customParameters")
        lead_info_str = custom_params.get("lead_info", "")
        self.lead_info = utils.decode_json_string(lead_info_str)
        logging.info(
            "HANDLER: 'start' event processed. Stream: %s, Call: %s",
            self.stream_sid,
            self.call_sid,
        )
        break  # Exit loop once "start" is received

      if not self.stream_sid:
        await self.websocket.close(
            code=1002, reason="Protocol error: 'start' event not received"
        )
        return

      await self.start_agent_session(session_id=self.call_sid)

      agent_task = asyncio.create_task(self.agent_to_twilio_messaging())
      twilio_task = asyncio.create_task(self.twilio_to_agent_messaging())

      _, pending = await asyncio.wait(
          [agent_task, twilio_task], return_when=asyncio.FIRST_COMPLETED
      )
      for task in pending:
        if not task.done():
          logging.debug(
              "WEBSOCKET: [%s] Cancelling pending bridge task...",
              self.stream_sid,
          )
          task.cancel()
          with suppress(asyncio.CancelledError):
            await task
    except WebSocketDisconnect:
      logging.info(
          "WEBSOCKET: [%s] Client WebSocket disconnected"
          " (detected in listener).",
          self.stream_sid,
      )
      if self.live_request_queue:
        self.live_request_queue.close()
    except asyncio.CancelledError:
      logging.info(
          "WEBSOCKET: Endpoint task cancelled for session: %s", self.stream_sid
      )
    except Exception as e:  # pylint: disable=broad-exception-caught
      logging.exception(
          "WEBSOCKET: Unhandled exception in session %s: %s",
          self.stream_sid,
          e,
      )
      with suppress(Exception):
        if self.call_sid:
          await self.telephony_service.end_call(self.call_sid)
        await self.websocket.close(
            code=1011, reason=f"Internal Server Error: {type(e).__name__}"
        )
    finally:
      logging.info("WEBSOCKET: Final cleanup for session: %s", self.stream_sid)
      if self.live_request_queue:
        logging.debug(
            f"WEBSOCKET: [%s] Closing live request queue in final cleanup.",
            self.stream_sid,
        )
        try:
          self.live_request_queue.close()
        except Exception as q_close_err:
          logging.warning(
              "WEBSOCKET: [%s] Error closing LiveRequestQueue: %s",
              self.stream_sid,
              q_close_err,
          )
      if agent_task and not agent_task.done():
        agent_task.cancel()
      if twilio_task and not twilio_task.done():
        twilio_task.cancel()
      if self.agent_session:
        await self.agent_session.close()
      if self.call_sid:
        await self.telephony_service.end_call(self.call_sid)
      await self.websocket.close(code=1000, reason="Connection closed")
