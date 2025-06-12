"""Helper functions for working with audio."""

import audioop
import base64
import json

from absl import logging


ADK_TTS_OUTPUT_SAMPLE_RATE = 24000
TWILIO_SAMPLE_RATE = 8000


def convert_pcm_audio_to_mulaw(
    pcm_audio_data_bytes: bytes,
    pcm_sample_rate: int = ADK_TTS_OUTPUT_SAMPLE_RATE,
    mulaw_sample_rate: int = TWILIO_SAMPLE_RATE,
) -> str:
  """Resamples, encodes, and base64-encodes audio.

  Args:
    pcm_audio_data_bytes: The audio data in PCM format.
    pcm_sample_rate: The sample rate of the PCM audio data.
    mulaw_sample_rate: The desired sample rate for the mu-law encoded audio.

  Returns:
    A base64-encoded string representing the mu-law encoded audio data.
  """
  data, _ = audioop.ratecv(
      pcm_audio_data_bytes,
      2,
      1,
      pcm_sample_rate,
      mulaw_sample_rate,
      None,
  )
  mulaw_audio = audioop.lin2ulaw(data, 2)
  b64_mulaw_audio = base64.b64encode(mulaw_audio).decode("utf-8")
  return b64_mulaw_audio


def decode_json_string(json_string: str) -> dict[str, str]:
  """Decodes a base64-encoded JSON string to a dictionary.

  Args:
    json_string: The base64-encoded JSON string.

  Returns:
    The decoded JSON string as a dictionary.
  """
  try:
    decoded_lead_info_json = base64.urlsafe_b64decode(json_string).decode(
        "utf-8"
    )
    return json.loads(decoded_lead_info_json)
  except json.JSONDecodeError as e:
    logging.error(
        "Could not decode json_string: %s. Error: %s",
        json_string,
        e,
    )


def convert_mulaw_audio_to_pcm(mulaw_audio_payload: str) -> bytes:
  """Converts a mulaw audio payload to PCM.

  Args:
    mulaw_audio_payload: The mulaw audio payload.

  Returns:
    The PCM audio data.
  """
  decoded_audio = base64.b64decode(mulaw_audio_payload)
  return audioop.ulaw2lin(decoded_audio, 2)