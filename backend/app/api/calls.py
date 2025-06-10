# app/api/v1/twilio_status_handler.py (New File)
from fastapi import APIRouter, Form, Response
from absl import logging

from app.schemas import lead
from app.services import telephony_service as telephony_service_lib

LeadWebhookPayload = lead.LeadWebhookPayload
telephony_service = telephony_service_lib.telephony_service


router = APIRouter(prefix="/api", tags=["Calls"])  # Or adjust as needed


@router.post("/initiate_call", status_code=202)
async def initiate_call_endpoint(payload: LeadWebhookPayload) -> Response:
  """HTTP Webhook to receive a lead and command Twilio to make a call."""
  logging.info("INITIATE_CALL: Received lead for %s", payload.lead_id)
  call_sid = telephony_service.initiate_call_with_stream(
      lead_info=payload.model_dump(),
  )
  if call_sid:
    return {"status": "call_initiated", "call_sid": call_sid}
  return Response(status_code=500, content="Failed to initiate call")


@router.post("/twilio_status_handler")
async def handle_twilio_call_status(
    CallSid: str = Form(...),
    CallStatus: str = Form(...),
    From: str = Form(None),
    To: str = Form(None),
    Direction: str = Form(None),
    CallDuration: str = Form(None),
    SipResponseCode: str = Form(None),
):
  """Receives call status updates from Twilio."""
  try:
    logging.info(
        "TWILIO_STATUS_CALLBACK: CallSid: %s, CallStatus: %s, From: %s, To: %s,"
        " Duration: %s",
        CallSid,
        CallStatus,
        From,
        To,
        CallDuration,
    )

    if CallStatus == "completed":
      logging.info(
          "Call %s completed. Duration: %s seconds.", CallSid, CallDuration
      )
      # TODO: Update database, trigger post-call analysis, notify CRM, etc.
      # Example: await crm_service.log_call_completed(CallSid, CallDuration, From, To)
    elif CallStatus == "failed":
      logging.error(
          "Call %s failed. SipResponseCode: %s", CallSid, SipResponseCode
      )
      # TODO: Handle failed call, maybe retry logic or alert.
    elif CallStatus == "no-answer":
      logging.warning("Call %s was not answered.", CallSid)
      # TODO: Update lead status to "No Answer".
    elif CallStatus == "busy":
      logging.warning("Call %s was busy.", CallSid)
      # TODO: Update lead status to "Busy".
    # Add handling for other statuses like "ringing", "initiated", "canceled" if needed.
  except Exception as e:
    logging.exception(
        "TWILIO STATUS HANDLER: Error handling call status: %s", e
    )

  return Response(status_code=200)
