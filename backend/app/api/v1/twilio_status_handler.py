# app/api/v1/twilio_status_handler.py (New File)
from fastapi import APIRouter, Form, Response
from absl import logging

router = APIRouter(
    prefix="/api/v1", tags=["Twilio Status Callbacks"]  # Or adjust as needed
)


@router.post("/twilio_status_handler")
async def handle_twilio_call_status(
    CallSid: str = Form(...),
    CallStatus: str = Form(...),
    # Twilio sends many other parameters, you can capture them as needed
    # See: https://www.twilio.com/docs/voice/api/call-resource#statuscallback
    From: str = Form(None),
    To: str = Form(None),
    Direction: str = Form(None),
    CallDuration: str = Form(None),  # Duration in seconds
    SipResponseCode: str = Form(None),  # If applicable
    # ... any other fields you care about
):
  """
  Receives call status updates from Twilio.
  This endpoint should be publicly accessible.
  """
  logging.info(
      "TWILIO_STATUS_CALLBACK: CallSid: %s, CallStatus: %s, From: %s, To: %s,"
      " Duration: %s",
      CallSid,
      CallStatus,
      From,
      To,
      CallDuration,
  )

  # Here, you can implement logic based on the call status:
  if CallStatus == "completed":
    logging.info(
        "Call %s completed. Duration: %s seconds.", CallSid, CallDuration
    )
    # TODO: Update your database, trigger post-call analysis, notify CRM, etc.
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

  return Response(status_code=200)  # Always return a 200 OK to Twilio
