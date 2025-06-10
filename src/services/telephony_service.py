"""This module provides a Twilio telephony service."""

import base64
import json

from absl import logging
from src.config import settings
from twilio import rest
from twilio.base.exceptions import TwilioException
from twilio.twiml import voice_response

Client = rest.Client
Connect = voice_response.Connect
VoiceResponse = voice_response.VoiceResponse
Stream = voice_response.Stream


class TwilioTelephonyService:
  """Manages initiating and controlling calls via the Twilio REST API.

  For live, interactive conversations, this service works in conjunction
  with a WebSocket handler that manages the Twilio Media Stream.
  """

  def __init__(self):
    try:
      self.client = Client(
          settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN
      )
      logging.info("SERVICE: Twilio client initialized successfully.")
    except TwilioException as e:
      self.client = None
      logging.critical(
          "SERVICE_ERROR: Failed to initialize Twilio client: %s", e
      )

  def initiate_call_with_stream(self, lead_info: dict[str, str]) -> str | None:
    """Initiates an outbound call using Twilio.

    Instructs Twilio to connect a bidirectional media stream
    to a WebSocket endpoint.

    Args:
        lead_info: A dictionary containing initial context for the agent.

    Returns:
        The Call SID if the call was successfully initiated, None otherwise.
    """
    if not self.client:
      logging.error(
          "SERVICE_ERROR: Cannot initiate call, Twilio client not available."
      )
      return None

    phone_number = lead_info.get("phone_number")
    lead_id = lead_info.get("lead_id")
    if not phone_number or not lead_id:
      logging.error(
          "SERVICE_ERROR: Phone number or lead_id missing in lead_info."
      )
      return None

    try:
      lead_context_json = json.dumps(lead_info)
      lead_context_b64 = base64.urlsafe_b64encode(
          lead_context_json.encode("utf-8")
      ).decode("utf-8")

      websocket_url = (
          f"{settings.BASE_URL.replace('http://', 'ws://').replace('https://', 'wss://')}/api/ws/twilio_stream"
      )

      logging.info(
          "SERVICE: Using WebSocket stream URL for Twilio: %s",
          websocket_url,
      )

      twiml_response = VoiceResponse()
      connect = Connect()
      stream = Stream(url=websocket_url)
      stream.parameter(name="lead_info", value=lead_context_b64)
      connect.append(stream)
      twiml_response.append(connect)
      status_callback_url = f"{settings.BASE_URL}/api/twilio_status_handler"

      logging.info(
          "SERVICE: Initiating Twilio stream call to %s from %s for lead_id %s",
          phone_number,
          settings.TWILIO_VIRTUAL_PHONE_NUMBER,
          lead_id,
      )

      call = self.client.calls.create(
          to=phone_number,
          from_=settings.TWILIO_VIRTUAL_PHONE_NUMBER,
          twiml=twiml_response.to_xml(),
          status_callback=status_callback_url,
          status_callback_method="POST",
          status_callback_event=[
              "initiated",
              "ringing",
              "answered",
              "completed",
              "failed",
              "busy",
              "no-answer",
          ],
      )

      logging.info(
          "SERVICE: Twilio call initiated. Call SID: %s and twiml %s",
          call.sid,
          twiml_response.to_xml(),
      )
      return call.sid

    except TwilioException as e:
      logging.error(
          "SERVICE_ERROR: Failed to initiate Twilio stream call for lead_id"
          " %s: %s",
          lead_id,
          e,
      )
      return None

  def end_call(self, call_sid: str) -> bool:
    """Terminates an active call using the Twilio REST API.

    Args:
        call_sid: The SID of the call to terminate.

    Returns:
        True if the call was successfully terminated, False otherwise.
    """
    if not self.client:
      logging.error(
          "SERVICE_ERROR: Cannot end call %s, Twilio client not available.",
          call_sid,
      )
      return False
    try:
      logging.info(
          "SERVICE: Requesting to terminate call SID %s via REST API.", call_sid
      )
      call = self.client.calls(call_sid).update(status="completed")
      logging.info(
          "SERVICE: Call %s status updated to '%s' via API.",
          call_sid,
          call.status,
      )
      return True
    except TwilioException as e:
      logging.warning(
          "SERVICE_WARNING: Failed to terminate call %s (it may have already"
          " ended): %s",
          call_sid,
          e,
      )
      return False


# Singleton instance to be used by other parts of the application.
telephony_service = TwilioTelephonyService()
