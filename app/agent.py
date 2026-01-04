from datetime import datetime,timedelta
import json
from openai import OpenAI,pydantic_function_tool
import os
from pydantic import BaseModel,Field
from typing import Optional
from zoneinfo import ZoneInfo
from app.utils.google_calendar_utils import list_events_on_date,create_event,delete_event,update_event,get_event_info,check_for_conflicts,get_calendar_timezone




# define pydantic models for responses

class CalendarEventsResponse(BaseModel):
    date:str
    time:str
    events_description:str = Field(description="A natural language response to user's question.")

#define tools and their input models 

class ListEvents(BaseModel):
    target_date_str: str = Field("The date to list events for, in YYYY-MM-DD format.")

class GetEventInfo(BaseModel):
    event_id: str = Field("The ID of the event to retrieve information for.")

class CreateEvent(BaseModel):
    event_title: str = Field("The title of the event to create.")
    event_date_str: str = Field("The date of the event to create, in YYYY-MM-DD format.")
    event_time_str: str = Field("The time of the event to create, in HH:MM format.")
    duration_minutes: int = Field(default = 30,description="The duration of the event to create, in minutes.")
    force_ignore_conflict: bool = Field(description="Set to True only if the user explicitly told you to ignore conflicts.")

class UpdateEvent(BaseModel):
    event_id: str = Field("The ID of the event to update.")
    new_title: Optional[str] = Field("The new title for the event.")
    new_date_str: Optional[str] = Field("The new date for the event, in YYYY-MM-DD format.")
    new_time_str: Optional[str] = Field("The new time for the event, in HH:MM format.")
    new_duration_minutes: Optional[int] = Field("The new duration of the event, in minutes. The default is to keep the existing duration." \
    " If you don't have this information, use the GetEventInfo tool to fetch the current event details first.")
    force_ignore_conflict: bool = Field(description="Set to True only if the user explicitly told you to ignore conflicts.")

class DeleteEvent(BaseModel):
    event_id: str = Field("The ID of the event to delete. If you don't have the ID use the list_events_on_date tool to find it first.")

class CheckForConflicts(BaseModel):
    event_date_str: str = Field("The date of the event to check for conflicts, in YYYY-MM-DD format.")
    event_time_str: str = Field("The time of the event to check for conflicts, in HH:MM format.")
    duration_minutes: Optional[int] = Field("The duration of the event to check for conflicts, in minutes.")
    ignore_id: Optional[str] = Field("An event ID to ignore when checking for conflicts, useful when updating an existing event.")

# list of tools available to agent

tools = [pydantic_function_tool(ListEvents, name="list_events_on_date"),
         pydantic_function_tool(CreateEvent, name="create_event"),
         pydantic_function_tool(DeleteEvent, name="delete_event"),
         pydantic_function_tool(UpdateEvent, name="update_event"),
         pydantic_function_tool(GetEventInfo, name="get_event_info"),
         pydantic_function_tool(CheckForConflicts, name="check_for_conflicts")]

# logic to actually call functions

def call_function(name, args,user_timezone):
    if name == "list_events_on_date":
        return list_events_on_date(target_date_str=args['target_date_str'], user_timezone=user_timezone)

    elif name == "create_event":
        conflicts = check_for_conflicts(event_date_str=args['event_date_str'], event_time_str=args['event_time_str'], duration_minutes=args['duration_minutes'], timezone=user_timezone)
        if conflicts and not args.get("force_ignore_conflict"):
            conflict_names = ", ".join([c.get("summary") for c in conflicts])
            return {"status": "error", "message": f"Event conflicts with existing events: {conflict_names}"}
        return create_event(event_date_str=args.get("event_date_str"), event_time_str=args.get("event_time_str"), event_title=args.get("event_title"), duration_minutes=args.get("duration_minutes"), timezone=user_timezone)

    elif name == "update_event":
        existing_event = get_event_info(args["event_id"])
        if not existing_event:
            return {"status": "error", "message": "Event not found."}
        
        start_str = existing_event['start'].get('dateTime', existing_event['start'].get('date'))
        end_str = existing_event['end'].get('dateTime', existing_event['end'].get('date'))
        
        # Simple ISO parse (ignores timezone offset for the math)
        fmt = "%Y-%m-%dT%H:%M:%S"
        curr_start = datetime.strptime(start_str[:19], fmt)
        curr_end = datetime.strptime(end_str[:19], fmt)
        original_duration = int((curr_end - curr_start).total_seconds() / 60)

        body = {}
        if args.get("new_title"):
            body["summary"] = args["new_title"]

        if args.get("new_date_str") or args.get("new_time_str"):

            final_date = args.get("new_date_str") or start_str[:10]
            final_time = args.get("new_time_str") or start_str[11:16]
            
            # check for conflicts with updated date/time
            conflicts = check_for_conflicts(event_date_str=final_date, event_time_str=final_time, duration_minutes=original_duration, ignore_id=args["event_id"], timezone=user_timezone)
            if conflicts and not args.get("force_ignore_conflict"):
                conflict_names = ", ".join([c.get("summary") for c in conflicts])
                return {"status": "error", "message": f"Event conflicts with existing events: {conflict_names}"}

            start_dt = datetime.strptime(f"{final_date} {final_time}", "%Y-%m-%d %H:%M")
            end_dt = start_dt + timedelta(minutes=original_duration)

            # 3. Convert back to ISO format for Google (e.g., '2025-12-28T14:00:00')
            body["start"] = {
                "dateTime": start_dt.isoformat(), 
                "timeZone": user_timezone
            }
            body["end"] = {
                "dateTime": end_dt.isoformat(), 
                "timeZone": user_timezone
            }
        return update_event(event_id=args["event_id"], updates=body)
    
    elif name == "delete_event":
        print(f"CONFIRMATION REQUIRED: The agent wants to delete event ID: {args['event_id']}")
        confirm = input("Confirm deletion? (y/n): ")
        if confirm.lower() == "y":
            return delete_event(**args)
        else:
            print("Deletion canceled.")
            return {"status": "canceled", "message": "Event deletion was canceled by the user."}

# version for integration with fast api
def run_assistant(client, messages : list, user_timezone: str):
    now = datetime.now(ZoneInfo(user_timezone))
    current_date = now.strftime("%Y-%m-%d")

    system_message = {"role": "system", "content": f"You are a helpful assistant. CRITICAL: Today is {current_date}. Be very careful about dates and times. Do not invent events or details. Do not do things on dates and times that were not discussed with the user. Always refer to the what has been going on in the actual conversation with the user to make decisions.IMPORTANT RULES FOR SEARCHING: 1. When a user mentions a specific day (like 'tomorrow' or 'Friday'), you MUST search for the ENTIRE day, from 00:00:00 to 23:59:59. 2. Do not limit searches to the current time of day. 3. If a user asks about a day, assume they mean the whole day starting first 00:00:00 to 23:59:59. 4. If the user asks about a certain day, ONLY refer to events that start on or after 00:00:00 of the requested day. Do not include events from previous days or future days."}

    active_conversation = [system_message] + messages

    max_iterations = 5
    for _ in range(max_iterations):
        completion = client.beta.chat.completions.parse(
            model = "gpt-4o-mini",
            messages = active_conversation,
            tools = tools,
            response_format = CalendarEventsResponse
        )
        response_message = completion.choices[0].message
        active_conversation.append(response_message)

        if response_message.tool_calls:
            for tool_call in response_message.tool_calls:
                print(f"DEBUG: LLM is calling tool with args:{tool_call.function.arguments}")
                name = tool_call.function.name
                args = tool_call.function.parsed_arguments.model_dump()

                print(f"🛠️ Agent calling tool: {name}")
                result = call_function(name, args,user_timezone)
                active_conversation.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result)
                })

            continue
        
        else:
            break

    if response_message.tool_calls:
        return "Max iterations reached without a final answer."

    final_response = response_message.parsed
    return final_response.events_description



def main():
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    current_date = datetime.now().strftime("%Y-%m-%d")
    user_timezone = get_calendar_timezone()

    while True:
        user_question = input("Ask a question about your calendar: ")
        

        messages = [
                {"role": "system", "content": f"You are a helpful assistant. CRITICAL: Today is {current_date}. Be very careful about dates and times. Do not invent events or details. Do not do things on dates and times that were not discussed with the user. Always refer to the what has been going on in the actual conversation with the user to make decisions."},
                {"role": "user", "content": user_question},
            ]

        max_iterations = 5
        for _ in range(max_iterations):
            completion = client.beta.chat.completions.parse(
                model = "gpt-4o-mini",
                messages = messages,
                tools = tools,
                response_format = CalendarEventsResponse
            )
            response_message = completion.choices[0].message
            messages.append(response_message)

            if response_message.tool_calls:
                for tool_call in response_message.tool_calls:
                    print(f"DEBUG: LLM is calling tool with args:{tool_call.function.arguments}")
                    name = tool_call.function.name
                    args = tool_call.function.parsed_arguments.model_dump()

                    print(f"🛠️ Agent calling tool: {name}")
                    result = call_function(name, args,user_timezone)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result)
                    })

                continue
            
            else:
                # final_completion = client.beta.chat.completions.parse(
                #     model = "gpt-4o-mini",
                #     messages = messages,
                #     response_format = CalendarEventsResponse
                # )
                break

        if not completion:
            print("Max iterations reached without a final answer.")
            exit(1)

        final_response = completion.choices[0].message.parsed
        print(final_response.events_description)

if __name__ == "__main__":
    main()