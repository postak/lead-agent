"""Utility functions for Google Calendar integration."""

import datetime
import json
import logging
import pathlib
from typing import Any

from google.auth.transport import requests
from google.oauth2 import credentials
from google_auth_oauthlib import flow
from googleapiclient import discovery

Path = pathlib.Path
Request = requests.Request
build = discovery.build
InstalledAppFlow = flow.InstalledAppFlow
Credentials = credentials.Credentials

_SCOPES = ["https://www.googleapis.com/auth/calendar"]
_CREDENTIALS_PATH = Path("credentials.json")


def get_calendar_service() -> discovery.Resource | None:
  """Authenticate and create a Google Calendar service object.

  Returns:
      A Google Calendar service object or None if authentication fails
  """
  if _CREDENTIALS_PATH.exists():
    creds = Credentials.from_authorized_user_info(
        json.loads(_CREDENTIALS_PATH.read_text()), _SCOPES
    )
  else:
    logging.error(
        "Error: %s not found. Please follow setup instructions.",
        _CREDENTIALS_PATH,
    )
    return None

  return build("calendar", "v3", credentials=creds)


def format_event_time(event_time: dict[str, str]) -> str:
  """Format an event time into a human-readable string.

  Args:
      event_time: The event time dictionary from Google Calendar API

  Returns:
      str: A human-readable time string
  """
  if "dateTime" in event_time:
    dt = datetime.datetime.fromisoformat(
        event_time["dateTime"].replace("Z", "+00:00")
    )
    return dt.strftime("%Y-%m-%d %I:%M %p")
  elif "date" in event_time:
    return f"{event_time['date']} (All day)"
  return "Unknown time format"


def parse_datetime(datetime_str: str) -> datetime.datetime | None:
  """Parse a datetime string into a datetime object.

  Args:
      datetime_str: A string representing a date and time

  Returns:
      datetime: A datetime object or None if parsing fails
  """
  formats = [
      "%Y-%m-%d %H:%M",
      "%Y-%m-%d %I:%M %p",
      "%Y-%m-%d",
      "%m/%d/%Y %H:%M",
      "%m/%d/%Y %I:%M %p",
      "%m/%d/%Y",
      "%B %d, %Y %H:%M",
      "%B %d, %Y %I:%M %p",
      "%B %d, %Y",
  ]

  for fmt in formats:
    try:
      return datetime.datetime.strptime(datetime_str, fmt)
    except ValueError:
      continue

  return None


def get_current_time() -> dict[str, str]:
  """Get the current time and date."""
  now = datetime.datetime.now()

  # Format date as MM-DD-YYYY
  formatted_date = now.strftime("%m-%d-%Y")

  return {
      "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
      "formatted_date": formatted_date,
  }


def create_event(
    title: str,
    start_time: str,
    end_time: str,
    attendees: list[str],
) -> dict[str, Any]:
  """Create a new event in Google Calendar.

  Args:
      title: Event title/summary
      start_time: Start time (e.g., "2023-12-31 14:00")
      end_time: End time (e.g., "2023-12-31 15:00")
      attendees (list): List of attendees' email addresses

  Returns:
      dict: Information about the created event or error details
  """
  try:
    # Get calendar service
    service = get_calendar_service()
    if not service:
      return {
          "status": "error",
          "message": (
              "Failed to authenticate with Google Calendar. Please check"
              " credentials."
          ),
      }

    calendar_id = "primary"
    start_dt = parse_datetime(start_time)
    end_dt = parse_datetime(end_time)

    if not start_dt or not end_dt:
      return {
          "status": "error",
          "message": (
              "Invalid date/time format. Please use YYYY-MM-DD HH:MM format."
          ),
      }
    timezone_id = "America/New_York"  # Default to Eastern Time

    event_body = {}
    event_body["summary"] = title
    event_body["start"] = {
        "dateTime": start_dt.isoformat(),
        "timeZone": timezone_id,
    }
    event_body["end"] = {
        "dateTime": end_dt.isoformat(),
        "timeZone": timezone_id,
    }
    event_body["attendees"] = [{"email": attendee} for attendee in attendees]

    event = (
        service.events()
        .insert(calendarId=calendar_id, body=event_body)
        .execute()
    )

    return {
        "status": "success",
        "message": "Event created successfully",
        "event_id": event["id"],
        "event_link": event.get("htmlLink", ""),
    }

  except Exception as e:  # pylint: disable=broad-exception-caught
    return {"status": "error", "message": f"Error creating event: {str(e)}"}


def delete_event(
    event_id: str,
    confirm: bool,
) -> dict[str, Any]:
  """Delete an event from Google Calendar.

  Args:
      event_id: The unique ID of the event to delete
      confirm: Confirmation flag (must be set to True to delete)

  Returns:
      Operation status and details
  """
  # Safety check - require explicit confirmation
  if not confirm:
    return {
        "status": "error",
        "message": "Please confirm deletion by setting confirm=True",
    }

  try:
    # Get calendar service
    service = get_calendar_service()
    if not service:
      return {
          "status": "error",
          "message": (
              "Failed to authenticate with Google Calendar. Please check"
              " credentials."
          ),
      }

    # Always use primary calendar
    calendar_id = "primary"

    # Call the Calendar API to delete the event
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()

    return {
        "status": "success",
        "message": f"Event {event_id} has been deleted successfully",
        "event_id": event_id,
    }

  except Exception as e:  # pylint: disable=broad-exception-caught
    return {"status": "error", "message": f"Error deleting event: {str(e)}"}


def edit_event(
    event_id: str,
    summary: str,
    start_time: str,
    end_time: str,
) -> dict[str, Any]:
  """Edit an existing event in Google Calendar - change title and/or reschedule.

  Args:
      event_id: The ID of the event to edit
      summary: New title/summary for the event (pass empty string to keep
        unchanged)
      start_time: New start time (e.g., "2023-12-31 14:00", pass empty string to
        keep unchanged)
      end_time: New end time (e.g., "2023-12-31 15:00", pass empty string to
        keep unchanged)

  Returns:
      dict: Information about the edited event or error details
  """
  try:
    service = get_calendar_service()
    if not service:
      return {
          "status": "error",
          "message": (
              "Failed to authenticate with Google Calendar. Please check"
              " credentials."
          ),
      }

    calendar_id = "primary"

    try:
      event = (
          service.events()
          .get(calendarId=calendar_id, eventId=event_id)
          .execute()
      )
    except Exception:  # pylint: disable=broad-exception-caught
      return {
          "status": "error",
          "message": f"Event with ID {event_id} not found in primary calendar.",
      }

    if summary:
      event["summary"] = summary

    timezone_id = "America/New_York"  # Default
    if "start" in event and "timeZone" in event["start"]:
      timezone_id = event["start"]["timeZone"]

    if start_time:
      start_dt = parse_datetime(start_time)
      if not start_dt:
        return {
            "status": "error",
            "message": (
                "Invalid start time format. Please use YYYY-MM-DD HH:MM format."
            ),
        }
      event["start"] = {
          "dateTime": start_dt.isoformat(),
          "timeZone": timezone_id,
      }

    if end_time:
      end_dt = parse_datetime(end_time)
      if not end_dt:
        return {
            "status": "error",
            "message": (
                "Invalid end time format. Please use YYYY-MM-DD HH:MM format."
            ),
        }
      event["end"] = {"dateTime": end_dt.isoformat(), "timeZone": timezone_id}

    updated_event = (
        service.events()
        .update(calendarId=calendar_id, eventId=event_id, body=event)
        .execute()
    )

    return {
        "status": "success",
        "message": "Event updated successfully",
        "event_id": updated_event["id"],
        "event_link": updated_event.get("htmlLink", ""),
    }

  except Exception as e:  # pylint: disable=broad-exception-caught
    return {"status": "error", "message": f"Error updating event: {str(e)}"}


def list_events(
    start_date: str,
    days: int,
) -> dict[str, Any]:
  """List upcoming calendar events within a specified date range.

  Args:
      start_date: Start date in YYYY-MM-DD format. If empty string, defaults to
        today.
      days: Number of days to look ahead. Use 1 for today only, 7 for a week, 30
        for a month, etc.

  Returns:
      Information about upcoming events or error details
  """
  try:
    service = get_calendar_service()
    if not service:
      return {
          "status": "error",
          "message": (
              "Failed to authenticate with Google Calendar. Please check"
              " credentials."
          ),
          "events": [],
      }

    max_results = 100
    calendar_id = "primary"

    if not start_date or not start_date.strip():
      start_time = datetime.datetime.now(datetime.timezone.utc)
    else:
      try:
        start_time = datetime.datetime.strptime(start_date, "%Y-%m-%d")
      except ValueError:
        return {
            "status": "error",
            "message": (
                f"Invalid date format: {start_date}. Use YYYY-MM-DD format."
            ),
            "events": [],
        }

    if not days or days < 1:
      days = 1

    end_time = start_time + datetime.timedelta(days=days)
    time_min = start_time.isoformat() + "Z"
    time_max = end_time.isoformat() + "Z"
    events_result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = events_result.get("items", [])

    if not events:
      return {
          "status": "success",
          "message": "No upcoming events found.",
          "events": [],
      }

    formatted_events = []
    for event in events:
      formatted_event = {
          "id": event.get("id"),
          "summary": event.get("summary", "Untitled Event"),
          "start": format_event_time(event.get("start", {})),
          "end": format_event_time(event.get("end", {})),
          "location": event.get("location", ""),
          "description": event.get("description", ""),
          "attendees": [
              attendee.get("email")
              for attendee in event.get("attendees", [])
              if "email" in attendee
          ],
          "link": event.get("htmlLink", ""),
      }
      formatted_events.append(formatted_event)

    return {
        "status": "success",
        "message": f"Found {len(formatted_events)} event(s).",
        "events": formatted_events,
    }

  except Exception as e:  # pylint: disable=broad-exception-caught
    return {
        "status": "error",
        "message": f"Error fetching events: {str(e)}",
        "events": [],
    }
