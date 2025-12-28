from datetime import datetime
import json
from openai import OpenAI,pydantic_function_tool
import os
from pydantic import BaseModel,Field
from utils.google_calendar_utils import list_events_on_date,create_event,delete_event


# define pydantic models for responses

class CalendarEventsResponse(BaseModel):
    date:str
    time:str
    events_description:str = Field(description="A natural language response to user's question.")

#define tools and their input models 

class ListEvents(BaseModel):
    target_date_str: str = Field("The date to list events for, in YYYY-MM-DD format.")

class CreateEvent(BaseModel):
    event_title: str = Field("The title of the event to create.")
    event_date_str: str = Field("The date of the event to create, in YYYY-MM-DD format.")
    event_time_str: str = Field("The time of the event to create, in HH:MM format.")
    duration_minutes: int = Field(default = 30,description="The duration of the event to create, in minutes.")

class UpdateEvent(BaseModel):
    event_id: str = Field("The ID of the event to update.")
    new_date_str: str = Field("The new date for the event, in YYYY-MM-DD format.")
    new_time_str: str = Field("The new time for the event, in HH:MM format.")

class DeleteEvent(BaseModel):
    event_id: str = Field("The ID of the event to delete. If you don't have the ID use the list_events_on_date tool to find it first.")

tools = [pydantic_function_tool(ListEvents, name="list_events_on_date"),
         pydantic_function_tool(CreateEvent, name="create_event"),
         pydantic_function_tool(DeleteEvent, name="delete_event")]

# logic to actually call function

def call_function(name, args):
    if name == "list_events_on_date":
        return list_events_on_date(**args)
    elif name == "create_event":
        return create_event(**args)
    elif name == "update_event":
        return update_event(**args)
    elif name == "delete_event":
        print(f"CONFIRMATION REQUIRED: The agent wants to delete event ID: {args.event_id}")
        confirm = input("Confirm deletion? (y/n): ")
        if confirm.lower() == "y":
            return delete_event(**args)
        else:
            print("Deletion canceled.")
            return {"status": "canceled", "message": "Event deletion was canceled by the user."}


# main agent loop

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
user_question = input("Ask a question about your calendar: ")
current_date = datetime.now().strftime("%Y-%m-%d")

messages = [
        {"role":"system","content":f"You are a helpful assistant. Today is {current_date}."},
        {"role":"user","content":user_question},
    ]

max_iterations = 5
for _ in range(max_iterations):
    print('hello')
    completion = client.beta.chat.completions.parse(
        model = "gpt-4o-mini",
        messages = messages,
        tools = tools
    )
    response_message = completion.choices[0].message
    messages.append(response_message)

    if response_message.tool_calls:
        for tool_call in response_message.tool_calls:
            name = tool_call.function.name
            args = tool_call.function.parsed_arguments.model_dump()

            print(f"🛠️ Agent calling tool: {name}")
            result = call_function(name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result)
            })

        continue
    
    else:
        final_completion = client.beta.chat.completions.parse(
            model = "gpt-4o-mini",
            messages = messages,
            response_format = CalendarEventsResponse
        )
        break

if not final_completion:
    print("Max iterations reached without a final answer.")
    exit(1)

final_response = final_completion.choices[0].message.parsed
#print(completion.model_dump())
#print(completion2.model_dump())
print(final_response.events_description)


# response = completion.choices[0].message.parsed.time
# print(response)