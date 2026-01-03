import datetime
import os.path
from typing import List, Dict, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from zoneinfo import ZoneInfo

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar.events", "https://www.googleapis.com/auth/calendar.readonly"] 

def get_calendar_service():
    """
    Handles the Google Calendar API authentication flow.
    Returns an authenticated Google Calendar service object.
    """
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing Google Calendar API credentials...")
            creds.refresh(Request())
        else:
            print("Initiating Google Calendar API OAuth flow...")
            # Ensure credentials.json is in the same directory as this script
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())
        print("Google Calendar API credentials saved to token.json.")

    try:
        service = build("calendar", "v3", credentials=creds)
        return service
    except HttpError as error:
        print(f"An error occurred connecting to Google Calendar API: {error}")
        return None
    
def list_events_on_date(target_date_str: str) -> List[Dict]:
    """
    Lists events on a specific date from the user's primary Google Calendar.

    Args:
        target_date_str: The date in 'YYYY-MM-DD' format (e.g., '2025-06-15').

    Returns:
        A list of dictionaries, each representing an event's summary, start, and end time.
        Returns an empty list if no events or an error occurs.
    """
    service = get_calendar_service()
    if not service:
        return {"error": "Failed to connect to Google Calendar API."}

    try:
        # Parse the target_date_str into a date object
        target_date = datetime.datetime.strptime(target_date_str, "%Y-%m-%d").date()

        # Set timeMin to the beginning of the target date (UTC)
        time_min = datetime.datetime(
            target_date.year, target_date.month, target_date.day,
            0, 0, 0, tzinfo=datetime.timezone.utc
        ).isoformat()

        # Set timeMax to the end of the target date (UTC)
        time_max = datetime.datetime(
            target_date.year, target_date.month, target_date.day,
            23, 59, 59, tzinfo=datetime.timezone.utc
        ).isoformat()

        print(f"Searching for events between {time_min} and {time_max}")

        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])

        if not events:
            return {"message": f"No events found on {target_date_str}."}

        event_list = []
        for event in events:
            # Handle full-day events vs timed events
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))
            event_list.append({
                "summary": event.get("summary", "No Title"),
                "start": start,
                "end": end,
                "htmlLink": event.get("htmlLink"),
                "event_id": event.get("id")  
            })
        return {"events": event_list, "message": f"Found {len(event_list)} events on {target_date_str}."}

    except ValueError:
        return {"error": "Invalid date format. Please provide date in YYYY-MM-DD."}
    except HttpError as error:
        print(f"An API error occurred: {error}")
        return {"error": f"Failed to retrieve events from Calendar API: {error.content.decode('utf-8')}"}
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return {"error": f"An unexpected error occurred: {e}"}
    
def get_event_info(event_id: str) -> Optional[Dict]:
    service = get_calendar_service()
    if not service:
        return None
    try:
        event = service.events().get(calendarId='primary', eventId=event_id).execute()
        return event
    except Exception as e:
        print(f"Error fetching event info: {e}")
        return None

def create_event(event_title: str, event_date_str: str, event_time_str: str, timezone: str, duration_minutes: int = 30):
    service = get_calendar_service()
    if not service:
        return {"error": "Failed to connect to Google Calendar API."}
    
    start_dt = datetime.datetime.strptime(f"{event_date_str} {event_time_str}", "%Y-%m-%d %H:%M")
    end_dt = start_dt + datetime.timedelta(minutes=duration_minutes)

    start_str = start_dt.isoformat()
    end_str = end_dt.isoformat()

    event = {
        "summary": event_title,
        "start": {
            "dateTime": start_str,
            "timeZone": timezone,
        },
        "end": {
            "dateTime": end_str,
            "timeZone": timezone,
        },
    }

    try:
        created_event = service.events().insert(calendarId="primary", body=event).execute()
        return {"status": "success", "link": created_event.get("htmlLink")}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    
def delete_event(event_id: str):
    service = get_calendar_service()
    if not service:
        return {"error": "Failed to connect to Google Calendar API."}
    try:
        service.events().delete(calendarId="primary", eventId=event_id).execute()
        return {"status": "success", "message": f"Event {event_id} deleted."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    
def update_event(event_id: str, updates: Dict):
    service = get_calendar_service()
    if not service:
        return {"error": "Failed to connect to Google Calendar API."}
    
    try:
        updated_event = service.events().patch(
            calendarId='primary', 
            eventId=event_id, 
            body=updates
        ).execute()
        return {"status": "success", "link": updated_event.get("htmlLink")}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def check_for_conflicts(event_date_str: str, event_time_str: str, timezone: str, duration_minutes: int = 30, ignore_id: str = None) -> list:
    service = get_calendar_service()
    if not service:
        return []

    local_tz = ZoneInfo(timezone)
    start_dt = datetime.datetime.strptime(f"{event_date_str} {event_time_str}", "%Y-%m-%d %H:%M")
    start_dt = start_dt.replace(tzinfo=local_tz)
    end_dt = start_dt + datetime.timedelta(minutes=duration_minutes)

    time_min = start_dt.isoformat()
    time_max = end_dt.isoformat()

    events_result = service.events().list(
        calendarId='primary',
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    events = events_result.get('items', [])
    actual_conflicts = [e for e in events if e.get("id") != ignore_id]
    return actual_conflicts

def get_calendar_timezone():
    service = get_calendar_service()
    setting = service.settings().get(setting='timezone').execute()
    return setting['value']
    
